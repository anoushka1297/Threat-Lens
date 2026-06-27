"""
ThreatLens server (lightweight).

Responsibilities ONLY:
  - accept frames (ESP32 raw POST or multipart) and save to frames/
  - queue each frame as a 'pending' row in SQLite
  - serve the dashboard and the /api/events feed it polls
  - serve saved frame images

It does NOT run any AI. That happens in detector.py, so this endpoint stays
instant and the ESP32 never waits on Roboflow/CLIP. Run this and detector.py
side by side in two terminals.
"""

import os
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
import db
import time

SITES = {
    "house_a": {
        "name": "House A",
        "address": "Blk 168 Punggol Field",
        "lat": 1.40280,
        "lng": 103.90920,
    },
    "house_b": {
        "name": "House B",
        "address": "Blk 271 Punggol Way",
        "lat": 1.40510,
        "lng": 103.91230,
    },
}
DEFAULT_SITE = "house_a"
ALERT_WINDOW_SECONDS = 30

CAPTURE_DIR = "frames"
os.makedirs(CAPTURE_DIR, exist_ok=True)
db.init_db()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB safety cap


@app.route("/upload", methods=["POST"])
def upload():
    """ESP32 (raw JPEG body) or demo feeder (also raw) posts here."""
    if request.files:                       # multipart, just in case
        file = next(iter(request.files.values()))
        img_bytes = file.read()
    else:                                   # raw body — what our firmware sends
        img_bytes = request.get_data()

    if not img_bytes:
        return jsonify({"error": "no image received"}), 400

    source = request.headers.get("X-Device-Id", "esp32")
    ts = datetime.now()
    event_id = ts.strftime("%Y%m%d_%H%M%S_%f")
    fname = event_id + ".jpg"

    with open(os.path.join(CAPTURE_DIR, fname), "wb") as f:
        f.write(img_bytes)

    # Queue it. detector.py will pick it up within a fraction of a second.
    db.add_pending(event_id, fname, source)

    # Respond instantly — no waiting on detection.
    return jsonify({"status": "queued", "id": event_id})


@app.route("/captures/<path:fname>")
def captures(fname):
    return send_from_directory(CAPTURE_DIR, fname)


@app.route("/api/events")
def api_events():
    """Shape DB rows into exactly what dashboard.html expects."""
    out = []
    for e in db.get_events():
        out.append({
            "id": e["id"],
            "image_url": f"/captures/{e['filename']}",
            "time": e["time_label"],
            "img_width": e["img_width"],
            "img_height": e["img_height"],
            "detections": e["detections"],
            "danger": bool(e["danger"]),
            "descriptor": e["descriptor"],   # optional context, dashboard can ignore
            "summary": e.get("summary"),
        })
    return jsonify(out)


@app.route("/")
def index():
    return send_from_directory(".", "dashboard.html")

@app.route("/api/map")
def api_map():
    now = time.time()
    events = db.get_events(limit=50)
    result = []
    for sid, site in SITES.items():
        last = next(
            (e for e in events if e.get("source") == sid and e["danger"]),
            None,
        )
        active = bool(last and now - datetime.fromisoformat(last["created_at"]).timestamp() <= ALERT_WINDOW_SECONDS)
        result.append({
            "site_id": sid,
            "name": site["name"],
            "address": site["address"],
            "lat": site["lat"],
            "lng": site["lng"],
            "active": active,
            "last_time": last["time_label"] if last else None,
            "last_image": f"/captures/{last['filename']}" if last else None,
        })
    return jsonify(result)

@app.route("/map")
def map_page():
    return send_from_directory(".", "map.html")

if __name__ == "__main__":
    # debug=False on purpose — debug mode caused the ESP32 connection refusals.
    # threaded=True keeps the dashboard responsive while frames pour in.
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
