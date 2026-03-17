"""
focus_tray_app.py
AI Focus Monitor — System Tray Controller
------------------------------------------
Sits in the Windows system tray.
Lets users Start / Stop / Configure / View Reports
without touching any Python code.

Improvements over original:
  - Settings dialog edits config.json (no Notepad needed)
  - Status shows if monitor is running
  - "View Today's Report" menu item
  - Graceful process cleanup on exit
  - Icon color changes based on monitor state
"""

import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import subprocess
import threading
import tkinter as tk
from tkinter import simpledialog, messagebox, ttk
import os
import json
import sys

# ─────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
ICON_PATH   = os.path.join(BASE_DIR, "icons",   "icon.png")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
LOG_PATH    = os.path.join(BASE_DIR, "detection_log.txt")

# ─────────────────────────────────────────────
#  CONFIG HELPERS
# ─────────────────────────────────────────────

DEFAULT_CONFIG = {
    "grace_period_seconds":                  10,
    "max_distractions":                       5,
    "detection_confidence":                0.35,
    "cooldown_seconds":                      30,
    "camera_index":                           0,
    "sound_enabled":                       True,
    "screenshot_on_distraction":           True,
    "show_popup_on_max_distractions":      True,
}

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r") as f:
            d = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        merged.update(d)
        return merged
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(data):
    try:
        # Preserve keys we don't expose in the dialog
        existing = load_config()
        existing.update(data)
        with open(CONFIG_PATH, "w") as f:
            json.dump(existing, f, indent=4)
        return True
    except Exception as e:
        messagebox.showerror("Save Error", f"Could not save config:\n{e}")
        return False

# ─────────────────────────────────────────────
#  STATE
# ─────────────────────────────────────────────

focus_process = None

def is_running():
    return focus_process is not None and focus_process.poll() is None

# ─────────────────────────────────────────────
#  ICON HELPERS  (green when running, grey when idle)
# ─────────────────────────────────────────────

def make_icon_image(running=False):
    """Generate a simple icon if icon.png is missing, or load it."""
    if os.path.exists(ICON_PATH):
        try:
            img = Image.open(ICON_PATH).convert("RGBA")
            # Tint green when running
            if running:
                r, g, b, a = img.split()
                img = Image.merge("RGBA", (
                    r.point(lambda x: max(0, x - 80)),
                    g.point(lambda x: min(255, x + 60)),
                    b.point(lambda x: max(0, x - 80)),
                    a
                ))
            return img
        except Exception:
            pass

    # Fallback: draw a simple circle icon
    size  = 64
    img   = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw  = ImageDraw.Draw(img)
    color = (60, 200, 100) if running else (140, 140, 160)
    draw.ellipse([4, 4, size - 4, size - 4], fill=color)
    draw.text((18, 20), "FM", fill=(255, 255, 255))
    return img

# ─────────────────────────────────────────────
#  SETTINGS DIALOG
# ─────────────────────────────────────────────

def open_settings(icon, _):
    def _dialog():
        cfg = load_config()

        root = tk.Tk()
        root.title("Focus Monitor — Settings")
        root.geometry("400x420")
        root.resizable(False, False)
        root.configure(bg="#1e1e2e")

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TLabel",      background="#1e1e2e", foreground="#cdd6f4",
                        font=("Segoe UI", 10))
        style.configure("TEntry",      fieldbackground="#313244", foreground="#cdd6f4",
                        font=("Segoe UI", 10))
        style.configure("TCheckbutton",background="#1e1e2e", foreground="#cdd6f4",
                        font=("Segoe UI", 10))
        style.configure("TButton",     background="#89b4fa", foreground="#1e1e2e",
                        font=("Segoe UI", 10, "bold"))

        tk.Label(root, text="⚙  Focus Monitor Settings",
                 bg="#1e1e2e", fg="#89b4fa",
                 font=("Segoe UI", 13, "bold")).pack(pady=(18, 6))

        frame = tk.Frame(root, bg="#1e1e2e")
        frame.pack(padx=30, fill="x")

        fields = {}

        def add_field(label, key, row):
            tk.Label(frame, text=label,
                     bg="#1e1e2e", fg="#cdd6f4",
                     font=("Segoe UI", 10)).grid(
                         row=row, column=0, sticky="w", pady=6)
            var = tk.StringVar(value=str(cfg.get(key, "")))
            entry = tk.Entry(frame, textvariable=var,
                             bg="#313244", fg="#cdd6f4",
                             insertbackground="#cdd6f4",
                             relief="flat", font=("Segoe UI", 10), width=12)
            entry.grid(row=row, column=1, padx=(10, 0), sticky="w")
            fields[key] = var

        add_field("Grace period (seconds)",    "grace_period_seconds",   0)
        add_field("Max distractions",          "max_distractions",       1)
        add_field("Cooldown (seconds)",        "cooldown_seconds",       2)
        add_field("Detection confidence",      "detection_confidence",   3)
        add_field("Camera index",              "camera_index",           4)

        bool_fields = {}

        def add_check(label, key, row):
            var = tk.BooleanVar(value=bool(cfg.get(key, True)))
            cb  = tk.Checkbutton(frame, text=label, variable=var,
                                 bg="#1e1e2e", fg="#cdd6f4",
                                 selectcolor="#313244",
                                 activebackground="#1e1e2e",
                                 font=("Segoe UI", 10))
            cb.grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
            bool_fields[key] = var

        add_check("🔊  Sound enabled",              "sound_enabled",                 5)
        add_check("📷  Screenshot on distraction",  "screenshot_on_distraction",     6)
        add_check("🔔  Popup on max distractions",  "show_popup_on_max_distractions", 7)

        def on_save():
            new_cfg = {}
            type_map = {
                "grace_period_seconds": int,
                "max_distractions":     int,
                "cooldown_seconds":     int,
                "detection_confidence": float,
                "camera_index":         int,
            }
            for key, var in fields.items():
                try:
                    new_cfg[key] = type_map[key](var.get())
                except ValueError:
                    messagebox.showerror("Invalid Input",
                                         f"'{key}' has an invalid value.")
                    return
            for key, var in bool_fields.items():
                new_cfg[key] = var.get()

            if save_config(new_cfg):
                messagebox.showinfo("Saved", "Settings saved!\nRestart Focus Mode to apply.")
                root.destroy()

        tk.Button(root, text="Save Settings",
                  command=on_save,
                  bg="#89b4fa", fg="#1e1e2e",
                  font=("Segoe UI", 11, "bold"),
                  relief="flat", pady=8, padx=20,
                  cursor="hand2").pack(pady=20)

        root.mainloop()

    threading.Thread(target=_dialog, daemon=True).start()

# ─────────────────────────────────────────────
#  VIEW TODAY'S REPORT
# ─────────────────────────────────────────────

def view_report(icon, _):
    from datetime import date
    today       = date.today().strftime("%Y-%m-%d")
    report_path = os.path.join(REPORTS_DIR, f"{today}.txt")
    if os.path.exists(report_path):
        os.startfile(report_path)   # opens in Notepad on Windows
    else:
        def _msg():
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("No Report",
                                f"No report yet for today ({today}).\n"
                                "Run Focus Mode first.")
            root.destroy()
        threading.Thread(target=_msg, daemon=True).start()

def view_log(icon, _):
    if os.path.exists(LOG_PATH):
        os.startfile(LOG_PATH)
    else:
        def _msg():
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("No Log", "No detection log found yet.")
            root.destroy()
        threading.Thread(target=_msg, daemon=True).start()

# ─────────────────────────────────────────────
#  START / STOP
# ─────────────────────────────────────────────

def start_focus(icon, _):
    def run():
        global focus_process

        if is_running():
            def _msg():
                root = tk.Tk()
                root.withdraw()
                messagebox.showinfo("Already Running",
                                    "Focus Mode is already active.")
                root.destroy()
            threading.Thread(target=_msg, daemon=True).start()
            return

        cfg            = load_config()
        script_path    = os.path.join(BASE_DIR, "focus_monitor.py")
        python_exe     = sys.executable

        focus_process = subprocess.Popen(
            [python_exe, script_path,
             str(cfg["grace_period_seconds"]),
             str(cfg["max_distractions"])]
        )
        print(f"[Tray] Focus Mode started (PID {focus_process.pid})")

        # Update icon to green
        icon.icon  = make_icon_image(running=True)
        icon.title = "Focus Monitor — Active"

    threading.Thread(target=run, daemon=True).start()


def stop_focus(icon, _):
    global focus_process

    if focus_process:
        focus_process.terminate()
        focus_process = None
        print("[Tray] Focus Mode stopped.")

    icon.icon  = make_icon_image(running=False)
    icon.title = "Focus Monitor"


def exit_app(icon, _):
    stop_focus(icon, _)
    icon.stop()

# ─────────────────────────────────────────────
#  TRAY MENU
# ─────────────────────────────────────────────

def build_menu():
    return (
        item("▶  Start Focus Mode",   start_focus),
        item("⏹  Stop Focus Mode",    stop_focus),
        pystray.Menu.SEPARATOR,
        item("⚙  Settings",           open_settings),
        item("📄  Today's Report",    view_report),
        item("📋  View Full Log",     view_log),
        pystray.Menu.SEPARATOR,
        item("✖  Exit",               exit_app),
    )

image = make_icon_image(running=False)

tray_icon = pystray.Icon(
    "FocusMonitor",
    image,
    "Focus Monitor",
    build_menu()
)

print("[Tray] Focus Monitor tray app started.")
tray_icon.run()