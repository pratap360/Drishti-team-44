#!/usr/bin/env bash
#
# demo_setup.sh — one-shot setup for the Qdrant-backed CCTV demo.
#
#   1. venv + face-backend deps (incl. qdrant-client)
#   2. start backend_reference.py on :8100 (owns Qdrant; embedded ./qdrant_data
#      by default — set QDRANT_URL to use a Qdrant server instead)
#   3. seed sightings + frames from the sample crowd video (and print the query frame)
#   4. enroll a few sample missing persons into Qdrant (persons collection)
#   5. start live_feed.py — streams the crowd video as a *live* camera (real-time)
#
# Run:  bash demo_setup.sh
# Stop: kill "$(cat .backend.pid)" "$(cat .feed.pid)" 2>/dev/null
#
set -euo pipefail
cd "$(dirname "$0")"

VIDEO="sample_footage/street_crossing.webm"
PORT=8100
BACKEND="http://localhost:${PORT}"
ZONE="Zone Area 30"
START="09:00"

[ -f "$VIDEO" ] || { echo "Missing $VIDEO — see the README 'Sample footage' section."; exit 1; }

# 1. venv + deps -----------------------------------------------------------
[ -d venv ] || python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
echo "→ installing deps (first run only)…"
pip install -q --upgrade pip
pip install -q -r requirements-face.txt

# 2. start backend if not already up --------------------------------------
if curl -sf -m 2 "${BACKEND}/health" >/dev/null 2>&1; then
  echo "→ backend already running on :${PORT}"
else
  echo "→ starting backend_reference.py on :${PORT} (Qdrant ${QDRANT_URL:-embedded ./qdrant_data}; logs → backend.log)…"
  nohup python3 backend_reference.py > backend.log 2>&1 &
  echo $! > .backend.pid
fi

printf "→ waiting for backend"
ready=""
for _ in $(seq 1 120); do          # up to ~4 min for first-run model download
  if curl -sf -m 2 "${BACKEND}/health" >/dev/null 2>&1; then ready=1; echo " — ready."; break; fi
  printf "."; sleep 2
done
[ -n "$ready" ] || { echo; echo "Backend did not come up — check backend.log"; exit 1; }

# 3. seed sightings + frames (batch pass over the clip) -------------------
echo "→ indexing ${VIDEO} as sightings + saving frames…"
rm -rf frames && mkdir -p frames
python3 ingest_video.py "$VIDEO" --camera Z30-C12 --zone "$ZONE" --start "$START" --save-frames frames/

# 4. enroll sample missing persons into Qdrant ----------------------------
echo "→ seeding sample missing persons (Qdrant persons collection)…"
python3 seed.py --frames-dir frames || echo "  (seed skipped — no detectable faces in picked frames)"

# 5. start the real-time live feed ----------------------------------------
if [ -f .feed.pid ] && kill -0 "$(cat .feed.pid)" 2>/dev/null; then
  echo "→ live feed already running (pid $(cat .feed.pid))"
else
  echo "→ starting live_feed.py (real-time crowd stream; logs → live_feed.log)…"
  nohup python3 live_feed.py "$VIDEO" \
        --zones "Zone Area 30,Zone Area 31,Zone Area 21,Zone Area 29,Zone Area 23,Zone Area 22" \
        --fps 3 --speed 4 > live_feed.log 2>&1 &
  echo $! > .feed.pid
fi

# 6. report ---------------------------------------------------------------
echo
echo "Status: $(curl -s "${BACKEND}/health")"
echo
echo "NEXT — open index.html → ⑥ CCTV trace, then:"
echo "   • Photo available?  → 'Photo contains the person'"
echo "   • Query photo       → upload the RECOMMENDED QUERY PHOTO printed above (frames/frame_XXX.jpg)"
echo "   • Last seen         → ${ZONE} / ${START}"
echo "   • Pull footage & search → candidates show 'live face match'; Confirm to track across zones."
echo
echo "Live feed keeps filling Qdrant in the background (tail -f live_feed.log)."
echo "Stop everything:  kill \$(cat .backend.pid) \$(cat .feed.pid) 2>/dev/null"
