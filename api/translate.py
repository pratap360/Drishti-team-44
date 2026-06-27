"""
Vercel serverless function — POST /api/translate
Sarvam AI voice-to-voice pipeline: ASR → NMT → TTS
Hides SARVAM_API_KEY from the browser.
"""
import json
import os
import io
import base64
import requests
from http.server import BaseHTTPRequestHandler

BASE = "https://api.sarvam.ai"

LANG_CODE = {
    "hi": "hi-IN", "bn": "bn-IN", "ta": "ta-IN", "te": "te-IN",
    "mr": "mr-IN", "gu": "gu-IN", "kn": "kn-IN", "ml": "ml-IN",
    "pa": "pa-IN", "or": "od-IN", "as": "as-IN", "ur": "ur-IN",
    "en": "en-IN",
}
DEFAULT_SPEAKER = {"female": "ritu", "male": "aditya"}


def _auth():
    return {"api-subscription-key": os.environ.get("SARVAM_API_KEY", "")}


def _asr(audio_bytes: bytes, lang_bcp: str) -> str:
    r = requests.post(
        f"{BASE}/speech-to-text",
        headers=_auth(),
        files={
            "file":          ("audio.wav", io.BytesIO(audio_bytes), "audio/wav"),
            "model":         (None, "saaras:v3"),
            "mode":          (None, "transcribe"),
            "language_code": (None, lang_bcp),
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("transcript", "")


def _translate(text: str, src: str, tgt: str) -> str:
    r = requests.post(
        f"{BASE}/translate",
        headers={**_auth(), "Content-Type": "application/json"},
        json={"input": text, "source_language_code": src,
              "target_language_code": tgt, "model": "sarvam-translate:v1", "mode": "formal"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("translated_text", "")


def _tts(text: str, lang: str, gender: str) -> str:
    r = requests.post(
        f"{BASE}/text-to-speech",
        headers={**_auth(), "Content-Type": "application/json"},
        json={"text": text, "target_language_code": lang, "model": "bulbul:v3",
              "speaker": DEFAULT_SPEAKER.get(gender, "ritu"), "speech_sample_rate": 8000},
        timeout=20,
    )
    r.raise_for_status()
    audios = r.json().get("audios", [])
    return audios[0] if audios else ""


def _cors(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.end_headers()

    def do_GET(self):
        key_ok = bool(os.environ.get("SARVAM_API_KEY"))
        self._json(200, {"status": "ok", "provider": "sarvam", "credentials_set": key_ok})

    def do_POST(self):
        api_key = os.environ.get("SARVAM_API_KEY", "")
        if not api_key:
            return self._json(503, {"error": "SARVAM_API_KEY not configured on server"})

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode()) if length else {}

        audio_b64   = body.get("audio")
        source_lang = body.get("source_lang", "hi")
        target_lang = body.get("target_lang", "en")
        gender      = body.get("gender", "female")

        if not audio_b64:
            return self._json(400, {"error": "No audio provided"})

        src_bcp = LANG_CODE.get(source_lang, source_lang)
        tgt_bcp = LANG_CODE.get(target_lang, target_lang)

        try:
            audio_bytes = base64.b64decode(audio_b64)
            transcript  = _asr(audio_bytes, src_bcp)
            if not transcript:
                return self._json(422, {"error": "ASR returned empty transcript"})
            translation = _translate(transcript, src_bcp, tgt_bcp)
            audio_out   = _tts(translation, tgt_bcp, gender)
            self._json(200, {"transcript": transcript, "translation": translation, "audio": audio_out})
        except requests.HTTPError as e:
            self._json(502, {"error": f"Sarvam API {e.response.status_code}: {e.response.text[:200]}"})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        _cors(self)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass
