"""
DRISHTI — Production-style reference backend (single file)
=========================================================
Real-time missing-person face matching for the Nashik Kumbh Mela, backed by
**Qdrant** (vector DB) for both person details+images and live CCTV sightings.

Stack:  SCRFD (detect) -> ArcFace / ANTELOPEV2 (512-D embed) -> Qdrant (ANN + payload filter)

Qdrant collections
  • persons    — enrolled missing persons: 512-D face vector + details payload
                 {person_id, name, age, gender, zone, mobile, ...}
  • sightings  — faces detected in CCTV frames: 512-D vector + payload
                 {camera_id, zone, t (minutes-of-day), bbox, det}

Why Qdrant: it does the ANN search *and* the metadata filtering in one query, so
the "no-photo locate" search — scoped to the last-seen zone and a ±N-minute
window — is a single filtered vector query (zone match + time range), which is
exactly what scales to Milvus/Qdrant in production.

Endpoints
  Watch-list:   POST /enroll      add a missing person (photo + details)
                POST /search      match faces in a frame vs the watch-list
  No-photo locate (Track A):
                POST /ingest-frame index a CCTV frame's faces as sightings
                POST /search/face  photo of the person + zone + window -> ranked sightings
                POST /track        face-based cross-zone tracking from a confirmed sighting
  Status:       GET  /persons /sightings /stats /health

Feeders (separate processes, talk to this backend over HTTP):
  • ingest_video.py  one-shot: sample a video's frames into sightings
  • live_feed.py     continuous: stream a crowd video as a live camera (real-time)
  • seed.py          enroll a few sample missing persons

This powers the ⑥ CCTV trace tab in index.html (default http://localhost:8100).
Full design + governance: LOST_PERSON_VIDEO_SEARCH_PLAN.md.

-----------------------------------------------------------------------------
PRIVACY / GOVERNANCE — authorised lost-and-found use only: consent for uploaded
photos, human-in-the-loop confirmation (never autonomous identification),
purpose limitation, access control + audit, auto-purge on case closure.
-----------------------------------------------------------------------------
SETUP
    python3 -m venv venv && source venv/bin/activate
    pip install -r requirements-face.txt
    python backend_reference.py            # serves on http://localhost:8100
    # Qdrant is embedded (local dir ./qdrant_data) by default — no Docker needed.
    # To use a Qdrant server instead:  export QDRANT_URL=http://localhost:6333
    #   (docker run -p 6333:6333 -v $PWD/qdrant_storage:/qdrant/storage qdrant/qdrant)

GPU note: swap onnxruntime -> onnxruntime-gpu for real throughput. Production
replaces the feeders with NVIDIA DeepStream over RTSP.
"""

import base64
import json
import math
import os
import threading
import time
import uuid
from typing import Optional

import numpy as np

try:
    import cv2
    from fastapi import FastAPI, UploadFile, File, Form, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from insightface.app import FaceAnalysis
    from qdrant_client import QdrantClient
    from qdrant_client.models import (Distance, VectorParams, PointStruct,
                                      Filter, FieldCondition, MatchValue, Range)
except ImportError as e:  # let the file be read even without deps installed
    print(f"[warn] missing dependency: {e}. pip install -r requirements-face.txt")

BASE = os.path.dirname(__file__)
EMB_DIM = 512                # ArcFace embedding size
FACE_SIM_CONFIDENT = 0.45    # sighting cosine-similarity above which a candidate is "likely same person"
PERSON_SIM_CONFIDENT = 0.50  # watch-list match threshold
DET_SIZE = (640, 640)
WALK_KMPM = 1.3 * 60 / 1000  # walking speed km/min (~0.078) — gates cross-zone hops
# Reach floor for cross-zone hops. The synthetic "Zone Area" centroids are
# city-scale (km apart), so a literal walking radius connects almost nothing;
# 4 km gives a believable multi-hop demo trajectory. Real ghat-zones are denser,
# where step_min * WALK_KMPM (true walking distance) is the right gate.
REACH_FLOOR_KM = float(os.environ.get("DRISHTI_REACH_KM", "4.0"))


# --------------------------------------------------------------------------- #
#  Geography from app_data.js (zones/police) so /track gates by zone and finds
#  the nearest help-point — keeps the backend in lock-step with the UI's data.
# --------------------------------------------------------------------------- #
def _load_geo():
    try:
        txt = open(os.path.join(BASE, "app_data.js"), encoding="utf-8").read()
        d = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        return d.get("zones", []), d.get("police", [])
    except Exception as e:
        print(f"[warn] could not load geo from app_data.js: {e}")
        return [], []


ZONES, POLICE = _load_geo()
ZONE_BY_NAME = {z["name"]: z for z in ZONES}


def haversine(a, b):
    R = 6371.0
    dlat = math.radians(b["lat"] - a["lat"])
    dlng = math.radians(b["lng"] - a["lng"])
    s = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(a["lat"])) * math.cos(math.radians(b["lat"])) * math.sin(dlng / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(s))


def to_minutes(ts):
    """Accept 'HH:MM' or a number already in minutes-of-day."""
    if ts is None or ts == "":
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    s = str(ts)
    if ":" in s:
        h, m = s.split(":")[:2]
        return int(h) * 60 + int(m)
    return float(s)


# --------------------------------------------------------------------------- #
#  Pedestrian attributes (Track B): gender + age come from the face model's
#  genderage head; clothing colours from sampling the body region below the
#  face; height is an *apparent-size* approximation (true height needs per-camera
#  homography — see LOST_PERSON_VIDEO_SEARCH_PLAN.md). Decision-support only.
# --------------------------------------------------------------------------- #
CAPTURES = os.path.join(BASE, "captures")
AGE_BANDS = [(12, "0-12"), (17, "13-17"), (40, "18-40"), (60, "41-60"), (70, "61-70"), (80, "71-80")]
NAMED_COLORS = {
    "black": (25, 25, 25), "white": (235, 235, 235), "gray": (128, 128, 128),
    "red": (200, 35, 35), "orange": (230, 140, 30), "yellow": (235, 220, 50),
    "green": (45, 160, 65), "blue": (45, 85, 200), "navy": (25, 35, 95),
    "purple": (120, 45, 165), "pink": (230, 135, 180), "brown": (120, 80, 45),
    "beige": (220, 200, 165),
}


def age_band(age):
    if age is None:
        return "Unknown"
    a = int(age)
    for hi, band in AGE_BANDS:
        if a <= hi:
            return band
    return "80+"


def nearest_color(rgb):
    return min(NAMED_COLORS, key=lambda n: sum((a - b) ** 2 for a, b in zip(rgb, NAMED_COLORS[n])))


def region_color(img, x0, y0, x1, y1):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))
    if x1 <= x0 or y1 <= y0:
        return None
    patch = img[y0:y1, x0:x1].reshape(-1, 3)
    if patch.size == 0:
        return None
    b, g, r = np.median(patch, axis=0)            # cv2 is BGR
    return nearest_color((int(r), int(g), int(b)))


def crop_b64(img, box, width=96):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = (max(0, int(box[0])), max(0, int(box[1])), min(w, int(box[2])), min(h, int(box[3])))
    if x1 <= x0 or y1 <= y0:
        return None, None
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return None, None
    th = cv2.resize(crop, (width, max(1, int(crop.shape[0] * width / crop.shape[1]))))
    ok, buf = cv2.imencode(".jpg", th, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return (base64.b64encode(buf).decode() if ok else None), crop


def estimate_attributes(img, face):
    """gender/age (model), upper+lower clothing colour (sampled), height (approx)."""
    h = img.shape[0]
    fx0, fy0, fx1, fy1 = [float(v) for v in face.bbox.tolist()]
    fw, fh, cx = fx1 - fx0, fy1 - fy0, (fx0 + fx1) / 2
    gender = {"M": "Male", "F": "Female"}.get(getattr(face, "sex", None), "Unknown")
    age = getattr(face, "age", None)
    upper = region_color(img, cx - 1.2 * fw, fy1 + 0.4 * fh, cx + 1.2 * fw, fy1 + 2.2 * fh)
    lower = region_color(img, cx - 1.2 * fw, fy1 + 2.4 * fh, cx + 1.2 * fw, fy1 + 4.8 * fh)
    frac = (7.5 * fh) / h                          # apparent body height as a fraction of frame
    height = "tall~" if frac > 0.7 else "medium~" if frac > 0.45 else "short~"
    person_box = (cx - 1.6 * fw, fy0 - 0.4 * fh, cx + 1.6 * fw, fy1 + 6.0 * fh)
    attrs = {"gender": gender, "age": age_band(age),
             "age_years": int(age) if age is not None else None,
             "upper_color": upper or "?", "lower_color": lower or "?", "height": height}
    return attrs, person_box


# --------------------------------------------------------------------------- #
#  Face engine — SCRFD detect + ArcFace embed (no index; storage is Qdrant)
# --------------------------------------------------------------------------- #
class FaceMatcher:
    def __init__(self):
        # buffalo_l bundles detection (SCRFD) + recognition (512-D) + genderage,
        # so we get gender/age out of the box (antelopev2 has no genderage head).
        self.app = FaceAnalysis(name=os.environ.get("DRISHTI_FACE_MODEL", "buffalo_l"),
                                providers=["CPUExecutionProvider"])
        self.app.prepare(ctx_id=0, det_size=DET_SIZE)
        self.faces_scanned = 0

    @staticmethod
    def _norm(v: np.ndarray) -> np.ndarray:
        return v / (np.linalg.norm(v) + 1e-9)

    def embed_all(self, img: np.ndarray) -> list[dict]:
        faces = self.app.get(img)
        self.faces_scanned += len(faces)
        return [{"emb": self._norm(f.embedding).astype("float32"),
                 "bbox": [int(v) for v in f.bbox.tolist()],
                 "det": float(f.det_score)} for f in faces]

    def embed_best(self, img: np.ndarray) -> Optional[np.ndarray]:
        faces = self.app.get(img)
        if not faces:
            return None
        f = max(faces, key=lambda x: x.det_score)
        return self._norm(f.embedding).astype("float32")

    def people_in(self, img: np.ndarray) -> list[dict]:
        """Detect each person and return embedding + attributes + a thumbnail crop."""
        out = []
        for f in self.app.get(img):
            self.faces_scanned += 1
            attrs, pbox = estimate_attributes(img, f)
            thumb, crop = crop_b64(img, pbox)
            out.append({"emb": self._norm(f.embedding).astype("float32"),
                        "bbox": [int(v) for v in f.bbox.tolist()], "det": float(f.det_score),
                        "attrs": attrs, "thumb": thumb, "crop": crop})
        return out


# --------------------------------------------------------------------------- #
#  Qdrant store — persons + sightings. Local embedded by default; QDRANT_URL
#  switches to a server/cloud instance. A lock serialises access because the
#  embedded client (and our background feeders) hit it concurrently.
# --------------------------------------------------------------------------- #
class QdrantStore:
    def __init__(self):
        url = os.environ.get("QDRANT_URL")
        if url:
            self.client = QdrantClient(url=url, api_key=os.environ.get("QDRANT_API_KEY"))
            self.mode = f"server {url}"
        else:
            self.client = QdrantClient(path=os.path.join(BASE, "qdrant_data"))
            self.mode = "embedded ./qdrant_data"
        self._lock = threading.Lock()
        for name in ("persons", "sightings", "people"):
            if not self.client.collection_exists(name):
                self.client.create_collection(
                    name, vectors_config=VectorParams(size=EMB_DIM, distance=Distance.COSINE))

    @staticmethod
    def _vec(v):
        return v.tolist() if hasattr(v, "tolist") else list(v)

    def add_person(self, emb, payload, point_id):
        with self._lock:
            self.client.upsert("persons", [PointStruct(id=point_id, vector=self._vec(emb), payload=payload)])

    def add_sighting(self, emb, payload, point_id):
        with self._lock:
            self.client.upsert("sightings", [PointStruct(id=point_id, vector=self._vec(emb), payload=payload)])

    def search_sightings(self, query, zone=None, t_center=None, window_min=15, k=20):
        must = []
        if zone:
            must.append(FieldCondition(key="zone", match=MatchValue(value=zone)))
        if t_center is not None:
            must.append(FieldCondition(key="t", range=Range(gte=t_center - window_min, lte=t_center + window_min)))
        flt = Filter(must=must) if must else None
        with self._lock:
            res = self.client.query_points("sightings", query=self._vec(query),
                                           query_filter=flt, limit=k, with_payload=True)
        out = []
        for p in res.points:
            pl, sim = p.payload, float(p.score)
            out.append({"sighting_id": pl.get("sighting_id", str(p.id)), "camera_id": pl["camera_id"],
                        "zone": pl["zone"], "t": pl["t"], "score": round(sim * 100, 1),
                        "confident": sim >= FACE_SIM_CONFIDENT, "bbox": pl.get("bbox")})
        return out

    def get_sighting(self, sighting_id):
        with self._lock:
            recs = self.client.retrieve("sightings", ids=[sighting_id], with_vectors=True, with_payload=True)
        if not recs:
            return None, None
        return recs[0].vector, recs[0].payload

    def search_persons(self, query, k=1):
        with self._lock:
            return self.client.query_points("persons", query=self._vec(query), limit=k, with_payload=True).points

    def list_persons(self, limit=200):
        with self._lock:
            pts, _ = self.client.scroll("persons", limit=limit, with_payload=True)
        return [p.payload for p in pts]

    def recent_sightings(self, limit=400):
        """Lightweight payloads for the live map layer (no vectors)."""
        with self._lock:
            pts, _ = self.client.scroll("sightings", limit=limit, with_payload=True, with_vectors=False)
        return [{"camera_id": p.payload.get("camera_id"), "zone": p.payload.get("zone"),
                 "t": p.payload.get("t")} for p in pts]

    def add_people(self, emb, payload, point_id):
        with self._lock:
            self.client.upsert("people", [PointStruct(id=point_id, vector=self._vec(emb), payload=payload)])

    def recent_people(self, limit=200):
        with self._lock:
            pts, _ = self.client.scroll("people", limit=limit, with_payload=True, with_vectors=False)
        return [p.payload for p in pts]

    def count(self, name):
        with self._lock:
            return self.client.count(name).count


def track_face(query, start_zone, start_t, step_min=10, max_steps=6) -> list[dict]:
    """Gated cross-zone tracking (Track A): at each step search only the zones the
    person could have walked to, for the same face, in the next time window."""
    traj, visited = [], {start_zone}
    cur = ZONE_BY_NAME.get(start_zone)
    t = start_t
    for _ in range(max_steps):
        if not cur:
            break
        t += step_min
        reach_km = max(step_min * WALK_KMPM, REACH_FLOOR_KM)
        reachable = [z["name"] for z in ZONES
                     if z["name"] not in visited and haversine(cur, z) <= reach_km]
        best = None
        for zn in reachable:
            res = STORE.search_sightings(query, zone=zn, t_center=t, window_min=step_min)
            if res and (best is None or res[0]["score"] > best["score"]):
                best = res[0]
        if not best or not best["confident"]:
            break
        traj.append(best)
        visited.add(best["zone"])
        cur = ZONE_BY_NAME.get(best["zone"])
        t = best["t"]
    return traj


# --------------------------------------------------------------------------- #
#  API
# --------------------------------------------------------------------------- #
app = FastAPI(title="DRISHTI — Kumbh Missing Person Finder",
              description="SCRFD + ArcFace + Qdrant — watch-list + CCTV sighting search & tracking")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

matcher: Optional[FaceMatcher] = None
STORE: Optional[QdrantStore] = None


@app.on_event("startup")
def _startup():
    global matcher, STORE
    STORE = QdrantStore()
    matcher = FaceMatcher()
    print(f"[drishti] Qdrant {STORE.mode}; models loaded; {len(ZONES)} zones, {len(POLICE)} police. ready.")


def _read(upload: UploadFile) -> np.ndarray:
    arr = np.frombuffer(upload.file.read(), np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Could not decode image.")
    return img


# ---- watch-list ----
@app.post("/enroll")
async def enroll(file: UploadFile = File(...), name: str = Form(...), age: str = Form(""),
                 gender: str = Form("Unknown"), zone: str = Form("Unknown"), mobile: str = Form("")):
    emb = matcher.embed_best(_read(file))
    if emb is None:
        raise HTTPException(422, "No face detected in enrollment photo.")
    pid = str(uuid.uuid4())
    payload = {"person_id": pid, "name": name, "age": age, "gender": gender,
               "zone": zone, "mobile": mobile, "enrolled_at": time.time()}
    STORE.add_person(emb, payload, pid)
    return {"status": "enrolled", "person": payload, "watchlist_size": STORE.count("persons")}


@app.post("/search")
async def search(file: UploadFile = File(...), camera_id: str = Form("CAM-00"),
                 location: str = Form("Unknown"), threshold: float = Form(PERSON_SIM_CONFIDENT)):
    hits = []
    for f in matcher.embed_all(_read(file)):
        pts = STORE.search_persons(f["emb"], k=1)
        if pts and float(pts[0].score) >= threshold:
            pl = pts[0].payload
            hits.append({"person_id": pl.get("person_id"), "name": pl.get("name"),
                         "confidence": round(float(pts[0].score) * 100, 1),
                         "camera_id": camera_id, "location": location, "bbox": f["bbox"]})
    return {"matches": hits}


# ---- CCTV sighting model (no-photo locate, Track A) ----
@app.post("/ingest-frame")
async def ingest_frame(file: UploadFile = File(...), camera_id: str = Form(...),
                       zone: str = Form(...), ts: str = Form("09:00")):
    t = to_minutes(ts) or 0.0
    faces = matcher.embed_all(_read(file))
    ids = []
    for f in faces:
        sid = str(uuid.uuid4())
        STORE.add_sighting(f["emb"], {"sighting_id": sid, "camera_id": camera_id, "zone": zone,
                                      "t": t, "bbox": f["bbox"], "det": f["det"]}, sid)
        ids.append(sid)
    return {"camera_id": camera_id, "zone": zone, "t": t, "faces_indexed": len(ids),
            "max_det": round(max((f["det"] for f in faces), default=0.0), 3),
            "sighting_ids": ids, "total_sightings": STORE.count("sightings")}


@app.post("/ingest-people")
async def ingest_people(file: UploadFile = File(...), camera_id: str = Form(...),
                        zone: str = Form(...), ts: str = Form("09:00")):
    """Detect each person in a frame, extract attributes (gender/age/colour/height),
    save the crop, and store the embedding + metadata + thumbnail in Qdrant `people`."""
    os.makedirs(CAPTURES, exist_ok=True)
    img = _read(file)
    t = to_minutes(ts) or 0.0
    res = []
    for p in matcher.people_in(img):
        pid = str(uuid.uuid4())
        if p["crop"] is not None and p["crop"].size:
            cv2.imwrite(os.path.join(CAPTURES, pid + ".jpg"), p["crop"])
        payload = {"person_id": pid, "camera_id": camera_id, "zone": zone, "t": t,
                   "det": round(p["det"], 3), "bbox": p["bbox"], "thumb": p["thumb"], **p["attrs"]}
        STORE.add_people(p["emb"], payload, pid)
        res.append({"person_id": pid, **p["attrs"]})
    return {"camera_id": camera_id, "zone": zone, "t": t, "people_indexed": len(res),
            "people": res, "total_people": STORE.count("people")}


@app.get("/people")
async def people(limit: int = 50):
    """List indexed people (thumbnails omitted from the list for size)."""
    items = [{k: v for k, v in it.items() if k != "thumb"} for it in STORE.recent_people(limit)]
    return {"count": STORE.count("people"), "people": items}


@app.post("/search/face")
async def search_face(file: UploadFile = File(...), zone: str = Form(""),
                      t_center: str = Form(""), window_min: float = Form(15), k: int = Form(20)):
    q = matcher.embed_best(_read(file))
    if q is None:
        raise HTTPException(422, "No clear face in the query photo.")
    tc = to_minutes(t_center)
    cands = STORE.search_sightings(q, zone=zone or None, t_center=tc, window_min=window_min, k=k)
    return {"track": "A", "zone": zone, "t_center": tc, "window_min": window_min,
            "scanned": STORE.count("sightings"), "candidates": cands}


@app.post("/track")
async def track(sighting_id: str = Form(...), step_min: float = Form(10), max_steps: int = Form(6)):
    vec, pl = STORE.get_sighting(sighting_id)
    if pl is None:
        raise HTTPException(404, "Unknown sighting_id — confirm a sighting first.")
    traj = [{"sighting_id": sighting_id, "camera_id": pl["camera_id"], "zone": pl["zone"],
             "t": pl["t"], "score": 100.0, "confident": True}]
    traj += track_face(np.asarray(vec, dtype="float32"), pl["zone"], pl["t"],
                       step_min=step_min, max_steps=max_steps)
    last = ZONE_BY_NAME.get(traj[-1]["zone"])
    nearest = None
    if last and POLICE:
        ps = min(POLICE, key=lambda p: haversine(last, p))
        nearest = {"name": ps["name"], "km": round(haversine(last, ps), 2)}
    return {"trajectory": traj, "current_estimate": traj[-1]["zone"], "nearest_help_point": nearest}


# ---- status ----
@app.get("/persons")
async def persons():
    return {"count": STORE.count("persons"), "people": STORE.list_persons()}


@app.get("/sightings")
async def sightings():
    return {"count": STORE.count("sightings")}


@app.get("/recent-sightings")
async def recent_sightings(limit: int = 400):
    """For the Coverage map's live layer: recent sightings as {camera_id, zone, t}."""
    return {"count": STORE.count("sightings"), "sightings": STORE.recent_sightings(limit)}


@app.get("/stats")
async def stats():
    return {"backend": "qdrant", "qdrant": STORE.mode if STORE else "?",
            "persons": STORE.count("persons") if STORE else 0,
            "sightings": STORE.count("sightings") if STORE else 0,
            "people": STORE.count("people") if STORE else 0,
            "faces_scanned": matcher.faces_scanned if matcher else 0,
            "embedding_dim": EMB_DIM, "sighting_threshold": FACE_SIM_CONFIDENT}


@app.get("/health")
async def health():
    return {"ok": True, "qdrant": STORE.mode if STORE else "?",
            "persons": STORE.count("persons") if STORE else 0,
            "sightings": STORE.count("sightings") if STORE else 0,
            "zones": len(ZONES), "police": len(POLICE)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100)
