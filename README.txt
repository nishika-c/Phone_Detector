# 🎯 AI Focus Monitor

A real-time phone-detection focus tool that uses your webcam and YOLOv8 to catch you picking up your phone — and alarms you back to work.

Built with Python, OpenCV, YOLOv8, and Tkinter. Runs entirely on your laptop, no cloud required.

---

## Features

- **Live phone detection** via YOLOv8 + webcam
- **Grace period** before alarm fires (configurable)
- **Cooldown system** — no alarm spam
- **Session tracking** with start/end summaries
- **Focus streak counter** — rewards clean minutes
- **Daily reports** saved to `/reports/`
- **Distraction heatmap** — see your worst hours
- **System tray app** — runs silently in background
- **Settings dialog** — change all config via GUI
- **Log viewer** with weekly charts

---

## Project Structure

```
Phone_Detector/
├── focus_monitor.py      ← Core detection engine
├── focus_tray_app.py     ← System tray controller
├── view_report.py        ← Log viewer & analytics
├── config.json           ← All user settings (edit freely)
├── requirements.txt      ← Python dependencies
├── models/
│   └── yolov8s.pt        ← YOLOv8 model (download separately)
├── sounds/
│   └── loud_alrm.mp3     ← Alarm sound
├── icons/
│   └── icon.png          ← Tray icon
├── screenshots/          ← Auto-saved distraction screenshots
└── reports/              ← Daily focus reports (auto-generated)
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/Phone_Detector.git
cd Phone_Detector
```

### 2. Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Download the YOLOv8 model

```bash
python -c "from ultralytics import YOLO; YOLO('yolov8s.pt')"
```
Then move `yolov8s.pt` into the `models/` folder.

### 5. Add your alarm sound

Place any `.mp3` file named `loud_alrm.mp3` inside the `sounds/` folder.

### 6. Run

```bash
# Option A: Start the tray app (recommended)
python focus_tray_app.py

# Option B: Run the monitor directly
python focus_monitor.py

# Option C: View your focus history
python view_report.py
python view_report.py --week
python view_report.py --today
```

---

## Configuration

Edit `config.json` to change any setting — no code editing needed:

| Key | Default | Description |
|-----|---------|-------------|
| `grace_period_seconds` | 10 | Seconds before alarm fires |
| `max_distractions` | 5 | Popup warning threshold |
| `cooldown_seconds` | 30 | Minimum time between alarms |
| `detection_confidence` | 0.35 | YOLOv8 confidence threshold |
| `camera_index` | 0 | Webcam index (0 = default) |
| `sound_enabled` | true | Enable/disable alarm sound |
| `screenshot_on_distraction` | true | Save screenshot each time |

Or use the **Settings** option in the tray menu for a GUI editor.

---

## Roadmap

- [ ] Daily email/notification summary
- [ ] Multiple distraction types (book, tablet)
- [ ] Pomodoro timer integration
- [ ] Dashboard web UI (local HTML)
- [ ] Exportable CSV reports

---

## Tech Stack

- [YOLOv8](https://github.com/ultralytics/ultralytics) — object detection
- [OpenCV](https://opencv.org/) — webcam + frame processing
- [Pygame](https://www.pygame.org/) — alarm audio
- [Pystray](https://github.com/moses-palmer/pystray) — system tray
- [Tkinter](https://docs.python.org/3/library/tkinter.html) — settings GUI

---

## License

MIT License — free to use, modify, and share.