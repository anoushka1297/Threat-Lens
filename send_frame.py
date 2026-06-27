"""
Send a single frame to the ThreatLens server.
Usage:
    python send_frame.py shot1.jpg
    python send_frame.py demo_images/shot1.jpg demo_images/shot2.jpg
"""
import sys
import requests

SERVER = "http://localhost:5000/upload"

def main():
    if len(sys.argv) < 2:
        print("usage: python send_frame.py <image.jpg> [image2.jpg ...]")
        return

    for image_path in sys.argv[1:]:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        resp = requests.post(
            SERVER,
            data=img_bytes,
            headers={
                "Content-Type": "image/jpeg",
                "X-Device-Id": "demo",
            },
            timeout=10,
        )
        print(f"{image_path} -> {resp.status_code} {resp.text[:200]}")

if __name__ == "__main__":
    main()
