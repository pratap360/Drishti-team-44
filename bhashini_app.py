#!/usr/bin/env python3
"""Bhashini voice-to-voice translation endpoint.

Pipeline: ASR (speech→text) → NMT (translate) → TTS (text→speech)
All three steps happen in a single Bhashini pipeline call.

Register at https://bhashini.gov.in/ulca to get credentials.
Set BHASHINI_USER_ID and BHASHINI_API_KEY in .env before running.
"""

import os
import requests
from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

USER_ID     = os.environ.get("BHASHINI_USER_ID", "")
API_KEY     = os.environ.get("BHASHINI_API_KEY", "")
PIPELINE_ID = os.environ.get("BHASHINI_PIPELINE_ID", "64392f96daac500b55c543cd")

CONFIG_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"


def get_pipeline_config(source_lang: str, target_lang: str) -> dict:
    """Fetch service IDs and callback URL for the given language pair."""
    resp = requests.post(
        CONFIG_URL,
        headers={
            "userID": USER_ID,
            "ulcaApiKey": API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "pipelineTasks": [
                {"taskType": "asr",         "config": {"language": {"sourceLanguage": source_lang}}},
                {"taskType": "translation",  "config": {"language": {"sourceLanguage": source_lang, "targetLanguage": target_lang}}},
                {"taskType": "tts",          "config": {"language": {"sourceLanguage": target_lang}}},
            ],
            "pipelineRequestConfig": {"pipelineId": PIPELINE_ID},
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def run_pipeline(config: dict, audio_b64: str, source_lang: str, target_lang: str, gender: str) -> dict:
    """Execute the ASR→NMT→TTS pipeline with the recorded audio."""
    pipeline_cfg = config["pipelineResponseConfig"][0]
    callback_url  = pipeline_cfg["callbackUrl"]
    inference_key = pipeline_cfg["inferenceApiKey"]["value"]

    # Map service IDs from config response
    service = {t["taskType"]: t["config"]["serviceId"] for t in pipeline_cfg["taskSequence"]}

    resp = requests.post(
        callback_url,
        headers={"Authorization": inference_key, "Content-Type": "application/json"},
        json={
            "pipelineTasks": [
                {
                    "taskType": "asr",
                    "config": {
                        "language":    {"sourceLanguage": source_lang},
                        "serviceId":   service["asr"],
                        "audioFormat": "wav",
                        "samplingRate": 16000,
                    },
                },
                {
                    "taskType": "translation",
                    "config": {
                        "language":  {"sourceLanguage": source_lang, "targetLanguage": target_lang},
                        "serviceId": service["translation"],
                    },
                },
                {
                    "taskType": "tts",
                    "config": {
                        "language":    {"sourceLanguage": target_lang},
                        "serviceId":   service["tts"],
                        "gender":      gender,
                        "samplingRate": 8000,
                    },
                },
            ],
            "inputData": {"audio": [{"audioContent": audio_b64}]},
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


@app.route("/")
def index():
    return send_file("bhashini_ui.html")


@app.route("/api/translate", methods=["POST"])
def translate():
    if not USER_ID or not API_KEY or USER_ID == "your_user_id_here":
        return jsonify({"error": "Bhashini credentials not configured. Set BHASHINI_USER_ID and BHASHINI_API_KEY in .env"}), 503

    body = request.get_json(silent=True) or {}
    audio_b64   = body.get("audio")
    source_lang = body.get("source_lang", "hi")
    target_lang = body.get("target_lang", "en")
    gender      = body.get("gender", "female")

    if not audio_b64:
        return jsonify({"error": "No audio provided"}), 400

    try:
        config = get_pipeline_config(source_lang, target_lang)
        result = run_pipeline(config, audio_b64, source_lang, target_lang, gender)

        output = {}
        for task in result.get("pipelineResponse", []):
            tt = task["taskType"]
            if tt == "asr":
                output["transcript"] = task.get("output", [{}])[0].get("source", "")
            elif tt == "translation":
                output["translation"] = task.get("output", [{}])[0].get("target", "")
            elif tt == "tts":
                output["audio"] = task.get("audio", [{}])[0].get("audioContent", "")

        return jsonify(output)

    except requests.HTTPError as e:
        return jsonify({"error": f"Bhashini API error {e.response.status_code}: {e.response.text[:300]}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "credentials_set": bool(USER_ID and API_KEY and USER_ID != "your_user_id_here"),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n  Bhashini UI →  http://localhost:{port}")
    print(f"  Credentials:   {'✓ configured' if USER_ID and USER_ID != 'your_user_id_here' else '✗ fill BHASHINI_USER_ID + BHASHINI_API_KEY in .env'}\n")
    app.run(debug=True, port=port)
