"""
Vercel serverless function — POST /api/bhashini
Bhashini voice-to-voice pipeline: ASR → NMT → TTS
Hides BHASHINI_USER_ID / BHASHINI_API_KEY from the browser.
Activate once Bhashini approves your registration.
"""
import json
import os
import requests
from http.server import BaseHTTPRequestHandler

CONFIG_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"


def _cfg_headers():
    return {
        "userID":     os.environ.get("BHASHINI_USER_ID", ""),
        "ulcaApiKey": os.environ.get("BHASHINI_API_KEY", ""),
        "Content-Type": "application/json",
    }


def _pipeline_config(src: str, tgt: str) -> dict:
    r = requests.post(
        CONFIG_URL,
        headers=_cfg_headers(),
        json={
            "pipelineTasks": [
                {"taskType": "asr",        "config": {"language": {"sourceLanguage": src}}},
                {"taskType": "translation", "config": {"language": {"sourceLanguage": src, "targetLanguage": tgt}}},
                {"taskType": "tts",        "config": {"language": {"sourceLanguage": tgt}}},
            ],
            "pipelineRequestConfig": {"pipelineId": os.environ.get("BHASHINI_PIPELINE_ID", "64392f96daac500b55c543cd")},
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _run_pipeline(cfg: dict, audio_b64: str, src: str, tgt: str, gender: str) -> dict:
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
        uid = os.environ.get("BHASHINI_USER_ID", "")
        key = os.environ.get("BHASHINI_API_KEY", "")
        self._json(200, {
            "status": "ok", "provider": "bhashini",
            "credentials_set": bool(uid and key and uid != "your_user_id_here"),
        })

    def do_POST(self):
        uid = os.environ.get("BHASHINI_USER_ID", "")
        key = os.environ.get("BHASHINI_API_KEY", "")
        if not uid or not key or uid == "your_user_id_here":
            return self._json(503, {"error": "Bhashini credentials not configured"})

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode()) if length else {}

        audio_b64   = body.get("audio")
        source_lang = body.get("source_lang", "hi")
        target_lang = body.get("target_lang", "en")
        gender      = body.get("gender", "female")

        if not audio_b64:
            return self._json(400, {"error": "No audio provided"})

        try:
            cfg    = _pipeline_config(source_lang, target_lang)
            result = _run_pipeline(cfg, audio_b64, source_lang, target_lang, gender)

            out = {}
            for task in result.get("pipelineResponse", []):
                tt = task["taskType"]
                if tt == "asr":
                    out["transcript"]  = task.get("output", [{}])[0].get("source", "")
                elif tt == "translation":
                    out["translation"] = task.get("output", [{}])[0].get("target", "")
                elif tt == "tts":
                    out["audio"]       = task.get("audio", [{}])[0].get("audioContent", "")

            self._json(200, out)
        except requests.HTTPError as e:
            self._json(502, {"error": f"Bhashini API {e.response.status_code}: {e.response.text[:200]}"})
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
