# DRISHTI — CCTV Video Search & Cross-Zone Tracking for Lost Persons

**Goal:** When a person is reported missing, use their **last-seen time + zone** and either a
**photo containing the person** or a **family member's photo + description** to search a
~30-minute window of CCTV in that zone, surface the most likely sightings for an operator to
confirm, then **track the confirmed person across neighbouring zones** to estimate their current
position and route help to them.

This extends the existing prototype:
- Zone-tagged camera network (`CCTV Dataset.kml` → 4,079 cameras, each with a zone).
- The no-photo workflow + zone→cameras mapping already in `index.html` / `build_data.py`.
- The face pipeline reference `backend_reference.py` (SCRFD → ArcFace → FAISS).
- The Claude parsing backend `backend.py` (free text → structured attributes).

---

## 0. Reality check — what is and isn't possible

This must be stated up front because it drives the architecture.

1. **A relative's face ≠ the missing person's face.** Face recognition on a sibling/parent photo
   will **not** find the lost person. Family resemblance is far too weak for biometric matching.
2. Therefore there are **two distinct search tracks**:
   - **Track A — Face search.** Only possible when a photo *containing the missing person* exists
     (a group/festival photo is common even when "we have no photo of just them"). Crop the
     person's face → real face-recognition search. High precision.
   - **Track B — Attribute + Re-ID search.** Used when only a relative's photo and a verbal
     description exist. Searches by **soft biometrics** — gender, age band, estimated height,
     build, clothing colours, accessories, attire style — plus a body **re-identification (Re-ID)**
     embedding. The relative's photo contributes only *soft shared cues* (skin tone, attire style,
     build), never a face match. This is **candidate generation**, not identification.
3. **This is decision-support for an authorised operator, never autonomous identification.**
   Every match is human-confirmed before any action. (See §10 Governance.)
4. **Probabilistic, demographically uneven.** Face- and attribute-model accuracy varies by
   age, skin tone, lighting, and pose. Surface confidence; never present a match as certain.

---

## 1. End-to-end pipeline

```
 Intake ─▶ Scope (zone+time) ─▶ Footage retrieval ─▶ Detect + track (tracklets)
   │                                                          │
   │                                       per-tracklet: face emb + Re-ID emb + attributes
   ▼                                                          ▼
 Build query ───────────────────────────────────────▶ Candidate ranking (top-K)
 (face | attrs+relative cues)                                 │
                                                              ▼
                                              Operator confirmation (human-in-the-loop)
                                                              │
                                            confirmed appearance signature (face/Re-ID/attrs)
                                                              ▼
                                   Cross-zone forward tracking ─▶ trajectory + current-position estimate
                                                              ▼
                                          Alert nearest help-point / police + family
```

### Phase 0 — Intake (extends the current Report flow)
Already captured: name (optional), gender, age band, language, **last-seen location → zone**,
report time, physical description. Add:
- **Photo upload** with a required tag: *"contains the missing person"* (→ Track A) vs
  *"this is a relative"* (→ Track B). Different tag → different pipeline.
- Structured attributes for Track B (use `backend.py /parse-intake` to turn the volunteer's
  dictation into `{gender, age, height_estimate, upper_color, lower_color, build, marks}`).
- Consent capture for using the photo (see §10).

### Phase 1 — Spatio-temporal scoping
- `seenCoords[location].zone` → the camera set `D.cameras.filter(c => c.zone === zone)`
  (already computed; e.g. Ramkund → Zone Area 30 → ~1,260 cameras).
- Time window: default **`[T − 15min, T + 15min]`** around the last-seen time `T`, adaptively
  widened (±30, ±60) if no strong candidate appears.
- This scoping is the key cost-control lever — it turns "search 4,079 cameras forever" into
  "search the cameras of one zone for 30 minutes."

### Phase 2 — Footage retrieval
- Production: pull recorded segments from the VMS/NVR by `(camera_id, time_range)`.
- Prototype: a local folder of clips named `Z30-C12__2027-08-15T0900.mp4`, indexed by camera+time.

### Phase 3 — Detection & per-camera tracking
- **Person detector** (YOLOv8 / RT-DETR) on each frame → person boxes.
- **Face detector** (SCRFD, already in `backend_reference.py`) for Track A.
- **Tracker** (ByteTrack / BoT-SORT) to group detections into **tracklets** (one person crossing
  one camera = one tracklet), so we score *people*, not frames. Massively reduces candidates.

### Phase 4 — Per-tracklet feature extraction
For each tracklet compute and store:
- **Face embedding** (ArcFace / ANTELOPEV2, 512-d) — best frontal frame, if any.
- **Re-ID embedding** (OSNet / TransReID, 512-d) — body/clothing appearance, pose-robust.
- **Attributes** via a Pedestrian Attribute Recognition (PAR) model (trained on PA-100K / RAPv2):
  gender, age group, upper-clothing colour, lower-clothing colour, carrying/accessories.
- **Height estimate** — from the foot/head pixel positions projected through a **per-camera
  ground-plane homography** (requires one-time camera calibration; flag as real cost). Coarse
  bands (short/medium/tall) are realistic; exact cm is not.
- Metadata: `camera_id, zone, timestamp, bbox, thumbnail`.

> **Performance note:** in a real deployment these features are computed **continuously at ingest**
> (NVIDIA DeepStream over RTSP) and written to a vector DB, so a "search" is a fast *filtered
> vector query* — not a re-decode of video. Retrospective decode is the fallback for the MVP.

### Phase 5 — Query construction
- **Track A:** query = the cropped face embedding (+ attribute filter as a soft prior).
- **Track B:** query = `{attribute vector, optional Re-ID cues from relative photo,
  family description}`. No face vector for the missing person yet.

### Phase 6 — Candidate ranking
Score every tracklet in scope:

- **Track A:** `score = cosine(face_q, face_t)` gated by attribute consistency; threshold ≈ 0.38
  cosine distance (already in `backend_reference.py`).
- **Track B:** weighted blend (weights calibrated on a validation set):
  ```
  score =  w_attr · attr_match(gender, age, height, upper_color, lower_color)
         + w_reid · reid_softcue_sim          # weak — relative photo / generic body prior
         + w_space · spatial_plausibility       # near the last-seen point within the window
         + w_time · temporal_proximity(|t − T|)
  ```
  Return **top-K (e.g. 20)** with thumbnails, camera, timestamp, and a calibrated confidence —
  **never** auto-select.

### Phase 7 — Operator confirmation (mandatory)
- Operator reviews the top-K grid; the family can help identify clothing.
- On confirm, lock the **appearance signature** from that tracklet:
  `{face_emb (now real, if visible), reid_emb, attrs, last_confirmed: (camera, zone, t)}`.
- This is the moment the system gains a real query for the *missing person* even in Track B.

### Phase 8 — Cross-zone forward tracking
Tracking-by-search, gated by geography so we never brute-force all cameras:

```
signature  ← confirmed tracklet
current    ← (camera, zone, t_confirmed)
trajectory ← [current]
while not at_present_time and not closed:
    Δt          ← search step (e.g. 5–10 min)
    reachable   ← zones within walking distance of current.zone in Δt
                  (haversine on zone centroids ÷ ~1.4 m/s; we already have coords)
    cams        ← cameras in reachable zones
    window      ← [current.t, current.t + Δt]
    cands       ← rank tracklets in (cams × window) against signature   # Re-ID + face + attrs
    best        ← argmax(cands) if score ≥ τ else None
    if best:
        trajectory.append(best); current ← best
        update signature (rolling clothing/appearance, handle bag put down etc.)
    else:
        widen reachable / Δt once; if still nothing → mark trajectory end (lost track)
estimate_current_position(trajectory)   # last confident node, or zone heat-map if uncertain
```

- **Gating** (reachable-zone set) keeps each step to tens of cameras, not thousands.
- Maintain a **probability heat-map over zones** for the current position when the tail is
  uncertain (multiple weak continuations).
- Can also run **backward** from the first confirmed sighting to reconstruct the entry path.

### Phase 9 — Alerting & routing
- Reuse the existing map: draw the **trajectory** across zones with timestamps and the
  **current best-guess zone**.
- Auto-notify the **nearest police help-point** to the current estimate (already computed via
  haversine to `D.police`) and the **family contact**.
- If the live position is fresh (last sighting < few minutes), flag "LIVE — person likely here now."

### Phase 10 — Feedback, audit, lifecycle
- Operator marks true/false match → labelled data to recalibrate weights/thresholds.
- Full audit log of every search, view, and confirmation.
- Auto-purge embeddings/clips per retention policy on case closure / festival end.

---

## 2. Data model

```
Case(id, status, last_seen_zone, last_seen_ts, attrs, photo_kind[contains|relative], consent)
Tracklet(id, case_id?, camera_id, zone, t_start, t_end, face_emb, reid_emb, attrs, thumb_uri, bbox)
Sighting(id, case_id, tracklet_id, score, confidence, kind[candidate|confirmed], operator_id, ts)
Trajectory(case_id, [ {zone, camera_id, t, sighting_id} ... ], current_estimate, heatmap)
AuditLog(actor, action, case_id, target, ts)
```

Vector indexes: FAISS (faces) + FAISS (Re-ID), or **Milvus** at scale, partitioned by zone+time
for fast filtered queries.

---

## 3. APIs to add (extend `backend.py` / `backend_reference.py`)

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/case` | create a case (intake) |
| `POST` | `/search/face` | `{case_id, photo, zone, t_center, window_min}` → ranked sightings (Track A) |
| `POST` | `/search/attributes` | `{case_id, query, relative_photo?, zone, t, window}` → ranked (Track B) |
| `POST` | `/confirm` | `{case_id, sighting_id}` → lock appearance signature |
| `POST` | `/track` | `{case_id}` → run cross-zone tracking → trajectory + current estimate |
| `GET`  | `/case/{id}/trajectory` | fetch path + heat-map for the map UI |
| `WS`   | `/alerts` | push live position / new sighting events |

The existing `backend.py /parse-intake` already produces the structured attribute query Track B
needs; `backend_reference.py` already does face detect + embed + FAISS — `/search/face` is a thin
wrapper that adds the **camera/zone/time scope filter** before the FAISS query.

---

## 4. Model & infrastructure choices

| Need | Prototype | Production (Kumbh scale) |
|---|---|---|
| Person detection | YOLOv8n | YOLOv8/RT-DETR on DeepStream, edge GPUs |
| Face detect+embed | SCRFD + ArcFace (already) | same, GPU-batched |
| Tracking | ByteTrack | BoT-SORT + cross-camera Re-ID |
| Re-ID | OSNet (torchreid) | TransReID, continuously indexed |
| Attributes/height | PAR model + simple homography | calibrated multi-cam homography, PAR ensemble |
| Vector search | FAISS (in-proc) | Milvus, zone/time-partitioned |
| Ingest | folder of clips | NVIDIA DeepStream over RTSP, 4,079 streams |
| Orchestration | RQ/Celery job per search | Kafka + workers; one GPU ≈ 30–60 streams |
| LLM | Claude `/parse-intake`, trajectory summaries, VLM re-rank | same + VLM crop-vs-description verifier |

**Where Claude helps:** (a) free-text description → structured attribute query (done); (b) plain-
language trajectory summaries for operators ("last seen heading toward Zone 31 at 09:14"); (c) an
optional **VLM re-ranker** — pass a candidate crop + the family's description and ask Claude to
score consistency, as a second opinion on the top-K (still human-confirmed).

---

## 5. Performance & scale

- The **continuous-ingest + vector-index** design is what makes this tractable: search becomes a
  filtered ANN query over pre-computed tracklet embeddings, not a video re-decode.
- Scoping to one zone × 30 min cuts the candidate set from millions to thousands; tracklet-level
  (not frame-level) scoring cuts it again; gated cross-zone steps keep tracking cheap.
- Budget the worst case: busiest zone (~1,260 cameras) × 30 min — pre-indexed, this is a sub-second
  vector query; retrospective decode would need a GPU pool and a few minutes (acceptable for the
  first search, not for live tracking — hence pre-indexing for the live path).

---

## 6. Governance, privacy & ethics (non-negotiable)

This is mass biometric search over crowd footage at a religious gathering — legitimate **only** as
an authorised, tightly-scoped lost-and-found tool.

- **Authorisation & purpose limitation:** operated by mela administration / police; usable only for
  active lost-and-found cases — never a general watchlist.
- **Consent:** explicit consent to use the uploaded photo; the relative is told their photo is a
  *cue*, not a tracker of themselves.
- **Human-in-the-loop:** no autonomous identification or action; an operator confirms every match.
- **Data minimisation & retention:** store tracklet embeddings + thumbnails, not raw long-term
  video; **auto-purge** on case closure / end of festival; access-controlled, fully audited.
- **Accuracy caveats surfaced:** show confidence; document demographic error-rate variance; treat
  low-confidence matches as leads only.
- **Compliance:** India DPDP Act; document a DPIA; define a grievance/redress path.
- **No function creep:** contractual + technical controls preventing reuse for surveillance.

---

## 7. Evaluation

- **Retrieval:** rank-1 / rank-5 hit rate, Re-ID mAP on a held-out multi-camera set.
- **Tracking:** trajectory precision/recall, ID-switch rate, time-to-locate.
- **Safety:** false-match rate at the operator-presented threshold; demographic slice analysis.
- **Ops:** operator review time per case, % cases located.
- Build a synthetic/recorded eval set (volunteers walking known paths across cameras) before any
  real footage.

---

## 8. Phased roadmap

**Phase 1 — MVP (fits the current prototype, no live video):**
- Intake photo + `contains/relative` tag; reuse zone→cameras + time scoping (already built).
- `/search/face` = `backend_reference.py` FAISS query restricted to the zone's cameras + window,
  over a small set of pre-recorded/synthetic clips.
- Operator confirm UI in `index.html` (results grid → confirm) + a trajectory drawn on the
  existing map canvas using haversine zone adjacency for the "next likely zone" suggestion.
- Track B: attribute-only ranking (no Re-ID model yet) using `/parse-intake` output.

**Phase 2 — Real CV:** ByteTrack tracklets, OSNet Re-ID, PAR attributes, height via homography,
continuous embedding index for one zone.

**Phase 3 — Live:** DeepStream ingest, Milvus, real-time cross-zone tracking, WebSocket alerts,
police/family routing.

**Phase 4 — Scale & governance:** all zones, evaluation harness, DPIA, retention automation,
access control & audit.

---

## 9. MVP build order (concrete next steps)

1. Add photo-kind tag + consent to the report form; pass last-seen zone + time into a `Case`.
2. Extend `backend_reference.py`: `/search/face` accepts `{photo, zone, t_center, window_min}`,
   filters the watch-list/tracklet set by `zone ∈ cameras` and `|t − T| ≤ window`, returns ranked
   sightings with thumbnails.
3. Build the operator confirm grid in `index.html` (calls `/search/face`); on confirm, store the
   signature.
4. Add `/track`: greedy gated next-zone search using `D.cameras` zones + haversine adjacency;
   return a trajectory; render it on the map with timestamps + current-estimate marker.
5. Track B attribute ranking via `/parse-intake`; add Re-ID + PAR models in Phase 2.
```
