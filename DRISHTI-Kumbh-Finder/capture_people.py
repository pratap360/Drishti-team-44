"""
capture_people.py — read an MP4 as a live stream, capture each person, and store
their image + attributes (gender / age / clothing colour / approx height) in Qdrant.

It paces frames to wall-clock time (like a live camera) and POSTs each to the
backend's /ingest-people, which detects people, extracts attributes, saves the
crop to captures/, and upserts the embedding + metadata + thumbnail into the
Qdrant `people` collection.

Usage (after `python3 backend_reference.py` is up):
    python3 capture_people.py 10924096-hd_1920_1080_30fps.mp4 \
        --camera CAM-CROWD --zone "Zone Area 30" --fps 3 --loop

  --fps   frames processed per wall-clock second (keep low; attribute extraction is heavy)
  --loop  restart the clip when it ends (continuous "live" stream)

Only dependency beyond stdlib is OpenCV (in requirements-face.txt).
"""
import argparse
import json
import time
import urllib.request
import uuid

try:
    import cv2
except ImportError:
    raise SystemExit("OpenCV missing — `pip install -r requirements-face.txt` first.")


def to_hhmm(total_min: float) -> str:
    m = int(round(total_min))
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def post_frame(url: str, jpg: bytes, fields: dict) -> dict:
    boundary = "----drishti" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                  "filename=\"frame.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n").encode())
    body = b"".join(parts) + jpg + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser(description="Stream an MP4 into DRISHTI, capturing people + attributes.")
    ap.add_argument("video")
    ap.add_argument("--backend", default="http://localhost:8100")
    ap.add_argument("--camera", default="CAM-CROWD")
    ap.add_argument("--zone", default="Zone Area 30")
    ap.add_argument("--start", default="09:00")
    ap.add_argument("--fps", type=float, default=3.0)
    ap.add_argument("--speed", type=float, default=4.0)
    ap.add_argument("--loop", action="store_true")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"Could not open {args.video}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(src_fps / args.fps)))
    clock = float(int(args.start.split(":")[0]) * 60 + int(args.start.split(":")[1]))
    idx = frames = people = 0
    print(f"[capture] {args.video} -> {args.backend}/ingest-people | {args.camera} / {args.zone}")
    print("[capture] Ctrl-C to stop.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                if args.loop:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break
            idx += 1
            if idx % step:
                continue
            ok2, buf = cv2.imencode(".jpg", frame)
            if ok2:
                try:
                    resp = post_frame(args.backend + "/ingest-people", buf.tobytes(),
                                      {"camera_id": args.camera, "zone": args.zone, "ts": to_hhmm(clock)})
                    frames += 1
                    people += resp.get("people_indexed", 0)
                    for p in resp.get("people", []):
                        print(f"  + {p.get('gender'):7} {p.get('age'):6} "
                              f"{p.get('upper_color')}/{p.get('lower_color'):6} {p.get('height')}")
                    if frames % 10 == 0:
                        print(f"[capture] {to_hhmm(clock)} {args.zone}: {frames} frames, "
                              f"{people} people stored (total={resp.get('total_people')})")
                except Exception as e:
                    print(f"[capture] upload failed ({e}); is backend_reference.py running?")
                    time.sleep(1.0)
            clock += (step / src_fps) / 60.0 * args.speed
            time.sleep(1.0 / args.fps)
    except KeyboardInterrupt:
        print(f"\n[capture] stopped after {frames} frames / {people} people stored.")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
