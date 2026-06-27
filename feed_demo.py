"""
Feed hard-coded demo images through the exact same path as live ESP32 frames.

Drop your security-cam demo .jpg files into a demo_images/ folder, then run:
    python feed_demo.py
or feed specific files:
    python feed_demo.py shot1.jpg shot2.jpg

Each image is POSTed to the running server, queued, and processed by detector.py
identically to a live frame — so the dashboard treats them the same way.
"""

import sys
import glob
import time

import requests

SERVER = "http://localhost:5000/upload"
DELAY = 0.8  # seconds between images, mimics the ESP32 capture interval


def main():
    files = sys.argv[1:] or sorted(glob.glob("demo_images/*.jpg"))
    if not files:
        print("No images. Put .jpg files in demo_images/ or pass paths as arguments.")
        return

    for path in files:
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            r = requests.post(
                SERVER,
                data=data,
                headers={"Content-Type": "image/jpeg", "X-Device-Id": "demo"},
                timeout=10,
            )
            print(f"{path:40s} -> {r.status_code} {r.json()}")
        except Exception as e:
            print(f"{path:40s} -> FAILED: {e}")
        time.sleep(DELAY)


if __name__ == "__main__":
    main()
