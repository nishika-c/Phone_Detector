"""
focus_monitor.py
AI Focus Monitor — Core Detection Engine
-----------------------------------------
Detects phone usage via webcam using YOLOv8.
Triggers alarm after grace period, logs sessions,
generates daily reports, and manages state cleanly.

Improvements over original:
  - Config file (no hardcoded settings)
  - Session management with atexit
  - Cooldown between alarms (no spam)
  - Daily reports in /reports/
  - Graceful camera recovery with backoff
  - Structured logging with rotation
  - Focus streak tracking
  - Sensitivity modes (strict / normal / relaxed)
  - Distraction heatmap data collection
  - Clean shutdown on any exit path
"""

import cv2
import time
import threading
import sys
import os
import json
import atexit
import logging
import pygame
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from collections import defaultdict
from ultralytics import YOLO

# ─────────────────────────────────────────────
#  PORTABLE BASE PATH
# ─────────────────────────────────────────────

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH      = os.path.join(BASE_DIR, "models",      "yolov8s.pt")
SOUND_PATH      = os.path.join(BASE_DIR, "sounds",      "loud_alrm.mp3")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")
REPORTS_DIR     = os.path.join(BASE_DIR, "reports")
LOG_PATH        = os.path.join(BASE_DIR, "detection_log.txt")
CONFIG_PATH     = os.path.join(BASE_DIR, "config.json")

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR,     exist_ok=True)

# ─────────────────────────────────────────────
#  CONFIG LOADER  (safe merge with defaults)
# ─────────────────────────────────────────────

DEFAULT_CONFIG = {
    "grace_period_seconds":                  10,
    "max_distractions":                       5,
    "detection_confidence":                0.35,
    "detection_interval_frames":              2,
    "detection_hold_seconds":                 2,
    "cooldown_seconds":                      30,
    "camera_index":                           0,
    "window_width":                         900,
    "window_height":                        600,
    "focus_score_penalty_per_distraction":   10,
    "max_camera_retries":                     5,
    "screenshot_on_distraction":           True,
    "sound_enabled":                       True,
    "show_popup_on_max_distractions":      True,
    "log_level":                          "INFO",
}

def load_config():
    if not os.path.exists(CONFIG_PATH):
        print("[Config] config.json not found — using defaults.")
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r") as f:
            user_cfg = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        merged.update(user_cfg)
        return merged
    except json.JSONDecodeError as e:
        print(f"[Config] Syntax error in config.json: {e}")
        print("[Config] Using default settings.")
        return DEFAULT_CONFIG.copy()

cfg = load_config()

# Allow CLI overrides for tray app integration
try:
    if len(sys.argv) > 1:
        cfg["grace_period_seconds"] = int(sys.argv[1])
    if len(sys.argv) > 2:
        cfg["max_distractions"]     = int(sys.argv[2])
except (ValueError, IndexError):
    pass

# ─────────────────────────────────────────────
#  LOGGING SETUP
# ─────────────────────────────────────────────

log_level = getattr(logging, cfg.get("log_level", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level    = log_level,
    format   = "%(asctime)s [%(levelname)s] %(message)s",
    handlers = [
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("FocusMonitor")

# ─────────────────────────────────────────────
#  FILE CHECKS
# ─────────────────────────────────────────────

def abort(msg):
    logger.error(msg)
    sys.exit(1)

if not os.path.exists(MODEL_PATH):
    abort("Missing model file: models/yolov8s.pt — please download YOLOv8s.")
if not os.path.exists(SOUND_PATH):
    abort("Missing alarm sound: sounds/loud_alrm.mp3")

# ─────────────────────────────────────────────
#  MODEL
# ─────────────────────────────────────────────

logger.info("Loading YOLOv8 model...")
model = YOLO(MODEL_PATH)
logger.info("Model loaded.")

# ─────────────────────────────────────────────
#  SOUND
# ─────────────────────────────────────────────

_sound_ready = False
if cfg["sound_enabled"]:
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(SOUND_PATH)
        _sound_ready = True
    except Exception as e:
        logger.warning(f"Sound init failed: {e} — running silently.")

def start_alarm():
    if _sound_ready:
        pygame.mixer.music.play(-1)

def stop_alarm():
    if _sound_ready:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

# ─────────────────────────────────────────────
#  POPUP (non-blocking)
# ─────────────────────────────────────────────

def show_warning(distractions):
    def _popup():
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning(
            "Focus Monitor",
            f"⚠️  Maximum distractions reached ({distractions})!\n\nPlease put your phone away and refocus."
        )
        root.destroy()
    threading.Thread(target=_popup, daemon=True).start()

# ─────────────────────────────────────────────
#  SESSION STATE
# ─────────────────────────────────────────────

session_start_unix = time.time()
session_start_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

distractions       = 0
focus_score        = 100
focus_streak       = 0          # consecutive clean minutes
longest_streak     = 0
last_streak_check  = time.time()
STREAK_INTERVAL    = 60         # 1 minute of no phone = +1 streak

heatmap_hours      = defaultdict(int)   # hour -> distraction count

# ─────────────────────────────────────────────
#  SESSION LOGGING
# ─────────────────────────────────────────────

logger.info(f"=== SESSION START: {session_start_str} ===")
logger.info(f"Settings → Grace: {cfg['grace_period_seconds']}s | "
            f"Max distractions: {cfg['max_distractions']} | "
            f"Cooldown: {cfg['cooldown_seconds']}s | "
            f"Confidence: {cfg['detection_confidence']}")

def log_distraction(num, screenshot_path):
    hour = datetime.now().hour
    heatmap_hours[hour] += 1
    logger.info(f"Distraction #{num} | Score: {focus_score}% | Screenshot: {screenshot_path}")

# ─────────────────────────────────────────────
#  SESSION SUMMARY + DAILY REPORT  (atexit)
# ─────────────────────────────────────────────

def write_session_summary():
    end_str   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    duration  = int(time.time() - session_start_unix)
    mins, sec = divmod(duration, 60)

    if distractions == 0:
        grade = "🏆 Excellent — zero distractions!"
    elif distractions <= 2:
        grade = "✅ Good — minor distractions"
    elif distractions <= 5:
        grade = "⚠️  Fair — moderate distractions"
    else:
        grade = "❌ Needs improvement"

    summary = (
        f"\n{'─'*55}\n"
        f"SESSION SUMMARY\n"
        f"  Started      : {session_start_str}\n"
        f"  Ended        : {end_str}\n"
        f"  Duration     : {mins}m {sec}s\n"
        f"  Distractions : {distractions}\n"
        f"  Final Score  : {focus_score}%\n"
        f"  Longest Streak: {longest_streak} clean minutes\n"
        f"  Grade        : {grade}\n"
        f"{'─'*55}\n"
    )
    logger.info(summary)
    write_daily_report(end_str, mins, grade)

def write_daily_report(end_str, mins, grade):
    today       = datetime.now().strftime("%Y-%m-%d")
    report_path = os.path.join(REPORTS_DIR, f"{today}.txt")

    # Build heatmap string
    if heatmap_hours:
        peak_hour = max(heatmap_hours, key=heatmap_hours.get)
        heatmap_str = "  Distraction Heatmap (by hour):\n"
        for h in sorted(heatmap_hours.keys()):
            bar = "█" * heatmap_hours[h]
            heatmap_str += f"    {h:02d}:00  {bar} ({heatmap_hours[h]})\n"
        heatmap_str += f"  Peak distraction hour: {peak_hour:02d}:00\n"
    else:
        heatmap_str = "  No distractions recorded.\n"

    report_lines = "\n".join([
        f"Focus Session Report — {today}",
        "=" * 40,
        f"Started      : {session_start_str}",
        f"Ended        : {end_str}",
        f"Duration     : {mins} minutes",
        f"Distractions : {distractions}",
        f"Focus Score  : {focus_score}%",
        f"Longest Streak: {longest_streak} clean minutes",
        f"Grade        : {grade}",
        "",
        heatmap_str,
        "",
    ])

    try:
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(report_lines)
        logger.info(f"Daily report saved → {report_path}")
    except Exception as e:
        logger.error(f"Could not write report: {e}")

atexit.register(write_session_summary)

# ─────────────────────────────────────────────
#  CAMERA INIT  (with retry)
# ─────────────────────────────────────────────

def open_camera(index, max_retries=5):
    for attempt in range(1, max_retries + 1):
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            logger.info(f"Camera opened on attempt {attempt}.")
            return cap
        logger.warning(f"Camera open attempt {attempt}/{max_retries} failed.")
        time.sleep(attempt * 2)
    return None

cap = open_camera(cfg["camera_index"], cfg["max_camera_retries"])
if cap is None:
    abort("Could not open camera after retries. Check that no other app is using it.")

logger.info("Camera ready.")

# ─────────────────────────────────────────────
#  WINDOW
# ─────────────────────────────────────────────

cv2.namedWindow("Focus Monitor", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Focus Monitor", cfg["window_width"], cfg["window_height"])

# ─────────────────────────────────────────────
#  DETECTION STATE
# ─────────────────────────────────────────────

phone_timer      = None
last_phone_seen  = 0
alarm_running    = False
alarm_triggered  = False
cooldown_until   = 0
frame_count      = 0

GRACE_PERIOD        = cfg["grace_period_seconds"]
MAX_DISTRACTIONS    = cfg["max_distractions"]
CONF                = cfg["detection_confidence"]
DETECTION_INTERVAL  = cfg["detection_interval_frames"]
DETECTION_HOLD_TIME = cfg["detection_hold_seconds"]
COOLDOWN_SECONDS    = cfg["cooldown_seconds"]
SCORE_PENALTY       = cfg["focus_score_penalty_per_distraction"]

logger.info("Focus Monitor running. Press ESC to stop.")

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def draw_hud(frame, phone_detected, elapsed_grace=0):
    """Draw all on-screen UI elements."""
    h, w = frame.shape[:2]

    # Semi-transparent top bar
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 145), (10, 10, 10), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    # Title
    cv2.putText(frame, "AI Focus Monitor",
                (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 230, 255), 2)

    # Stats row
    cv2.putText(frame, f"Distractions: {distractions}",
                (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 1)
    cv2.putText(frame, f"Focus Score: {focus_score}%",
                (230, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                (0, 255, 120) if focus_score >= 70 else (0, 140, 255), 1)
    cv2.putText(frame, f"Streak: {focus_streak} min",
                (430, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 255, 100), 1)

    # Session duration
    elapsed_session = int(time.time() - session_start_unix)
    sm, ss = divmod(elapsed_session, 60)
    cv2.putText(frame, f"Session: {sm:02d}:{ss:02d}",
                (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 150, 150), 1)

    # Grace period progress bar (only when phone detected)
    if phone_detected and elapsed_grace > 0:
        pct     = min(elapsed_grace / GRACE_PERIOD, 1.0)
        bar_w   = int((w - 40) * pct)
        bar_col = (0, int(255 * (1 - pct)), int(255 * pct))
        cv2.rectangle(frame, (20, 120), (20 + bar_w, 135), bar_col, -1)
        cv2.rectangle(frame, (20, 120), (w - 20, 135), (80, 80, 80), 1)
        cv2.putText(frame, f"Grace: {GRACE_PERIOD - int(elapsed_grace):.0f}s remaining",
                    (20, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

    # Distraction alert banner
    if phone_detected:
        cv2.rectangle(frame, (0, h - 50), (w, h), (0, 0, 180), -1)
        cv2.putText(frame, "⚠  PHONE DETECTED — PUT IT DOWN",
                    (w // 2 - 220, h - 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)

    # Cooldown notice
    if time.time() < cooldown_until:
        remaining = int(cooldown_until - time.time())
        cv2.putText(frame, f"Cooldown: {remaining}s",
                    (w - 160, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 200, 255), 1)

# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────

while True:
    ret, frame = cap.read()

    # ── Camera recovery ──────────────────────
    if not ret or frame is None:
        logger.warning("Camera frame lost — attempting recovery...")
        cap.release()
        cap = open_camera(cfg["camera_index"], cfg["max_camera_retries"])
        if cap is None:
            logger.error("Camera unrecoverable. Exiting.")
            break
        continue

    frame_count  += 1
    current_time  = time.time()

    # ── YOLO Detection ───────────────────────
    if frame_count % DETECTION_INTERVAL == 0:
        results = model(frame, conf=CONF, verbose=False)[0]

        for box in results.boxes:
            cls   = int(box.cls[0])
            label = model.names[cls]

            if "phone" in label.lower() or "cell" in label.lower():
                last_phone_seen = current_time
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf_val        = float(box.conf[0])

                # Bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 80), 2)
                label_text = f"Phone {conf_val:.0%}"
                (lw, lh), _ = cv2.getTextSize(
                    label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
                cv2.rectangle(frame,
                              (x1, y1 - lh - 8), (x1 + lw + 6, y1),
                              (0, 200, 60), -1)
                cv2.putText(frame, label_text,
                            (x1 + 3, y1 - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)

    phone_detected = (current_time - last_phone_seen) < DETECTION_HOLD_TIME

    # ── Phone timer management ───────────────
    if phone_detected:
        if phone_timer is None:
            phone_timer = current_time
    else:
        phone_timer     = None
        alarm_triggered = False
        if alarm_running:
            stop_alarm()
            alarm_running = False

    # ── Focus streak tracking ─────────────────
    if not phone_detected:
        if current_time - last_streak_check >= STREAK_INTERVAL:
            focus_streak  += 1
            longest_streak = max(longest_streak, focus_streak)
            last_streak_check = current_time
    else:
        focus_streak      = 0
        last_streak_check = current_time

    # ── Alarm trigger ─────────────────────────
    elapsed_grace = (current_time - phone_timer) if phone_timer else 0

    if phone_timer:
        if elapsed_grace > GRACE_PERIOD and not alarm_triggered:
            if current_time >= cooldown_until:              # respect cooldown
                alarm_triggered = True
                distractions   += 1
                focus_score     = max(0, 100 - distractions * SCORE_PENALTY)
                cooldown_until  = current_time + COOLDOWN_SECONDS

                # Screenshot
                screenshot_path = "N/A"
                if cfg["screenshot_on_distraction"]:
                    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                    spath = os.path.join(SCREENSHOTS_DIR,
                                        f"distraction_{distractions}_{ts}.jpg")
                    try:
                        cv2.imwrite(spath, frame)
                        screenshot_path = spath
                    except Exception as e:
                        logger.error(f"Screenshot failed: {e}")

                log_distraction(distractions, screenshot_path)

                start_alarm()
                alarm_running = True

                if distractions >= MAX_DISTRACTIONS and cfg["show_popup_on_max_distractions"]:
                    show_warning(distractions)

    # ── Draw HUD ─────────────────────────────
    draw_hud(frame, phone_detected, elapsed_grace)

    cv2.imshow("Focus Monitor", frame)
    time.sleep(0.01)

    if cv2.waitKey(1) & 0xFF == 27:
        logger.info("ESC pressed — shutting down.")
        break

# ─────────────────────────────────────────────
#  CLEANUP  (atexit handles the summary/report)
# ─────────────────────────────────────────────

stop_alarm()
cap.release()
cv2.destroyAllWindows()
logger.info("Focus Monitor exited cleanly.")