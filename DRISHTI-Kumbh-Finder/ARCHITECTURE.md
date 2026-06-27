# DRISHTI — App Architecture & Data Flow (as built)

Visual diagram: **`architecture_app.svg`**. Editable flow below.

> This is the *as-built prototype* flow. The aspirational production-scale view
> (edge GPUs / Kafka / Milvus / DeepStream) lives in `architecture_system.svg`
> and `architecture_pipeline.svg`.

```mermaid
flowchart LR
  %% ① data & offline build
  subgraph DATA["① Data & offline build"]
    CSV["data/*.csv<br/>2,500 persons + locations"]
    KML["KML (Google Earth)<br/>CCTV 4,079 zone-tagged · Police · Chokepoints"]
    BUILD["build_data.py<br/>mask mobiles · zone-tag cams · centroids"]
    APPDATA[("app_data.js — window.KMP<br/>persons · cameras · zones · police · choke · seenCoords · bbox")]
    CSV --> BUILD
    KML --> BUILD
    BUILD --> APPDATA
  end

  %% ② browser app (offline single file)
  subgraph APP["② Browser app — index.html (offline single file)"]
    T1["① Report (kiosk intake, optional photo)"]
    T2["② Unified search + ✨ Smart fill"]
    T3["③ Cross-center duplicates"]
    T4["④ Coverage map — 🛰 Satellite / ▦ diagram"]
    T5["⑤ Dashboard"]
    T6["⑥ CCTV trace — scope→rank→confirm→track"]
    ENGINE{{"matchScore() — gender·age·lang·GPS(haversine)·name·time"}}
    T2 --- ENGINE
    T3 --- ENGINE
  end

  %% ③ optional online services
  subgraph SVC["③ Optional online services (graceful-degrade)"]
    CLAUDE["backend.py :8000 (Claude)<br/>/parse-search · /parse-intake → claude-opus-4-8"]
    FACE["backend_reference.py :8100<br/>SCRFD+ArcFace (buffalo_l) · attributes · cross-zone track"]
    QDRANT[("Qdrant vector DB<br/>persons · sightings · people")]
    FEED["Feeders<br/>ingest_video · live_feed · capture_people · seed"]
    FOOT["Sample footage<br/>street_crossing.webm · 10924096-…mp4"]
    FOOT --> FEED
    FEED -->|"/ingest-frame · /ingest-people"| FACE
    FACE <-->|"vectors + filtered search (zone+time)"| QDRANT
  end

  APPDATA -->|"loads (embedded)"| APP
  T2 -->|"natural language"| CLAUDE
  CLAUDE -->|"structured filters"| T2
  T6 -->|"/search/face · /track"| FACE
  FACE -->|"candidates · trajectory"| T6
  FACE -.->|"/recent-sightings (live layer)"| T4

  ESRI["Esri / OSM tiles (online)"] -.-> T4
```

## Design principles
- **Offline-first** — Report, Search, Duplicates, Dashboard, and the Diagram map run with **no internet and no backend** (all data embedded in `app_data.js`).
- **Graceful degradation** — Claude NL-search, satellite tiles, and the face/people pipeline activate only when reachable; otherwise the app falls back (diagram map, manual filters, simulated trace).
- **Human-in-the-loop** — every face match is operator-confirmed; the model assists, people decide.
- **Privacy by design** — API key server-side only (never in the browser), consent on uploaded photos, embeddings auto-purged at case/mela close.
- **One-command demo** — `demo_setup.sh` brings the full stack (Qdrant backend + real-time feed + sample data) up at once.

## Request flows (who calls what)
| User action | In-app | Online call | Store |
|---|---|---|---|
| Report / search / duplicates / dashboard | `matchScore()` over `window.KMP` | — | embedded |
| ✨ Smart fill (NL → filters) | Search tab | `backend.py /parse-search` | — |
| Coverage map (satellite + layers + live) | Leaflet ④ | Esri tiles · `/recent-sightings` | Qdrant `sightings` |
| CCTV trace (no-photo locate, Track A) | trace ⑥ | `/search/face` → `/track` | Qdrant `sightings` |
| Live CCTV ingest | — | `live_feed → /ingest-frame` | Qdrant `sightings` |
| Crowd capture + attributes | — | `capture_people → /ingest-people` | Qdrant `people` |
| Enroll missing person | — | `seed → /enroll` | Qdrant `persons` |
