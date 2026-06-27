# Finding Missing People in Real Time at the Nashik Kumbh Mela 2027
### A research report and system design for DRISHTI

*Prepared June 2026 · for the Nashik–Trimbakeshwar Simhastha Kumbh Mela 2027–28*

---

## 1. The problem

The Kumbh Mela is the largest peaceful human gathering on Earth, and getting separated from one's family in it is one of the most common and frightening experiences a pilgrim can have. The next one — the Nashik–Trimbakeshwar Simhastha Kumbh — runs from late 2026 into 2028, with the main bathing season in 2027. Authorities expect on the order of **12 crore (120 million) pilgrims** across the mela, with a **peak-day footfall estimated near 2.5 crore (25 million)** concentrated around a handful of bathing dates and ghats. Tens of thousands of people are reported missing across a Kumbh; most are reunited within hours, but the elderly, children, and people who don't speak the local language are especially vulnerable, and every hour of separation is acute distress.

The traditional answer is the *Bhula-Bhatka* (lost-and-found) camp: a public-address system and a tent where separated people wait to be claimed. It works, but it is slow, depends on the missing person staying near a booth, and does nothing for someone who is disoriented, wandering, or unable to ask for help. The opportunity is to add a layer that actively *searches* the crowd: given a photo of the missing person supplied by their family, scan the live camera network and report where that face appears, in near-real time.

This is not hypothetical. At the **Prayagraj Maha Kumbh 2025**, authorities for the first time used AI facial recognition specifically to locate lost people: when someone was reported missing, the system scanned the camera network and traced the person's route through CCTV footage, supported by roughly **2,750+ AI-enhanced CCTV cameras**, **100 dedicated face-recognition cameras** at major stations, and **10 lost-and-found tech booths**. India's police already run a national **Automated Facial Recognition System (AFRS)** for tracing missing children, which has matched thousands of missing-child cases. DRISHTI takes that proven idea and designs it specifically for the scale and geography of Nashik 2027.

---

## 2. The Nashik 2027 ground truth (why design for this site specifically)

The system must be designed around the *actual* deployment the Maharashtra administration is building, not a generic crowd. Published planning gives us concrete numbers to design against:

| Parameter | Planned figure for Nashik 2027 |
|---|---|
| AI CCTV cameras | **4,011** |
| Surveillance drones | **18** |
| Surveillance / tech budget | **≈ ₹300 crore** |
| Central platform | **"Kumbh AI Stack"** — fuses CCTV + sensors + telecom signals |
| Expected pilgrims (whole mela) | **≈ 12 crore (120 million)** |
| Estimated peak-day footfall | **≈ 2.5 crore (25 million)** |
| Camera installation deadline | **March 2026** |
| Railway security | ~3,000 RPF personnel + AI surveillance |

**Where the cameras are.** Coverage is concentrated where pilgrims actually flow and where separations happen: the **Ramkund** bathing area on the Godavari (the single most crowded zone), the surrounding **ghats**, the **Sadhugram** akhada/sadhu camps, the **Trimbakeshwar temple** area in Trimbak (~30 km away), and the transport choke-points — **Nashik Road railway station**, the **CBS bus stand**, and feeder corridors like **Ramkund Marg**. This geography matters for design: a missing-person system should weight and prioritise the highest-density bathing zones and the transport gateways, because that is both where people get lost and where a wandering person is most likely to reappear.

**Two events sharing one site.** Nashik 2027 actually spans two locations ~30 km apart (Nashik city / Ramkund and Trimbakeshwar), connected by pilgrim corridors. A practical missing-person system must treat them as one logical search space — a person reported missing at Ramkund may surface at Trimbakeshwar — which is exactly why a single central vector index across all 4,011 cameras (rather than per-camera search) is the right architecture.

**The opportunity for DRISHTI.** The state's "Kumbh AI Stack" is being built primarily for *crowd-density and anomaly detection*. Facial recognition is listed among its features, but the missing-person reunification use case deserves a purpose-built, family-facing, privacy-bounded module. DRISHTI is that module: it rides on the same camera fabric the state is already paying ₹300 crore for, and adds the enrollment, matching, alerting, and consent workflow that turns raw face-recognition capability into reunited families.

---

## 3. How the technology actually works

Modern face search is a three-stage pipeline — **detect → embed → match** — and the prototype in this package implements exactly these stages (in the browser for the demo, and with production models in `backend_reference.py`).

**Detect.** A face detector finds every face in a frame and returns bounding boxes. The field standard for crowds is **RetinaFace** or its faster cousin **SCRFD**; both perform well even in dense, partially-occluded crowds, which is precisely the Kumbh condition. The browser demo uses SSD-MobileNet as a lightweight stand-in.

**Embed.** Each detected face is passed through a recognition network that outputs a fixed-length vector — an embedding, or "face-print." The state of the art is **ArcFace** (from the open-source **InsightFace** project), producing a 512-dimension vector that is robust to lighting, pose, and expression. Two photos of the same person produce vectors that are close together; different people produce vectors that are far apart. The demo uses a 128-D descriptor for speed.

**Match.** Recognition becomes a *nearest-neighbour search* problem. The family's enrolled photo is embedded once and stored in a vector index. Every face seen on every camera is embedded and compared against that index. With millions of faces flowing through the system, you cannot scan linearly — you use a **vector database** like **FAISS** or **Milvus**, which can return the closest matches from millions of vectors in tens of milliseconds, using cosine (or Euclidean) distance. If the distance to a watch-list face is below a tuned threshold, it's a candidate match.

**Tracking across cameras.** A single match is a sighting; what families and police really want is a *path*. **ByteTrack** (and similar multi-object trackers) link the same person across consecutive frames and neighbouring cameras, reconstructing the route a wandering person took — exactly what Prayagraj's "route mapping via CCTV" did, but automated.

**Running it at 4,011-camera scale.** You cannot send 4,011 video streams to one server. The standard answer is **edge inference**: **NVIDIA DeepStream** runs detection and embedding on GPU nodes close to the cameras, and only the resulting *vectors and metadata* (not raw video) travel to the central control room. This slashes bandwidth, improves privacy (raw faces aren't shipped around), and lets the system scale by adding GPU nodes. One modern GPU with DeepStream handles roughly 30–60 streams, so the full deployment is on the order of ~100 edge GPUs feeding a central FAISS/Milvus index — comfortably within the ₹300 crore envelope.

---

## 4. The DRISHTI system architecture

The full design (see `architecture_system.svg` and `architecture_pipeline.svg`) has three layers.

**① Edge — field capture.** The 4,011 AI CCTV cameras and 18 drones feed edge GPU nodes running DeepStream + TensorRT, which decode RTSP, detect faces (SCRFD), compute embeddings (ArcFace), and track (ByteTrack). Crucially, the edge sends *vectors, not video*. Alongside the cameras sit two enrollment channels: **Bhula-Bhatka booths** where a family member's photo and consent are captured, and a **citizen/police app** for self-service reporting.

**② Core — the matching platform** (riding on the state's "Kumbh AI Stack"). A stream-ingest layer (Kafka-style event bus, per-camera workers) feeds the **vector matching engine** (FAISS/Milvus) which holds every consented watch-list embedding and answers top-k queries in under 50 ms. A **watch-list database** (PostgreSQL) holds person metadata and consent records; an **alert & case engine** dedupes hits, routes them to the nearest booth and the registering family, and inserts a human-in-the-loop confirmation step. A **governance & audit layer** enforces DPDP compliance — consent registry, access logs, and automatic purge. The same camera feeds also serve a **crowd-analytics co-tenant** (density heatmaps, stampede early-warning), which is the state's primary motivation and a natural shared platform.

**③ Consumers.** A control-room **dashboard** (live map, camera wall, active cases), the **family/citizen app** ("your relative was seen at Ramkund Ghat, CAM-02, 14:32 — here's the route to the reunion point"), **police and lost-found booths** that dispatch volunteers and verify identity, and the **disaster-management cell** that consumes the shared crowd analytics.

The prototype's `backend_reference.py` implements the heart of layer ② — `/enroll`, `/search`, `/watchlist`, `/stats` over SCRFD + ArcFace + FAISS — so the architecture is not just a diagram but runnable code.

---

## 5. The prototype in this package

Two artefacts demonstrate the design end-to-end:

**`index.html` — a zero-install browser demo.** It runs a complete, real face-recognition pipeline in the browser (TensorFlow.js + face-api.js): register a missing person from a photo (or a sample face), then drop crowd photos/videos into a 12-tile simulated Kumbh camera wall and watch DRISHTI detect every face, match against the watch-list, draw boxes, fire a green "located" alert, and log the sighting with camera, time, and confidence. A command dashboard shows live counters next to the real Nashik 2027 figures. It is built for a hackathon demo: open it, register a face, find that face in a crowd, done.

**`backend_reference.py` — the production-style backend.** The same logic with the real stack — SCRFD + ArcFace (InsightFace) + FAISS — behind a FastAPI service with interactive Swagger docs. This is what would actually scale, by swapping CPU models for GPU (`onnxruntime-gpu`, `faiss-gpu`), the manual upload for DeepStream RTSP ingest, and in-process FAISS for Milvus.

The demo deliberately simplifies (128-D descriptors, linear scan, manual frame upload, synthetic sample faces) so it runs anywhere; the report and diagrams document every step from demo to production.

---

## 6. Accuracy, failure modes, and how to handle them

Face recognition in a Kumbh crowd is *hard mode*: harsh sun and shadow on the ghats, faces wet from bathing, ash-smeared sadhus, head coverings, extreme density and occlusion, motion blur, and a population with relatively few enrolled reference photos. Honest engineering means designing for failure:

- **Threshold tuning is a safety decision.** A loose threshold finds more people but produces false matches that waste volunteer time and risk misidentifying strangers; a strict threshold is precise but misses people. DRISHTI exposes this as an operator control and defaults to *balanced*, with **a mandatory human confirmation step** before any family is dispatched. The model proposes; a person decides.

- **Children are a special, higher-priority case** — and also harder (fewer reference photos, faster appearance change). They get the highest-priority SLA, and DRISHTI pairs face matching with clothing/colour descriptors and last-seen location to compensate.

- **Demographic bias is real.** Face models can perform unevenly across skin tone, age, and gender. The system must be evaluated on a representative Indian-population test set before deployment, and the human-confirmation step is the backstop against acting on a biased false positive.

- **Quality gating.** Low-quality detections (tiny, blurred, extreme-angle faces) are filtered before matching to cut false alarms.

- **Graceful degradation.** Where face recognition fails, the system still narrows search to a zone and time window, which is itself enormously valuable to a searching family — it turns "lost somewhere in 25 million people" into "last seen near Ramkund 20 minutes ago."

---

## 7. Privacy, ethics, and the law

A face-matching system over millions of pilgrims is powerful and, if misused, dangerous. DRISHTI is deliberately scoped as **opt-in reunification, not blanket surveillance**, and is designed around India's **Digital Personal Data Protection (DPDP) Act, 2023**.

The guiding principles:

- **Consent and purpose limitation.** The system matches *only* against photos that a family member has explicitly submitted to find a specific missing person. The DPDP Act requires that consent for biometric data be specific and unbundled; DRISHTI's enrollment captures exactly that. Live crowd faces are embedded transiently for the sole purpose of matching against the consented watch-list.

- **Data minimisation.** Non-matching faces are never stored — their embeddings are computed and immediately discarded. Raw video stays at the edge; only vectors and match metadata move centrally.

- **Automatic deletion.** All watch-list embeddings and match logs are purged at the close of the mela. The DPDP Act mandates deletion once the processing purpose is fulfilled.

- **Human oversight and auditability.** Every match is operator-confirmed; every access is logged. This addresses the central criticism of police facial recognition in India — that broad state exemptions under the Act risk function-creep. DRISHTI's answer is technical and procedural constraints that make function-creep difficult: a system that can only search consented missing-person photos and that deletes itself afterwards.

It is worth being candid that civil-society groups (e.g. the Internet Freedom Foundation) have urged caution and even moratoria on facial recognition in India, precisely because of weak guardrails. A credible system must treat those concerns as design requirements, not obstacles — which is why governance is a first-class layer in the architecture, not an afterthought.

---

## 8. Impact and KPIs

Success is measured in reunions and time, not in faces scanned:

- **Median time-to-reunion** for reported missing persons (target: minutes, not hours).
- **Percentage of reported missing persons located** via the system.
- **Children located** (highest-priority metric).
- **False-positive rate** at the operating threshold (kept low via human confirmation).
- **Coverage**: fraction of reported cases for which at least one camera sighting was produced.
- **Equity**: matching accuracy parity across demographic groups.

Even modest performance is transformative: turning a multi-hour PA-system search into a sub-15-minute, location-pinned reunion, at a gathering where simply *knowing the zone and time* a relative was last seen is life-changing for a panicked family.

---

## 9. Roadmap

1. **Prototype (this package)** — browser demo + reference backend proving the detect→embed→match→alert loop. ✔
2. **Pilot** — deploy on a bounded camera cluster (e.g. the Ramkund ghats) during a smaller bathing date; integrate with one Bhula-Bhatka booth; tune thresholds on real conditions.
3. **Scale-out** — DeepStream edge nodes across all 4,011 cameras + drones; FAISS→Milvus; integrate with the state "Kumbh AI Stack"; launch the family app.
4. **Hardening** — bias audit on representative data, full DPDP governance layer, load testing for peak-day (~2.5 crore footfall), 24×7 ops with auto-failover.
5. **Reuse** — the same platform serves future melas and other mass gatherings; the crowd-analytics tenant doubles as stampede early-warning.

---

## Sources

- [Nashik–Trimbakeshwar Simhastha — Wikipedia](https://en.wikipedia.org/wiki/Nashik-Trimbakeshwar_Simhastha)
- [AI-Based Security System Deployed for Nashik Kumbh Mela; 4,011 CCTV Cameras and 18 Drones — MahaENews](https://en.mahaenews.com/latest-news/ai-based-security-system-deployed-for-nashik-kumbh-mela-4011-cctv-cameras-and-18-drones-to-be-installed/)
- [With AI-led management systems in the works, Maharashtra plans 'most technologically advanced Kumbh yet' — ThePrint](https://theprint.in/india/with-ai-led-management-systems-in-the-works-maharashtra-plans-most-technologically-advanced-kumbh-yet/2916082/)
- [Kumbh Mela 2027: 3,000 RPF Personnel & AI Surveillance — Free Press Journal](https://www.freepressjournal.in/pune/kumbh-mela-2027-3000-rpf-personnel-ai-surveillance-to-secure-railways-in-nashik)
- [Nashik Kumbh Mela 2027 Crowd Zones Guide](https://kumbhmela.org.in/nashik-kumbh-mela-2027-crowd-zones-guide)
- [Cutting-edge AI to find missing relatives at ancient Kumbh Mela — News India Times](https://newsindiatimes.com/cutting-edge-ai-to-find-missing-relatives-at-ancient-kumbh-mela/)
- [Prayagraj to turn into fortress ahead of Maha Kumbh: 50,000 personnel, 3,000 CCTVs, drones — ThePrint](https://theprint.in/india/prayagraj-to-turn-into-fortress-ahead-of-maha-kumbh-50000-security-personnel-3000-cctvs-drones/2433716/)
- [Maha Kumbh 2025: A High-Tech Approach To Lost And Found Systems — NewsX](https://www.newsx.com/maha-kumbh-2025/maha-kumbh-2025-a-high-tech-approach-to-lost-and-found-systems/)
- [AI and Facial Recognition to Manage 400M Pilgrims at India's 2025 Mahakumbh — ID Tech](https://idtechwire.com/ai-and-facial-recognition-to-manage-400m-pilgrims-at-indias-2025-mahakumbh-festival/)
- [InsightFace — open-source face detection & recognition](https://www.insightface.ai/)
- [face-reidentification: SCRFD + ArcFace + FAISS — GitHub](https://github.com/yakhyo/face-reidentification)
- [face-recognition-deepstream: RetinaFace + ArcFace on DeepStream — GitHub](https://github.com/zhouyuchong/face-recognition-deepstream)
- [Regulation of Biometric Data under the DPDP Act, 2023 — King Stubb & Kasiva](https://ksandk.com/data-protection-and-data-privacy/regulation-of-biometric-data-under-the-dpdp-act/)
- [Facial recognition and India's DPDP Act — Law.asia](https://law.asia/facial-recognition-compliance/)
- [The 2026 Guide to Facial Recognition and Privacy in India — HyperVerge](https://hyperverge.co/blog/facial-recognition-privacy-india/)

*This report accompanies the DRISHTI prototype (`index.html`, `backend_reference.py`), architecture diagrams, and pitch deck.*
