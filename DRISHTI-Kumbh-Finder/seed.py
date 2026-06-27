"""
seed.py — enroll a few sample missing persons into the Qdrant `persons` collection.

Each enrolled person needs a face photo. We use frames extracted from the sample
crowd video (run ingest_video.py / demo_setup.sh with --save-frames first) so the
watch-list has real face embeddings. Sends each to backend_reference.py POST /enroll;
the backend detects the clearest face, embeds it, and stores it in Qdrant.

Usage:
    python3 seed.py                       # auto-pick frames from ./frames
    python3 seed.py --frames-dir frames   # explicit dir
    python3 seed.py path/a.jpg "Asha Patil" path/b.jpg "Ramesh Kale"   # explicit pairs

Only stdlib is used (multipart upload via urllib).
"""
import argparse
import glob
import json
import os
import urllib.request
import uuid

# Sample missing-person details paired with the first auto-picked frames.
SAMPLE_PEOPLE = [
    {"name": "Asha Patil",   "age": "61-70", "gender": "Female", "zone": "Zone Area 30", "mobile": "+91 ••••••12"},
    {"name": "Ramesh Kale",  "age": "71-80", "gender": "Male",   "zone": "Zone Area 30", "mobile": "+91 ••••••47"},
    {"name": "Lakshmi Iyer", "age": "41-60", "gender": "Female", "zone": "Zone Area 31", "mobile": ""},
]


def post_enroll(url: str, jpg_path: str, fields: dict) -> dict:
    boundary = "----drishti" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                  f"filename=\"{os.path.basename(jpg_path)}\"\r\nContent-Type: image/jpeg\r\n\r\n").encode())
    body = b"".join(parts) + open(jpg_path, "rb").read() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser(description="Seed sample missing persons into Qdrant via /enroll.")
    ap.add_argument("pairs", nargs="*", help="optional: frame.jpg \"Name\" frame.jpg \"Name\" ...")
    ap.add_argument("--backend", default="http://localhost:8100")
    ap.add_argument("--frames-dir", default="frames")
    args = ap.parse_args()

    jobs = []
    if args.pairs:
        for i in range(0, len(args.pairs) - 1, 2):
            jobs.append((args.pairs[i], {"name": args.pairs[i + 1]}))
    else:
        frames = sorted(glob.glob(os.path.join(args.frames_dir, "*.jpg")))
        if not frames:
            raise SystemExit(f"No frames in {args.frames_dir}/ — run ingest_video.py ... --save-frames {args.frames_dir} first.")
        # spread picks across the clip so we enroll different-looking faces
        picks = [frames[int(i * (len(frames) - 1) / max(1, len(SAMPLE_PEOPLE) - 1))]
                 for i in range(min(len(SAMPLE_PEOPLE), len(frames)))]
        jobs = list(zip(picks, SAMPLE_PEOPLE))

    enrolled = 0
    for path, person in jobs:
        try:
            resp = post_enroll(args.backend + "/enroll", path, person)
            p = resp.get("person", {})
            print(f"  ✓ enrolled {p.get('name')} ({p.get('person_id')}) from {os.path.basename(path)} "
                  f"— watchlist={resp.get('watchlist_size')}")
            enrolled += 1
        except Exception as e:
            print(f"  ✗ {os.path.basename(path)} ({person.get('name')}): {e}")
    print(f"seeded {enrolled} persons into Qdrant.")


if __name__ == "__main__":
    main()
