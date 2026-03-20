# 🎯 AI Focus Monitor

A real-time AI-based focus monitoring system that detects mobile phone usage using your webcam and helps reduce distractions during study or work.

Built using Python, OpenCV, and YOLOv8, this system runs locally on your device with no cloud dependency.

---

## 💡 Overview

In today’s digital environment, constant phone usage reduces productivity.  
This project acts as a smart focus assistant that monitors user behavior and alerts them when distractions are detected.

It is designed for:
- Students
- Developers
- Remote workers
- Anyone aiming to improve focus

---

## ⚙️ Features

- 📷 Real-time phone detection using YOLOv8
- ⏱ Configurable grace period before alert
- 🔊 Alarm system for distraction control
- 📸 Automatic screenshot capture
- 📊 Distraction tracking and logging
- 🖥 System tray integration for background operation
- ⚙️ Custom settings via configuration file

---

## 🧠 Tech Stack

- Python  
- OpenCV  
- YOLOv8 (Ultralytics)  
- PyStray  
- Tkinter  
- Playsound  

---

## 📂 Project Structure
Phone_Detector/
├── focus_monitor.py
├── focus_tray_app.py
├── view_report.py
├── config.json
├── requirements.txt
├── models/
├── sounds/
├── icons/
├── screenshots/
└── reports/