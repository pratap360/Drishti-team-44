"""
Vercel serverless function — GET /api/health
Reports configured status of all server-side API keys.
"""
import json
import os
from http.server import BaseHTTPRequestHandler


def _cors(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.end_headers()

    def do_GET(self):
        bhashini_uid = os.environ.get("BHASHINI_USER_ID", "")
        body = json.dumps({
            "status": "ok",
            "services": {
                "sarvam":    bool(os.environ.get("SARVAM_API_KEY")),
                "bhashini":  bool(bhashini_uid and bhashini_uid != "your_user_id_here"),
                "claude":    bool(os.environ.get("ANTHROPIC_API_KEY")),
            },
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        _cors(self)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass
