
import os
import time

import cv2
import numpy as np
import torch
from collections import deque
from PIL import Image

from inference_sdk import InferenceHTTPClient
from transformers import CLIPProcessor, CLIPModel

import db

# ======================================================================
# CONFIG
# ======================================================================
CAPTURE_DIR = "frames"
POLL_INTERVAL = 0.4          # seconds between DB checks for new frames

# --- Roboflow (primary detector) ---
ROBOFLOW_API_KEY = os.environ.get("ROBOFLOW_API_KEY", "enter-key")
API_URL = "https://serverless.roboflow.com"
WORKSPACE_NAME = "aryaan-rizvi"
WORKFLOW_ID = "find-rifle-man-and-others"
WEAPON_CLASSES = {"guns", "gun", "knife", "rifle", "pistol"}
ROBOFLOW_CONF = 0.50

# --- CLIP (confirmation layer) ---
CLIP_LABELS = [
    "a hand gripping a knife or blade",
    "a person aiming or holding a gun or pistol",
    "someone holding a weapon in a threatening way",
    "a person with both hands clearly empty",
    "a person holding a rectangular phone or laptop",
    "a person not holding or engaging in any violent activity",
]
CLIP_THREAT_INDICES = {0, 1, 2}
CLIP_THRESHOLD = 0.35
CLIP_AS_HARD_GATE = False     # see header note

# --- Descriptors (context only, never gate the decision) ---
ENABLE_DESCRIPTORS = True     # master switch for optical flow + SlowFast
LOAD_SLOWFAST = True          # load the model at startup (shows in console, available)
RUN_SLOWFAST = False          # actually invoke it per danger event.
                              # Keep False for the live demo — SlowFast on CPU
                              # takes ~30-60s and would stall the stream.
                              # Optical flow still runs (it's fast).
DESCRIPTOR_BUFFER = 32        # recent frames kept for temporal descriptors

# ======================================================================
# MODEL LOADING
# ======================================================================
print("Loading CLIP...")
clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
clip_model.eval()

print("Connecting Roboflow client...")
rf_client = InferenceHTTPClient(api_url=API_URL, api_key=ROBOFLOW_API_KEY)

slowfast_model = None
KINETICS_CLASSES = {}
if ENABLE_DESCRIPTORS and LOAD_SLOWFAST:
    print("Loading SlowFast (descriptor model)...")
    try:
        slowfast_model = torch.hub.load(
            "facebookresearch/pytorchvideo", "slowfast_r50", pretrained=True
        )
        slowfast_model.eval()
        import requests
        kr = requests.get(
            "https://dl.fbaipublicfiles.com/pyslowfast/dataset/class_names/"
            "kinetics_classnames.json"
        ).json()
        KINETICS_CLASSES = {v: k for k, v in kr.items()}
    except Exception as e:
        print("  SlowFast load failed, continuing without it:", e)
        slowfast_model = None

# Rolling buffer of recent frame arrays — gives the temporal descriptors
# something to work with even though frames arrive one at a time.
recent_frames = deque(maxlen=DESCRIPTOR_BUFFER)

print("Detector ready.\n")


# ======================================================================
# STAGE 1 — ROBOFLOW
# ======================================================================
def run_roboflow(image_path):
    """Call the Roboflow workflow, return (image_meta, [detections])."""
    result = rf_client.run_workflow(
        workspace_name=WORKSPACE_NAME,
        workflow_id=WORKFLOW_ID,
        images={"image": image_path},
        use_cache=True,
    )
    block = result[0]
    preds_block = block.get("predictions", block)
    if isinstance(preds_block, dict):
        img_meta = preds_block.get("image", {})
        raw = preds_block.get("predictions", [])
    else:
        img_meta, raw = {}, []

    dets = []
    for d in raw:
        conf = d.get("confidence", 0)
        if conf < ROBOFLOW_CONF:
            continue
        w, h = d["width"], d["height"]
        dets.append({
            "label": d.get("class", "?"),
            "confidence": round(float(conf), 3),
            "x_min": d["x"] - w / 2,
            "y_min": d["y"] - h / 2,
            "x_max": d["x"] + w / 2,
            "y_max": d["y"] + h / 2,
        })
    return img_meta, dets


# ======================================================================
# STAGE 2 — CLIP
# ======================================================================
def clip_confirm(frame_bgr, box):
    """Crop the Roboflow box and ask CLIP if it looks like a weapon."""
    x1, y1 = max(0, int(box["x_min"])), max(0, int(box["y_min"]))
    x2, y2 = int(box["x_max"]), int(box["y_max"])
    crop = frame_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return False, None, 0.0

    pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
    inputs = clip_processor(text=CLIP_LABELS, images=pil,
                            return_tensors="pt", padding=True)
    with torch.no_grad():
        probs = clip_model(**inputs).logits_per_image.softmax(dim=1)[0]

    top = probs.argmax().item()
    p = float(probs[top].item())
    confirmed = top in CLIP_THREAT_INDICES and p > CLIP_THRESHOLD
    return confirmed, CLIP_LABELS[top], round(p, 3)


# ======================================================================
# STAGE 3 — DESCRIPTORS (context only)
# ======================================================================

def describe_motion(frames_bgr):
    """Average optical-flow magnitude across recent frames. Returns a float."""
    if len(frames_bgr) < 2:
        return None

    # Resize every frame to a common size so optical flow can compare them.
    # Different cameras/images have different dimensions otherwise.
    TARGET = (320, 240)
    greys = []
    for f in frames_bgr:
        resized = cv2.resize(f, TARGET)
        greys.append(cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY))

    mags = []
    for i in range(1, len(greys)):
        flow = cv2.calcOpticalFlowFarneback(
            greys[i - 1], greys[i], None, 0.5, 3, 15, 3, 5, 1.2, 0
        )
        m, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        mags.append(float(m.mean()))
    return round(sum(mags) / len(mags), 3)

def describe_action(frames_bgr):
    """SlowFast top action label. Returns {'action', 'score'} or None."""
    if slowfast_model is None or not RUN_SLOWFAST or len(frames_bgr) < 8:
        return None

    FAST = 32
    idx = np.linspace(0, len(frames_bgr) - 1, FAST).astype(int)
    sel = [frames_bgr[i] for i in idx]

    rgb = [cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in sel]
    t = torch.from_numpy(np.stack(rgb)).float() / 255.0
    t = t.permute(3, 0, 1, 2)

    # resize short side to 256
    C, T, H, W = t.shape
    scale = 256 / min(H, W)
    nH, nW = int(H * scale), int(W * scale)
    res = []
    for i in range(T):
        fn = (t[:, i].permute(1, 2, 0).numpy() * 255).astype(np.uint8)
        res.append(cv2.resize(fn, (nW, nH)))
    t = torch.from_numpy(np.stack(res)).float() / 255.0
    t = t.permute(3, 0, 1, 2)

    # centre crop 224
    C, T, H, W = t.shape
    sh, sw = (H - 224) // 2, (W - 224) // 2
    t = t[:, :, sh:sh + 224, sw:sw + 224]

    mean = torch.tensor([0.45, 0.45, 0.45]).view(3, 1, 1, 1)
    std = torch.tensor([0.225, 0.225, 0.225]).view(3, 1, 1, 1)
    t = (t - mean) / std
    t = t.unsqueeze(0)

    slow_idx = torch.linspace(0, FAST - 1, FAST // 4).long()
    slow = t[:, :, slow_idx, :, :]

    try:
        with torch.no_grad():
            probs = torch.softmax(slowfast_model([slow, t]), dim=1)[0]
        i = probs.argmax().item()
        return {"action": KINETICS_CLASSES.get(i, str(i)),
                "score": round(float(probs[i].item()), 3)}
    except Exception as e:
        print("  SlowFast inference error:", e)
        return None


# ======================================================================
# PROCESS ONE FRAME
# ======================================================================
def process(event):
    fpath = os.path.join(CAPTURE_DIR, event["filename"])
    frame = cv2.imread(fpath)
    if frame is None:
        print("  Could not read", fpath)
        db.mark_error(event["id"])
        return

    recent_frames.append(frame.copy())

    # Stage 1
    img_meta, dets = run_roboflow(fpath)

    # Stage 2 — CLIP on each weapon box
    clip_confirmed_any = False
    for d in dets:
        if d["label"].lower() in WEAPON_CLASSES:
            ok, label, p = clip_confirm(frame, d)
            d["clip_confirmed"] = ok
            d["clip_label"] = label
            d["clip_conf"] = p
            if ok:
                clip_confirmed_any = True

    weapon_found = any(d["label"].lower() in WEAPON_CLASSES for d in dets)

    # Danger decision
    if CLIP_AS_HARD_GATE:
        danger = weapon_found and clip_confirmed_any
    else:
        danger = weapon_found

    # Stage 3 — descriptors, only worth computing when something flagged
    descriptor = {}
    if ENABLE_DESCRIPTORS and danger:
        descriptor["motion"] = describe_motion(list(recent_frames))
        descriptor["action"] = describe_action(list(recent_frames))

    h, w = frame.shape[:2]
    db.mark_done(
        event["id"], danger, dets, descriptor,
        img_meta.get("width", w), img_meta.get("height", h),
    )

    status = "DANGER" if danger else "clear"
    extra = f" | desc={descriptor}" if descriptor else ""
    print(f"[{event['time_label']}] {status} | {len(dets)} detection(s){extra}")
    if danger:
      try:
        from alerts import send_weapon_alert
        send_weapon_alert(fpath)
      except Exception as e:
        print("  Alert failed:", e)
# ======================================================================
# MAIN LOOP
# ======================================================================
def main():
    db.init_db()  # idempotent — safe if detector starts before server
    print("Watching for queued frames... (Ctrl+C to stop)\n")
    while True:
        for ev in db.fetch_pending():
            try:
                process(ev)
            except Exception as e:
                print("  process error:", e)
                db.mark_error(ev["id"])
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
