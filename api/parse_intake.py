"""
Vercel serverless function — POST /api/parse_intake
Claude AI: volunteer's dictated description → structured intake fields.
Ported from DRISHTI-Kumbh-Finder/backend.py. Hides ANTHROPIC_API_KEY.
"""
import json
import os
from http.server import BaseHTTPRequestHandler

_VOCAB_PATH = os.path.join(os.path.dirname(__file__), "vocab.json")

def _load_vocab():
    try:
        with open(_VOCAB_PATH, encoding="utf-8") as f:
            v = json.load(f)
        return v.get("languages", []), v.get("seen_locations", [])
    except Exception:
        return [], []

LANGS, SEEN_LOCS = _load_vocab()
AGES    = ["0-12", "13-17", "18-40", "41-60", "61-70", "71-80", "80+"]
GENDERS = ["Female", "Male", "Unknown"]

def _enum(values):
    return {"type": "string", "enum": ["", *values]}

SCHEMA = {
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

SYSTEM = (
    "You are helping a kiosk volunteer at a Kumbh Mela lost-and-found center turn a "
    "spoken description of a missing or found person into structured intake fields. "
    "Many people have no phone and cannot read, so capture whatever attributes are "
    "described. Use an empty string for anything not stated; never guess identity. "
    "'desc' should be a clean one-line summary of clothing and distinguishing marks."
)


def _extract(text: str) -> dict:
    import anthropic
    model = os.environ.get("DRISHTI_MODEL", "claude-haiku-4-5-20251001")
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=512,
        system=SYSTEM,
        messages=[{"role": "user", "content": text}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def _cors(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.end_headers()

    def do_POST(self):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return self._json(503, {"error": "ANTHROPIC_API_KEY not configured"})

        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length).decode()) if length else {}
        text   = (body.get("text") or "").strip()

        if not text:
            return self._json(400, {"error": "Empty input"})

        try:
            self._json(200, _extract(text))
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
