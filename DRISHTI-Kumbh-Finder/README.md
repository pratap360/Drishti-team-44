# DRISHTI — Unified Lost-&-Found for the Kumbh Mela 2027

A prototype that turns **ten disconnected lost-and-found centers into one searchable
registry** — closing the gap where a person found at Center A is invisible to a family
searching at Center B. Built on the Claude Impact Lab dataset (Nashik Kumbh Mela 2027).

## Run it
**Double-click `index.html`.** No install, no server, no internet required for the core flow —
all data is embedded in `app_data.js` and the map is drawn directly from GPS coordinates.

## The five-step flow

1. **Report a case** — a volunteer at a kiosk registers a *Missing* or *Found* person.
   Name and mobile are optional (15% of real cases have no name, 20% no mobile). On submit,
   DRISHTI instantly cross-searches **every other center** and surfaces possible matches.
2. **Unified search** — a family describes their relative at *any* center; the whole registry
   is ranked by similarity (gender, age band, language, last-seen proximity, name, time).
3. **Cross-center duplicates** — clusters likely-same records reported at *different* centers
   so an operator can link & resolve them (~8% of cases are cross-center duplicates).
4. **Coverage map** — 4,079 zone-tagged cameras, 32 zones, 14 police stations, 85 chokepoints.
   Toggle **🛰 Satellite** for a real zoomable map (Leaflet + Esri imagery, no API key, needs
   internet) with all layers as toggleable markers, or **▦ Diagram** for the fully-offline
   coordinate render. Pick a location → nearest police help-point, the cameras in that zone, and
   separation-risk warning if it sits on a chokepoint.
5. **Dashboard** — live analytics over all 2,500 cases (status, age, center load, hotspots).
6. **CCTV trace** — the no-photo locate workflow: pick a last-seen location + time → DRISHTI
   pulls the zone's cameras for a ±15-min window, ranks candidate sightings for an operator to
   *confirm*, then tracks the confirmed person across walking-reachable zones to estimate their
   current position and nearest help-point — drawn on the same **🛰 Satellite / ▦ Diagram** map as
   the Coverage tab. (Demo scores are simulated; the production face/Re-ID pipeline is specified in
   `LOST_PERSON_VIDEO_SEARCH_PLAN.md`.)

## No photo? (≈20% of families have none)
A missing person is never required to have a photo. When a report has no photo, DRISHTI:
1. **Matches on attributes** across every center (gender, age band, language, last-seen
   proximity, name, time) — the same engine as photo cases, photo just adds one more signal.
2. **Pulls CCTV by zone** — the last-seen location resolves to a zone, and every one of the
   4,079 cameras is tagged with the zone it covers (`Z7-C3` → Zone Area 7; the general/mobile/
   gate/ring-road cameras are assigned by nearest zone centroid). The report screen lists the
   nearest cameras and queues a footage-pull for all cameras in that zone, so the control room
   can review recordings (or lift a face from them) even when the family has nothing to upload.

## Optional: Claude AI backend (`backend.py`)
The core app is 100% offline. `backend.py` is an *optional* online add-on that turns
plain English into structured filters via Claude — the API key lives **only** on the
server, never in the browser.

```bash
pip install -r requirements-backend.txt
export ANTHROPIC_API_KEY=sk-ant-...    # set in the shell, never hardcoded
python3 backend.py                      # http://localhost:8000  (Swagger at /docs)
```

- `POST /parse-search` — *"elderly woman in a green saree, speaks Marathi, last seen near
  Ramkund"* → `{gender, age, lang, seen, …}`, constrained to the dataset's exact values, fed
  straight into the same `matchScore()` engine. Wired to the **✨ Smart fill** box on the
  Search tab (degrades to manual filters if the server is off).
- `POST /parse-intake` — a volunteer's dictated description → structured kiosk intake fields.

Uses `claude-opus-4-8` with structured outputs. The key is read from `ANTHROPIC_API_KEY`;
if it's ever exposed, rotate it in the [Anthropic Console](https://console.anthropic.com/settings/keys).

## Optional: face/sighting backend (`backend_reference.py`) — Qdrant-backed
Powers **Track A** of the CCTV trace tab with real face matching (SCRFD → ArcFace), storing
vectors in **Qdrant**, served on `http://localhost:8100`.

```bash
pip install -r requirements-face.txt
python3 backend_reference.py
```

**Qdrant** is the vector store, in two collections:
- `persons` — enrolled missing persons: 512-D face vector + details (`name`, `age`, `gender`, `zone`, `mobile`).
- `sightings` — faces detected in CCTV frames: 512-D vector + payload (`camera_id`, `zone`, `t`).

By default Qdrant runs **embedded** (a local `./qdrant_data` dir — no Docker). To use a server:
`export QDRANT_URL=http://localhost:6333` (e.g. `docker run -p 6333:6333 qdrant/qdrant`). The
2,500-row attribute registry stays in `app_data.js`; Qdrant is specifically the image/face store.

- `POST /ingest-frame` — index a CCTV frame's faces as **sightings**.
- `POST /search/face` — a photo *containing the missing person* + `zone` + time window → ranked
  sightings (Qdrant filtered vector query: zone match + time range; operator confirms).
- `POST /track` — from a confirmed `sighting_id`, track the same face across reachable zones
  (gated by `app_data.js` geography) → trajectory + nearest help-point.
- Watch-list `/enroll` + `/search`; status `/persons` `/sightings` `/recent-sightings` `/stats` `/health`.

On the satellite **Coverage map**, two extra layers tie it all together: **📹 Live sightings** (polls
`/recent-sightings` every few seconds and plots them near their zone, with a live count) and **🧭
Trace path** (the confirmed CCTV-trace trajectory) — so one view shows cameras, zones, police,
chokepoints, the live feed, and the located person's path at once.

**Feeders** (separate processes, talk to the backend over HTTP):
- `ingest_video.py` — one-shot: sample a video's frames into sightings.
- `live_feed.py` — continuous: stream the crowd video as a **live camera** (real-time), rotating
  through a walk-connected zone chain so `/track` gets a multi-hop path.
- `seed.py` — enroll a few sample missing persons into the `persons` collection.
- `capture_people.py` — stream an MP4 as live data and **capture each person with attributes**.

### People + attributes (`people` collection)
`POST /ingest-people` detects every person in a frame, reads **gender + age** (from the face
model's genderage head), samples **upper/lower clothing colour** from the body region, estimates
an **approximate height**, saves the crop to `captures/`, and stores the embedding + metadata +
a base64 thumbnail in the Qdrant **`people`** collection. Stream a video into it with:

```bash
python3 capture_people.py 10924096-hd_1920_1080_30fps.mp4 \
    --camera CAM-CROWD --zone "Zone Area 30" --fps 3 --loop
```

Each capture prints e.g. `+ Male  18-40  blue/navy  medium~`. List what's stored with
`GET /people`. Gender/age need the **`buffalo_l`** model (the default now; `antelopev2` has no
genderage head). Height is an *apparent-size* approximation — true height needs per-camera
calibration (see `LOST_PERSON_VIDEO_SEARCH_PLAN.md`).

> **Switching face models invalidates stored vectors.** `buffalo_l` and `antelopev2` produce
> different embeddings, so if you change `DRISHTI_FACE_MODEL`, delete `./qdrant_data` and re-ingest.

When this server is running with ingested footage, the **⑥ CCTV trace** tab uses real face
matches and real cross-zone tracking; otherwise it falls back to the built-in simulation. The
full production design (Re-ID, attributes, height, live ingest, governance) is in
`LOST_PERSON_VIDEO_SEARCH_PLAN.md`.

### Sample footage (stand-in CCTV) — one command
`sample_footage/street_crossing.webm` is a CC BY-SA 3.0 clip of a street crossing (see
`sample_footage/ATTRIBUTION.md`) used only as test CCTV. The whole Track A demo is one command:

```bash
bash demo_setup.sh
```

It creates a venv, installs deps, starts the Qdrant-backed backend, indexes the video as
sightings (+ saves frames and **prints the exact frame to use as the query photo**), seeds a few
sample missing persons into Qdrant, and starts `live_feed.py` so the crowd video keeps streaming
in **real time**. Then in **⑥ CCTV trace**: choose *Photo contains the person*, upload the printed
frame, set last-seen *Zone Area 30* / *09:00*, and search — candidates show the **live face match**
badge; Confirm to track across zones. Stop everything with
`kill $(cat .backend.pid) $(cat .feed.pid) 2>/dev/null`.

(Manual equivalent: start `python3 backend_reference.py`, then run `ingest_video.py`, `seed.py`,
and `live_feed.py` as documented above.)

## The matching engine
A single `matchScore(a, b)` (0–100) powers both search ranking and duplicate detection,
weighting gender, age band, language, last-seen GPS proximity (haversine), name edit-distance,
and report-time closeness. Duplicate detection adds a strict same-person predicate
(different center + matching demographics + same/near location + agreeing names).

## Files
| File | What |
|---|---|
| `index.html` | The app (single file) |
| `app_data.js` | Embedded dataset — generated, makes the app fully offline |
| `build_data.py` | Regenerates `app_data.js` from `data/*.csv` + `CCTV Dataset.kml` (masks mobile numbers) |
| `data/` | Source CSVs (synthetic missing persons + real location data) |
| `CCTV Dataset.kml` | Zone-tagged camera network (4,079 cameras) — richer than the CSV; ingested by `build_data.py` |
| `backend_reference.py` | Optional production stack (SCRFD+ArcFace+FAISS) for the face channel |
| `ARCHITECTURE.md`, `architecture_app.svg` | As-built app architecture & data flow (Mermaid + SVG) |
| `RESEARCH_REPORT.md`, `architecture_system.svg`, `architecture_pipeline.svg`, `DRISHTI_Pitch_Deck.pptx` | Production-vision docs |

## Built around the judging criteria
- **Deployability** — one offline HTML file; regenerate data with one Python command.
- **Real-world fit** — solves the dataset's two stated failures: the cross-center gap and duplicates.
- **UX for phoneless / non-literate** — operator-driven, attribute-based intake; no app on the
  missing person; language captured; large controls.
- **System design** — tolerates missing names/mobiles and partial queries; works with no network;
  face photo is an *optional* enhancement (pre-trained models, never required).
- **Responsible data** — synthetic records only; mobile numbers masked on load; nothing leaves the device.

## Regenerating data
```bash
python3 build_data.py     # reads data/*.csv → writes app_data.js
```

*Data: Kumbhathon Innovation Foundation (locations) + synthetic missing-person set,
Claude Impact Lab, Mumbai 2026. All missing-person records are fake.*
