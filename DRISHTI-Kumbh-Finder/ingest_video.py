"""
ingest_video.py — feed a local video into the DRISHTI face/sighting backend.

Samples frames from a video (e.g. sample_footage/street_crossing.webm), and for
each sampled frame calls backend_reference.py's POST /ingest-frame so the faces
become searchable CCTV *sightings* for the ⑥ CCTV trace tab (Track A).

Usage:
    # 1) start the face backend in another shell
    pip install -r requirements-face.txt && python3 backend_reference.py

    # 2) index the sample footage as camera Z30-C12 in Zone Area 30 at ~09:00
    python3 ingest_video.py sample_footage/street_crossing.webm \
        --camera Z30-C12 --zone "Zone Area 30" --start 09:00 --every 1.0

    # optional: also dump sampled frames to disk so you can pick a query photo
    python3 ingest_video.py sample_footage/street_crossing.webm --save-frames frames/

Then in the app's ⑥ CCTV trace tab: set "Photo contains the person", upload one
of the saved frames (a clear face), pick the same last-seen zone/time, and search
— Track A now runs on real face embeddings from this video.

Only dependency beyond the standard library is OpenCV (already in
requirements-face.txt). The backend upload uses urllib — no `requests` needed.
"""
import argparse
import json
import os
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
    """Minimal multipart/form-data POST (no third-party deps)."""
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
    ap = argparse.ArgumentParser(description="Ingest a video into the DRISHTI face backend.")
    ap.add_argument("video")
    ap.add_argument("--backend", default="http://localhost:8100")
    ap.add_argument("--camera", default="Z30-C12")
    ap.add_argument("--zone", default="Zone Area 30")
    ap.add_argument("--start", default="09:00", help="last-seen-style clock time the clip starts at")
    ap.add_argument("--every", type=float, default=1.0, help="sample one frame every N seconds")
    ap.add_argument("--save-frames", default=None, help="also write sampled frames to this dir")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"Could not open {args.video} (OpenCV may lack a WebM/ffmpeg backend).")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps * args.every)))
    if args.save_frames:
        os.makedirs(args.save_frames, exist_ok=True)

    start_min = int(args.start.split(":")[0]) * 60 + int(args.start.split(":")[1])
    idx = sampled = faces = 0
    best = (-1.0, None)   # (max face-detection score, frame path) — the clearest query candidate
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            ts = to_hhmm(start_min + (idx / fps) / 60.0)
            ok2, buf = cv2.imencode(".jpg", frame)
            if ok2:
                fp = None
                if args.save_frames:
                    fp = os.path.join(args.save_frames, f"frame_{sampled:03d}.jpg")
                    cv2.imwrite(fp, frame)
                try:
                    resp = post_frame(args.backend + "/ingest-frame", buf.tobytes(),
                                      {"camera_id": args.camera, "zone": args.zone, "ts": ts})
                    faces += resp.get("faces_indexed", 0)
                    if fp and resp.get("max_det", 0) > best[0]:
                        best = (resp["max_det"], fp)
                except Exception as e:
                    print(f"[warn] frame {sampled} upload failed: {e}")
                sampled += 1
        idx += 1
    cap.release()
    print(f"sampled {sampled} frames from {args.video} → {faces} faces indexed as "
          f"{args.camera} / {args.zone}. Total sightings: see {args.backend}/sightings")
    if best[1]:
        print(f"RECOMMENDED QUERY PHOTO: {best[1]} (clearest face, detection score {best[0]:.2f})")
    elif faces == 0:
        print("No faces were detected in the sampled frames — try --every 0.5 for denser sampling.")


if __name__ == "__main__":
    main()
