"""
Drishti — AI backend (Render / any Python host)
================================================
Single FastAPI service covering every server-side AI endpoint.
All API keys live in environment variables — never in code.

Endpoints
  GET  /api/health          all-services status
  POST /api/translate       Sarvam AI  voice-to-voice  (ASR→NMT→TTS)
  POST /api/bhashini        Bhashini   voice-to-voice  (ASR→NMT→TTS, pending approval)
  POST /api/parse-search    Claude     free text → search filters
  POST /api/parse-intake    Claude     dictated desc  → intake fields

Run locally
  pip install -r requirements-server.txt
  uvicorn server:app --reload --port 8000
  open http://localhost:8000/docs
"""

import base64
import io
import json
import os
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Shared vocab (generated from CSV data) ───────────────────────────────────
_vocab_path = Path(__file__).parent / "api" / "vocab.json"
try:
    _vocab = json.loads(_vocab_path.read_text(encoding="utf-8"))
    LANGS      = _vocab.get("languages", [])
    SEEN_LOCS  = _vocab.get("seen_locations", [])
    CENTERS    = _vocab.get("centers", [])
except Exception:
    LANGS = SEEN_LOCS = CENTERS = []

AGES     = ["0-12", "13-17", "18-40", "41-60", "61-70", "71-80", "80+"]
GENDERS  = ["Female", "Male", "Unknown"]
STATUSES = ["Pending", "Reunited", "Unresolved", "Transferred to hospital"]

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Drishti AI API",
    description="Voice translation (Sarvam / Bhashini) + Claude NL parsing for the Kumbh Mela missing-person system.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / response models ─────────────────────────────────────────────────
class VoiceRequest(BaseModel):
    audio:       str          # base64-encoded 16 kHz mono WAV
    source_lang: str = "hi"
    target_lang: str = "en"
    gender:      str = "female"

class TextRequest(BaseModel):
    text: str

# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["ops"])
def health():
    bhashini_uid = os.environ.get("BHASHINI_USER_ID", "")
    return {
        "status": "ok",
        "services": {
            "sarvam":   bool(os.environ.get("SARVAM_API_KEY")),
            "bhashini": bool(bhashini_uid and bhashini_uid != "your_user_id_here"),
            "claude":   bool(os.environ.get("ANTHROPIC_API_KEY")),
        },
        "vocab": {"languages": len(LANGS), "locations": len(SEEN_LOCS), "centers": len(CENTERS)},
    }

# ─────────────────────────────────────────────────────────────────────────────
# Sarvam AI voice-to-voice
# ─────────────────────────────────────────────────────────────────────────────
_SARVAM_BASE = "https://api.sarvam.ai"
_SARVAM_LANG = {
    "hi": "hi-IN", "bn": "bn-IN", "ta": "ta-IN", "te": "te-IN",
    "mr": "mr-IN", "gu": "gu-IN", "kn": "kn-IN", "ml": "ml-IN",
    "pa": "pa-IN", "or": "od-IN", "as": "as-IN", "ur": "ur-IN",
    "en": "en-IN",
}
_SARVAM_SPEAKER = {"female": "ritu", "male": "aditya"}


def _sarvam_headers():
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        raise HTTPException(503, "SARVAM_API_KEY not configured on server")
    return {"api-subscription-key": key}


def _sarvam_asr(audio_bytes: bytes, lang: str) -> str:
    r = requests.post(
        f"{_SARVAM_BASE}/speech-to-text",
        headers=_sarvam_headers(),
        files={
            "file":          ("audio.wav", io.BytesIO(audio_bytes), "audio/wav"),
            "model":         (None, "saaras:v3"),
            "mode":          (None, "transcribe"),
            "language_code": (None, lang),
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("transcript", "")


def _sarvam_translate(text: str, src: str, tgt: str) -> str:
    r = requests.post(
        f"{_SARVAM_BASE}/translate",
        headers={**_sarvam_headers(), "Content-Type": "application/json"},
        json={"input": text, "source_language_code": src,
              "target_language_code": tgt, "model": "sarvam-translate:v1", "mode": "formal"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("translated_text", "")


def _sarvam_tts(text: str, lang: str, gender: str) -> str:
    r = requests.post(
        f"{_SARVAM_BASE}/text-to-speech",
        headers={**_sarvam_headers(), "Content-Type": "application/json"},
        json={"text": text, "target_language_code": lang, "model": "bulbul:v3",
              "speaker": _SARVAM_SPEAKER.get(gender, "ritu"), "speech_sample_rate": 8000},
        timeout=20,
    )
    r.raise_for_status()
    audios = r.json().get("audios", [])
    return audios[0] if audios else ""


@app.post("/api/translate", tags=["voice"])
def translate(req: VoiceRequest):
    """Sarvam AI: WAV audio → transcript + translation + synthesised audio (base64 WAV)."""
    src = _SARVAM_LANG.get(req.source_lang, req.source_lang)
    tgt = _SARVAM_LANG.get(req.target_lang, req.target_lang)
    try:
        audio_bytes = base64.b64decode(req.audio)
        transcript  = _sarvam_asr(audio_bytes, src)
        if not transcript:
            raise HTTPException(422, "ASR returned empty transcript — speak more clearly")
        translation = _sarvam_translate(transcript, src, tgt)
        audio_out   = _sarvam_tts(translation, tgt, req.gender)
        return {"transcript": transcript, "translation": translation, "audio": audio_out}
    except HTTPException:
        raise
    except requests.HTTPError as e:
        raise HTTPException(502, f"Sarvam API {e.response.status_code}: {e.response.text[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# Bhashini voice-to-voice
# ─────────────────────────────────────────────────────────────────────────────
_BHASHINI_CONFIG_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"


def _bhashini_cfg_headers():
    uid = os.environ.get("BHASHINI_USER_ID", "")
    key = os.environ.get("BHASHINI_API_KEY", "")
    if not uid or uid == "your_user_id_here" or not key:
        raise HTTPException(503, "Bhashini credentials not configured (pending approval)")
    return {"userID": uid, "ulcaApiKey": key, "Content-Type": "application/json"}


def _bhashini_pipeline_config(src: str, tgt: str) -> dict:
    r = requests.post(
        _BHASHINI_CONFIG_URL,
        headers=_bhashini_cfg_headers(),
        json={
            "pipelineTasks": [
                {"taskType": "asr",        "config": {"language": {"sourceLanguage": src}}},
                {"taskType": "translation", "config": {"language": {"sourceLanguage": src, "targetLanguage": tgt}}},
                {"taskType": "tts",        "config": {"language": {"sourceLanguage": tgt}}},
            ],
            "pipelineRequestConfig": {
                "pipelineId": os.environ.get("BHASHINI_PIPELINE_ID", "64392f96daac500b55c543cd"),
            },
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _bhashini_run(cfg: dict, audio_b64: str, src: str, tgt: str, gender: str) -> dict:
    pcfg     = cfg["pipelineResponseConfig"][0]
    callback = pcfg["callbackUrl"]
    inf_key  = pcfg["inferenceApiKey"]["value"]
    svc      = {t["taskType"]: t["config"]["serviceId"] for t in pcfg["taskSequence"]}
    r = requests.post(
        callback,
        headers={"Authorization": inf_key, "Content-Type": "application/json"},
        json={
            "pipelineTasks": [
                {"taskType": "asr",        "config": {"language": {"sourceLanguage": src}, "serviceId": svc["asr"], "audioFormat": "wav", "samplingRate": 16000}},
                {"taskType": "translation", "config": {"language": {"sourceLanguage": src, "targetLanguage": tgt}, "serviceId": svc["translation"]}},
                {"taskType": "tts",        "config": {"language": {"sourceLanguage": tgt}, "serviceId": svc["tts"], "gender": gender, "samplingRate": 8000}},
            ],
            "inputData": {"audio": [{"audioContent": audio_b64}]},
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


@app.post("/api/bhashini", tags=["voice"])
def bhashini(req: VoiceRequest):
    """Bhashini: WAV audio → transcript + translation + synthesised audio (base64)."""
    try:
        cfg    = _bhashini_pipeline_config(req.source_lang, req.target_lang)
        result = _bhashini_run(cfg, req.audio, req.source_lang, req.target_lang, req.gender)
        out = {}
        for task in result.get("pipelineResponse", []):
            tt = task["taskType"]
            if tt == "asr":
                out["transcript"]  = task.get("output", [{}])[0].get("source", "")
            elif tt == "translation":
                out["translation"] = task.get("output", [{}])[0].get("target", "")
            elif tt == "tts":
                out["audio"]       = task.get("audio", [{}])[0].get("audioContent", "")
        return out
    except HTTPException:
        raise
    except requests.HTTPError as e:
        raise HTTPException(502, f"Bhashini API {e.response.status_code}: {e.response.text[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# Claude AI — NL parsing
# ─────────────────────────────────────────────────────────────────────────────
def _claude_client():
    import anthropic
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic()


def _enum(values):
    return {"type": "string", "enum": ["", *values]}


_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "name":   {"type": "string", "description": "Name if stated, else ''"},
        "gender": _enum(GENDERS),
        "age":    {**_enum(AGES), "description": "Closest age band, else ''"},
        "lang":   _enum(LANGS),
        "seen":   {**_enum(SEEN_LOCS), "description": "Closest known last-seen location, else ''"},
        "status": _enum(STATUSES),
        "notes":  {"type": "string", "description": "One short line on what was inferred vs. stated"},
    },
    "required": ["name", "gender", "age", "lang", "seen", "status", "notes"],
    "additionalProperties": False,
}

_INTAKE_SCHEMA = {
    "type": "object",
    "properties": {
        "gender": _enum(GENDERS),
        "age":    _enum(AGES),
        "lang":   _enum(LANGS),
        "seen":   _enum(SEEN_LOCS),
        "desc":   {"type": "string", "description": "Clean one-line physical description: clothing, marks, build"},
        "notes":  {"type": "string", "description": "One short line on confidence / what was unclear"},
    },
    "required": ["gender", "age", "lang", "seen", "desc", "notes"],
    "additionalProperties": False,
}

_SEARCH_SYSTEM = (
    "You turn a family's free-text description of a missing person into structured "
    "search filters for a lost-and-found registry at the Nashik Kumbh Mela. "
    "Extract only what the text supports; use an empty string for anything not stated. "
    "Map every value to the closest allowed option. Do not invent a name, gender, or "
    "location that was not implied. Keep 'notes' to one short sentence."
)

_INTAKE_SYSTEM = (
    "You are helping a kiosk volunteer at a Kumbh Mela lost-and-found center turn a "
    "spoken description of a missing or found person into structured intake fields. "
    "Many people have no phone and cannot read, so capture whatever attributes are "
    "described. Use an empty string for anything not stated; never guess identity. "
    "'desc' should be a clean one-line summary of clothing and distinguishing marks."
)


def _claude_extract(system: str, schema: dict, text: str) -> dict:
    text = text.strip()
    if not text:
        raise HTTPException(400, "Empty input")
    model = os.environ.get("DRISHTI_MODEL", "claude-haiku-4-5-20251001")
    try:
        resp = _claude_client().messages.create(
            model=model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": text}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
    except Exception as e:
        raise HTTPException(502, f"Claude API error: {e}")
    raw = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(raw)


@app.post("/api/parse-search", tags=["ai"])
def parse_search(req: TextRequest):
    """Claude: family's free text → structured search filters (gender, age, lang, seen, ...)."""
    return _claude_extract(_SEARCH_SYSTEM, _SEARCH_SCHEMA, req.text)


@app.post("/api/parse-intake", tags=["ai"])
def parse_intake(req: TextRequest):
    """Claude: volunteer's dictated description → intake fields (gender, age, desc, ...)."""
    return _claude_extract(_INTAKE_SYSTEM, _INTAKE_SCHEMA, req.text)


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"\n  Drishti API → http://localhost:{port}")
    print(f"  Swagger UI  → http://localhost:{port}/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
