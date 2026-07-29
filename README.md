# 🔴 ThreatLens

**Real-time weapon detection and public safety alerting system.**

Every camera becomes a first responder. ThreatLens turns standard security cameras into autonomous early warning endpoints — detecting weapons across multiple AI models, validating threats, and broadcasting alerts to civilians and authorities in seconds.

> Built at ['Sup Build 2026](https://supbuild.com) \
> Received Top 10 Finalist


---

## How It Works

```
ESP32-CAM captures frame
        │
        ▼
  Flask server (receives + queues)
        │
        ▼
  ┌─────────────────────────────────────┐
  │  STAGE 1: YOLOv8 (Roboflow)        │
  │  Object detection — weapons         │
  │  with bounding boxes + confidence   │
  └──────────────┬──────────────────────┘
                 │ weapon detected?
                 ▼
  ┌─────────────────────────────────────┐
  │  STAGE 2: OpenAI CLIP              │
  │  Zero-shot visual confirmation     │
  │  Crops bounding box, compares to   │
  │  threat vs non-threat descriptions │
  └──────────────┬──────────────────────┘
                 │ confirmed?
                 ▼
  ┌─────────────────────────────────────┐
  │  STAGE 3: SlowFast + Optical Flow  │
  │  Temporal motion analysis          │
  │  Scene context descriptors         │
  └──────────────┬──────────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────────┐
  │  ALERT: GPT-4.1-mini + Telegram    │
  │  AI-generated threat description   │
  │  Broadcast to nearby civilians     │
  └─────────────────────────────────────┘
```

---

## Features

- **Multi-model AI validation** — YOLOv8 detects, CLIP confirms, SlowFast + optical flow add motion context. No single model's error triggers a false alert.
- **ESP32-CAM hardware** — sub-$10 WiFi camera module. Frame-based capture reduces bandwidth by 60-80% vs video streaming.
- **AI-powered Telegram alerts** — GPT-4.1-mini vision generates factual threat descriptions (weapon type, person appearance, situation) and broadcasts to registered recipients.
- **Operator dashboard** — real-time web interface with detection bounding boxes, confidence scores, and chronological event log.
- **Authority map view** — geospatial overview of all monitored sites with pulsing threat indicators on a dark Leaflet map.
- **Human-in-the-loop** — Telegram recipients serve as a validation layer before escalation to law enforcement.
- **Privacy by design** — no facial recognition, no biometric data, no continuous recording. The camera detects danger, not individuals.
- **Persistent storage** — SQLite database preserves all events across restarts.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Edge hardware | ESP32-CAM (JPEG capture, WiFi HTTP POST) |
| Server | Python Flask (threaded, async-safe) |
| Database | SQLite3 (WAL mode) |
| Object detection | YOLOv8 via Roboflow serverless workflow |
| Visual confirmation | OpenAI CLIP (ViT-B/32) |
| Motion analysis | SlowFast R50 (Kinetics-400) + Farneback optical flow |
| Alert generation | GPT-4.1-mini (vision) |
| Alert delivery | Telegram Bot API |
| Dashboard | Vanilla HTML/JS/Canvas |
| Authority map | Leaflet.js + CartoDB dark tiles |
| Firmware | Arduino C++ (ESP32 HTTPClient) |

---

## Project Structure

```
threatlens/
├── server.py           # Flask server — receives frames, queues to DB, serves dashboards
├── detector.py         # AI pipeline — Roboflow + CLIP + descriptors
├── alerts.py           # Telegram alerting + GPT-4.1 threat descriptions
├── db.py               # Shared SQLite layer
├── feed_demo.py        # Push hardcoded demo images through the pipeline
├── send_frame.py       # Send individual frames to the server
├── dashboard.html      # Operator dashboard (live, served by Flask)
├── map.html            # Authority map view (live, served by Flask)
│
├── firmware/
│   ├── threatlens.ino  # ESP32-CAM firmware
│   └── idk.h           # WiFi + server config
│
├── demo_images/        # Hardcoded security cam images for demo
├── frames/             # Auto-created — received frames stored here
├── threatlens.db       # Auto-created — persistent event database
│
└── docs/               # Hosted website (GitHub Pages)
    ├── index.html      # Landing page
    ├── dashboard.html  # Static dashboard demo
    └── map.html        # Static authority map demo
```

---

## Getting Started

### Prerequisites

```bash
pip install flask inference-sdk transformers torch torchvision opencv-python pillow requests
```

### Setup

1. **Clone the repo**
```bash
git clone https://github.com/YOUR_REPO.git
cd threatlens
```

2. **Set your API keys** — create a `.env` or export them:
```bash
export ROBOFLOW_API_KEY="your_key"
export OPENAI_API_KEY="your_key"
export TELEGRAM_BOT_TOKEN="your_token"
```

3. **Run the system** — three terminals:
```bash
# Terminal 1 — start the server
python server.py

# Terminal 2 — start the detector (wait for "Detector ready")
python detector.py

# Terminal 3 — feed demo images
python feed_demo.py
```

4. **Open the dashboard** at `http://localhost:5000`
5. **Open the authority map** at `http://localhost:5000/map`

### ESP32-CAM Setup

1. Open `firmware/idk.h` and set your WiFi credentials and server IP
2. Flash `firmware/threatlens.ino` to your ESP32-CAM via Arduino IDE
3. The camera will automatically start posting frames to your server

---

## How the Demo Works

1. **Hardcoded images** — `feed_demo.py` pushes pre-selected security cam images through the full pipeline, showing detections on the dashboard
2. **Live ESP32 frames** — the camera captures real frames, posts them to the server, and threats are detected and alerted in real time
3. **Telegram alert** — when a weapon is confirmed, an AI-generated alert with the frame, weapon type, location, and description is broadcast to all registered recipients

---

## Architecture Decisions

| Decision | Why |
|---|---|
| Frames over video | 60-80% bandwidth reduction, independent processing per frame, scales to many cameras |
| Decoupled server + detector | Server responds instantly to ESP32, AI inference never blocks frame ingestion |
| CLIP as confirmation | Zero-shot, no retraining needed, catches YOLO false positives (phone mistaken for gun, ruler for knife) |
| SQLite WAL mode | Concurrent read/write from two processes without locking |
| Telegram as alert channel | Ubiquitous, supports images, no app install needed, built-in group broadcast |

---

## False Positive Mitigation

- **Sustained detection rule** — weapon must be detected across 20 consecutive frames (~1 second) before alerting
- **Forgiving counter** — allows up to 3 missed frames before resetting, preventing occlusion-related false resets
- **CLIP cross-validation** — semantic visual reasoning catches object misclassification (phone ≠ pistol)
- **Alert cooldown** — 60-second cooldown prevents duplicate alerts for the same incident
- **Human validation** — Telegram recipients verify AI assessment before escalating

---

## Demo pictures 

### ESP32 (OV3660 camera module)

<img width="1500" height="2000" alt="WhatsApp Image 2026-06-27 at 13 17 36" src="https://github.com/user-attachments/assets/c94b5a7c-1ab3-4abd-93b3-3d62cba5533b" />

### Custom 3d-printed casing 
<img width="1468" height="815" alt="Screenshot 2026-07-29 at 6 44 36 PM" src="https://github.com/user-attachments/assets/40c287da-29e8-4420-9636-5694157363d0" />

<img width="967" height="618" alt="Screenshot 2026-07-29 at 6 44 46 PM" src="https://github.com/user-attachments/assets/f2611ce7-349c-4ce4-a413-4c4003e40387" />

### Dashboard with live image detection

<img width="2938" height="1686" alt="WhatsApp Image 2026-06-27 at 14 29 56" src="https://github.com/user-attachments/assets/331aca27-988d-4450-baf3-77721e2f194b" />

### Telegram alert 

#### Live stream
<img width="715" height="747" alt="Screenshot 2026-07-29 at 6 38 44 PM" src="https://github.com/user-attachments/assets/98ccc66c-9cad-44fc-9478-2c5820a52f1b" />

#### Sample image

<img width="738" height="1600" alt="WhatsApp Image 2026-06-27 at 14 34 29" src="https://github.com/user-attachments/assets/ed393140-1695-43a3-9a18-225e1abe9c66" />

#### Control image 

<img width="1468" height="825" alt="Screenshot 2026-07-29 at 6 45 18 PM" src="https://github.com/user-attachments/assets/df8b1356-0da8-46c4-9c60-fd2799b54509" />

### Geolocation dashboard
<img width="1470" height="842" alt="Screenshot 2026-07-29 at 6 45 49 PM" src="https://github.com/user-attachments/assets/582f98f1-15bd-48c5-a3f8-311d0c45e5d9" />

## Privacy

- No facial recognition or biometric data collection
- No continuous video recording — individual frames only
- AI descriptions prohibit identification by name, race, nationality, religion, or exact age
- Camera footage processed locally — not stored on external cloud services
- The system detects danger, not individuals

---

## Future Roadmap

- **GPS-based geolocation** — dynamic location tagging and proximity-based civilian alerting
- **Multi-camera correlation** — track threat movement across cameras
- **Edge inference** — run detection on ESP32-S3 or Jetson Nano for offline operation
- **Emergency services API** — direct dispatch integration with pre-populated incident reports
- **Custom training pipeline** — in-app model fine-tuning for specific environments

---

## Team

| Member | Role |
|---|---|
| Aryaan | Detection pipeline, CLIP integration, system architecture |
| Anoushka | ESP32 firmware, YOLO training, hardware integration |
| Dhruv | Telegram alerts, LLM integration, dashboard |

---



