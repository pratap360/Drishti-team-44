"""
DRISHTI — AI backend (Claude)
=============================
A small FastAPI service that adds two *optional, online* AI enhancements to the
otherwise fully-offline DRISHTI app. The browser never sees the API key — it
calls these endpoints, and only this server talks to Claude.

    POST /parse-search   natural language  -> structured search filters
                         "elderly woman in a green saree, speaks Marathi,
                          last seen near Ramkund" -> {gender, age, lang, seen, ...}
                         feeds the same matchScore() engine the UI already uses.

    POST /parse-intake   a volunteer's dictated free-text description
                         -> structured intake fields (gender / age band / language
                          / clothing & marks) for the kiosk report form.

    GET  /health         readiness + whether the key is configured.

-----------------------------------------------------------------------------
SECURITY — the API key lives ONLY on this server, never in the browser.
-----------------------------------------------------------------------------
The key is read from the ANTHROPIC_API_KEY environment variable. It is never
hardcoded, never returned to the client, and never embedded in index.html /
app_data.js (those are downloaded to every visitor's browser). Rotate the key
in the Anthropic Console if it is ever exposed.

-----------------------------------------------------------------------------
SETUP
-----------------------------------------------------------------------------
    python3 -m venv venv && source venv/bin/activate
    pip install -r requirements-backend.txt

    export ANTHROPIC_API_KEY=sk-ant-...        # your key — set in the shell, not in code
    python3 backend.py                          # serves on http://localhost:8000
    # open http://localhost:8000/docs           # interactive Swagger UI

The offline app keeps working with no backend; these endpoints are a bonus that
activates only when this server is reachable.
"""
import json
import os

try:
    import anthropic
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
except ImportError as e:  # let the file be read even without deps installed
    print(f"[warn] missing dependency: {e}. pip install -r requirements-backend.txt")

# Default to the latest, most capable model. Extraction is cheap; override with
# DRISHTI_MODEL=claude-haiku-4-5 if you want lower latency/cost.
MODEL = os.environ.get("DRISHTI_MODEL", "claude-opus-4-8")

# --------------------------------------------------------------------------- #
#  Enum vocabulary — loaded from app_data.js so the backend stays in lock-step
#  with the dataset the UI uses. Claude is constrained to these exact values,
#  so its output drops straight into the existing matchScore() filters.
# --------------------------------------------------------------------------- #
AGES = ["0-12", "13-17", "18-40", "41-60", "61-70", "71-80", "80+"]
GENDERS = ["Female", "Male", "Unknown"]
STATUSES = ["Pending", "Reunited", "Unresolved", "Transferred to hospital"]


def _load_vocab():
    """Pull the distinct languages, last-seen locations and centers out of the
    generated app_data.js (which is `window.KMP = {...};`)."""
    path = os.path.join(os.path.dirname(__file__), "app_data.js")
    try:
        txt = open(path, encoding="utf-8").read()
        data = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        persons = data.get("persons", [])
        langs = sorted({p["lang"] for p in persons if p.get("lang")})
        seens = sorted({p["seen"] for p in persons if p.get("seen")})
        centers = sorted({p["center"] for p in persons if p.get("center")})
        return langs, seens, centers
    except Exception as e:  # backend still boots; enums just fall back to empty
        print(f"[warn] could not load vocab from app_data.js: {e}")
        return [], [], []


LANGS, SEEN_LOCS, CENTERS = _load_vocab()


def _enum(values, allow_blank=True):
    """A JSON-schema string field constrained to `values` (plus '' for unknown)."""
    return {"type": "string", "enum": (["", *values] if allow_blank else values)}


SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Name if stated, else ''"},
        "gender": _enum(GENDERS),
        "age": {**_enum(AGES), "description": "Closest age band, else ''"},
        "lang": _enum(LANGS),
        "seen": {**_enum(SEEN_LOCS), "description": "Closest known last-seen location, else ''"},
        "status": _enum(STATUSES),
        "notes": {"type": "string", "description": "One short line on what was inferred vs. stated"},
    },
    "required": ["name", "gender", "age", "lang", "seen", "status", "notes"],
    "additionalProperties": False,
}

INTAKE_SCHEMA = {
    "type": "object",
    "properties": {
        "gender": _enum(GENDERS),
        "age": _enum(AGES),
        "lang": _enum(LANGS),
        "seen": _enum(SEEN_LOCS),
        "desc": {"type": "string", "description": "Clean one-line physical description: clothing, marks, build"},
        "notes": {"type": "string", "description": "One short line on confidence / what was unclear"},
    },
    "required": ["gender", "age", "lang", "seen", "desc", "notes"],
    "additionalProperties": False,
}

SEARCH_SYSTEM = (
    "You turn a family's free-text description of a missing person into structured "
    "search filters for a lost-and-found registry at the Nashik Kumbh Mela. "
    "Extract only what the text supports; use an empty string for anything not stated. "
    "Map every value to the closest allowed option (e.g. 'old woman' -> age band, "
    "a place name -> the nearest known last-seen location). Do not invent a name, "
    "gender, or location that was not implied. Keep 'notes' to one short sentence."
)
INTAKE_SYSTEM = (
    "You are helping a kiosk volunteer at a Kumbh Mela lost-and-found center turn a "
    "spoken description of a missing or found person into structured intake fields. "
    "Many people have no phone and cannot read, so capture whatever attributes are "
    "described. Use an empty string for anything not stated; never guess identity. "
    "'desc' should be a clean one-line summary of clothing and distinguishing marks."
)


# --------------------------------------------------------------------------- #
#  App
# --------------------------------------------------------------------------- #
app = FastAPI(title="DRISHTI — Claude AI backend",
              description="Natural-language search & intake parsing for DRISHTI.")

# The app is opened from a file:// page (origin 'null') or a local static server,
# so allow any origin. The key never leaves this server regardless of origin.
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

_client = None


def client():
    """Lazily build the Anthropic client. Errors clearly if the key is missing —
    we never fall back to a hardcoded key."""
    global _client
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set on the server. "
                                 "Export it in the shell before starting backend.py.")
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    return _client


class TextIn(BaseModel):
    text: str


def extract(system: str, schema: dict, user_text: str) -> dict:
    """One constrained Claude call: free text -> JSON validated against `schema`."""
    text = (user_text or "").strip()
    if not text:
        raise HTTPException(400, "Empty input.")
    try:
        resp = client().messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": text}],
            # Constrain the response to our schema so it maps 1:1 onto the UI filters.
            output_config={"effort": "low",
                           "format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.AuthenticationError:
        raise HTTPException(401, "Invalid ANTHROPIC_API_KEY. Rotate it in the Anthropic Console.")
    except anthropic.RateLimitError:
        raise HTTPException(429, "Rate limited by the Anthropic API — retry shortly.")
    except anthropic.APIStatusError as e:
        raise HTTPException(502, f"Anthropic API error ({e.status_code}).")
    except anthropic.APIConnectionError:
        raise HTTPException(502, "Could not reach the Anthropic API.")

    if resp.stop_reason == "refusal":
        raise HTTPException(422, "Request was declined by the safety system.")
    out = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(out)  # output_config.format guarantees valid JSON


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL,
            "key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "vocab": {"languages": len(LANGS), "locations": len(SEEN_LOCS), "centers": len(CENTERS)}}


@app.post("/parse-search")
def parse_search(body: TextIn):
    """Family's words -> structured search filters for the unified registry search."""
    return extract(SEARCH_SYSTEM, SEARCH_SCHEMA, body.text)


@app.post("/parse-intake")
def parse_intake(body: TextIn):
    """Volunteer's dictated description -> structured kiosk intake fields."""
    return extract(INTAKE_SYSTEM, INTAKE_SCHEMA, body.text)


if __name__ == "__main__":
    import uvicorn
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[!] ANTHROPIC_API_KEY is not set — endpoints will return 503 until you export it.")
    uvicorn.run(app, host="127.0.0.1", port=8000)
