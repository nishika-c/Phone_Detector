"""
view_report.py
AI Focus Monitor — Log Viewer & Analytics
------------------------------------------
Run this script directly to see a full summary
of your focus history, weekly trends, and best days.

Usage:
    python view_report.py              (shows everything)
    python view_report.py --week       (last 7 days only)
    python view_report.py --today      (today only)
"""

import os
import re
import sys
import json
from collections import defaultdict
from datetime import datetime, date, timedelta

# ─────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
LOG_PATH    = os.path.join(BASE_DIR, "detection_log.txt")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

# ─────────────────────────────────────────────
#  PARSE LOG
# ─────────────────────────────────────────────

def parse_log():
    """
    Returns:
        daily   : dict  { "YYYY-MM-DD" -> [list of (time_str, distraction_num)] }
        sessions: list  of session summary strings
    """
    daily    = defaultdict(list)
    sessions = []

    if not os.path.exists(LOG_PATH):
        return daily, sessions

    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()

        # New-format: [2026-03-17 14:22:10] [INFO] Distraction #3 | ...
        m = re.search(
            r"\[?(\d{4}-\d{2}-\d{2})\s(\d{2}:\d{2}:\d{2})\]?"
            r".*?Distraction\s+#(\d+)",
            line, re.IGNORECASE
        )
        if m:
            day  = m.group(1)
            t    = m.group(2)
            num  = int(m.group(3))
            daily[day].append((t, num))
            continue

        # Session summary lines
        if "SESSION SUMMARY" in line or "FINAL SCORE" in line.upper():
            sessions.append(line)

    return daily, sessions

# ─────────────────────────────────────────────
#  DISPLAY HELPERS
# ─────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
GREY   = "\033[90m"
WHITE  = "\033[97m"

def grade(count):
    if count == 0:   return GREEN  + "Excellent" + RESET
    if count <= 2:   return GREEN  + "Good"      + RESET
    if count <= 5:   return YELLOW + "Fair"      + RESET
    return RED + "Needs work" + RESET

def score(count):
    return max(0, 100 - count * 10)

def bar(value, max_val, width=20):
    if max_val == 0:
        return "░" * width
    filled = int((value / max_val) * width)
    return "█" * filled + "░" * (width - filled)

def separator(char="─", width=58):
    print(GREY + char * width + RESET)

def header(text):
    separator("═")
    print(BOLD + CYAN + f"  {text}" + RESET)
    separator("═")

# ─────────────────────────────────────────────
#  VIEWS
# ─────────────────────────────────────────────

def show_day(day_str, events):
    count  = len(events)
    s      = score(count)
    g      = grade(count)
    print(f"\n  {BOLD}{WHITE}{day_str}{RESET}   "
          f"Distractions: {BOLD}{count}{RESET}   "
          f"Score: {BOLD}{s}%{RESET}   {g}")
    if events:
        for (t, n) in sorted(events, key=lambda x: x[0]):
            print(GREY + f"    {t}  →  Distraction #{n}" + RESET)

def show_weekly_chart(daily):
    today   = date.today()
    week    = [(today - timedelta(days=i)).strftime("%Y-%m-%d")
               for i in range(6, -1, -1)]
    counts  = [len(daily.get(d, [])) for d in week]
    max_c   = max(counts) if any(counts) else 1

    separator()
    print(f"\n  {BOLD}Last 7 Days — Distraction Chart{RESET}\n")

    for d, c in zip(week, counts):
        day_label = datetime.strptime(d, "%Y-%m-%d").strftime("%a %d")
        col = GREEN if c == 0 else YELLOW if c <= 3 else RED
        b   = bar(c, max_c, 24)
        print(f"  {GREY}{day_label}{RESET}  {col}{b}{RESET}  {c}")

    weekly_total = sum(counts)
    weekly_avg   = weekly_total / 7
    print(f"\n  Weekly total: {BOLD}{weekly_total}{RESET}   "
          f"Daily avg: {BOLD}{weekly_avg:.1f}{RESET}")

def show_all_time(daily):
    if not daily:
        print(f"\n  {GREY}No data recorded yet.{RESET}")
        return

    all_counts = [len(v) for v in daily.values()]
    best_day   = min(daily, key=lambda d: len(daily[d]))
    worst_day  = max(daily, key=lambda d: len(daily[d]))
    total      = sum(all_counts)
    avg        = total / len(all_counts)

    separator()
    print(f"\n  {BOLD}All-Time Stats{RESET}\n")
    print(f"  Total sessions tracked : {len(daily)} days")
    print(f"  Total distractions     : {total}")
    print(f"  Daily average          : {avg:.1f}")
    print(f"  Best day               : {GREEN}{best_day}{RESET}  ({len(daily[best_day])} distractions)")
    print(f"  Worst day              : {RED}{worst_day}{RESET}  ({len(daily[worst_day])} distractions)")
    print(f"  Current streak goal    : Put phone down for entire sessions!")

def show_report_files():
    if not os.path.exists(REPORTS_DIR):
        return
    files = sorted([f for f in os.listdir(REPORTS_DIR) if f.endswith(".txt")],
                   reverse=True)
    if not files:
        return
    separator()
    print(f"\n  {BOLD}Saved Report Files{RESET}\n")
    for f in files[:7]:
        path = os.path.join(REPORTS_DIR, f)
        size = os.path.getsize(path)
        print(f"  {GREY}{f}{RESET}   ({size} bytes)   → {GREY}{path}{RESET}")

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    mode = "--all"
    if "--week"  in sys.argv: mode = "--week"
    if "--today" in sys.argv: mode = "--today"

    daily, sessions = parse_log()

    header("AI FOCUS MONITOR — LOG VIEWER")

    if not daily:
        print(f"\n  {YELLOW}No distraction data found yet.{RESET}")
        print(f"  Run Focus Monitor and come back after a session!\n")
    else:
        if mode == "--today":
            today = date.today().strftime("%Y-%m-%d")
            if today in daily:
                show_day(today, daily[today])
            else:
                print(f"\n  {GREEN}No distractions recorded today. Great work!{RESET}")

        elif mode == "--week":
            today = date.today()
            for i in range(6, -1, -1):
                d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                if d in daily:
                    show_day(d, daily[d])
            show_weekly_chart(daily)

        else:  # --all
            for day in sorted(daily.keys(), reverse=True)[:14]:
                show_day(day, daily[day])
            show_weekly_chart(daily)
            show_all_time(daily)
            show_report_files()

    separator("═")
    print()

if __name__ == "__main__":
    main()
    input("Press Enter to close...")