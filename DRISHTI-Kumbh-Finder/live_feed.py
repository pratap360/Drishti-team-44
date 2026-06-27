"""
live_feed.py — stream a crowd video into the DRISHTI backend as a *live* camera.

Unlike ingest_video.py (one-shot batch), this paces frames to wall-clock time and
loops forever, so the backend's Qdrant `sightings` collection fills in real time —
the demo's "live CCTV feed". Each time the clip loops it advances to the next zone
in --zones and bumps the simulated clock, so the same recurring faces appear to
move across zones (giving POST /track a multi-hop trajectory to follow).

Usage (after `python3 backend_reference.py` is up):
    python3 live_feed.py sample_footage/street_crossing.webm \
        --zones "Zone Area 30,Zone Area 31,Zone Area 10" --fps 3 --speed 4

  --fps    frames ingested per wall-clock second
  --speed  >1 fast-forwards the simulated clock (4 = 1 real sec -> 4 sim sec)
  --zones  comma list; the feed moves to the next zone each time the clip loops
  --camera-prefix  camera id prefix (per-zone cam id = "<prefix>-<zoneNumber>")

Stop with Ctrl-C. Only dependency beyond stdlib is OpenCV (in requirements-face.txt).
"""
import argparse
import json
import re
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


def cam_for_zone(prefix: str, zone: str) -> str:
    n = re.search(r"\d+", zone)
    return f"{prefix}-{n.group()}" if n else f"{prefix}-0"


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
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser(description="Stream a video into DRISHTI as a live camera.")
    ap.add_argument("video")
    ap.add_argument("--backend", default="http://localhost:8100")
    ap.add_argument("--zones",
                    default="Zone Area 30,Zone Area 31,Zone Area 21,Zone Area 29,Zone Area 23,Zone Area 22")
    ap.add_argument("--camera-prefix", default="LIVE")
    ap.add_argument("--start", default="09:00")
    ap.add_argument("--fps", type=float, default=3.0, help="frames ingested per wall-clock second")
    ap.add_argument("--speed", type=float, default=4.0, help="simulated-clock fast-forward factor")
    args = ap.parse_args()

    zones = [z.strip() for z in args.zones.split(",") if z.strip()]
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"Could not open {args.video} (OpenCV may lack a WebM/ffmpeg backend).")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(src_fps / args.fps)))
    period = 1.0 / args.fps                       # wall-clock seconds between ingests

    clock = float(int(args.start.split(":")[0]) * 60 + int(args.start.split(":")[1]))
    zi = 0
    idx = total = faces = 0
    print(f"[live] streaming {args.video} -> {args.backend} | zones={zones} fps={args.fps} speed={args.speed}x")
    print("[live] Ctrl-C to stop.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:                            # clip ended -> loop, advance zone + clock
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                zi = (zi + 1) % len(zones)
                print(f"[live] --- loop; now feeding {zones[zi]} @ {to_hhmm(clock)} ---")
                continue
            idx += 1
            if idx % step:
                continue
            ok2, buf = cv2.imencode(".jpg", frame)
            if ok2:
                zone = zones[zi]
                fields = {"camera_id": cam_for_zone(args.camera_prefix, zone),
                          "zone": zone, "ts": to_hhmm(clock)}
                try:
                    resp = post_frame(args.backend + "/ingest-frame", buf.tobytes(), fields)
                    total += 1
                    faces += resp.get("faces_indexed", 0)
                    if total % 10 == 0:
                        print(f"[live] {fields['ts']} {zone}: {total} frames, {faces} faces, "
                              f"sightings={resp.get('total_sightings')}")
                except Exception as e:
                    print(f"[live] upload failed ({e}); is backend_reference.py running?")
                    time.sleep(1.0)
            clock += (step / src_fps) / 60.0 * args.speed   # advance simulated minutes
            time.sleep(period)
    except KeyboardInterrupt:
        print(f"\n[live] stopped after {total} frames / {faces} faces.")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
