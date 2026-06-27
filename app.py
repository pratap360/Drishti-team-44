import csv
import sqlite3
import os
import json
import time
import uuid
import logging
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, g, session
from rapidfuzz import fuzz
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

load_dotenv()

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)

app = Flask(__name__, static_folder="static")

# ---------------------------------------------------------------------------
# Secret key — fail loudly without it in production
# ---------------------------------------------------------------------------
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    _secret_key = "kumbh-mela-secret-key-2026"
    app.logger.warning(
        "SECRET_KEY not set in environment — using insecure default. "
        "Set SECRET_KEY env var before deploying to production."
    )
app.secret_key = _secret_key

# ---------------------------------------------------------------------------
# Session / cookie security
# ---------------------------------------------------------------------------
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

_IS_VERCEL = os.environ.get("VERCEL", "") == "1"
DB_PATH = os.path.join("/tmp", "kumbh.db") if _IS_VERCEL else os.path.join(os.path.dirname(__file__), "kumbh.db")
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ---------------------------------------------------------------------------
# Rate limiter config — env-var driven
# ---------------------------------------------------------------------------
MAX_REQUESTS = int(os.environ.get("RATE_MAX_REQUESTS", "100"))
TIME_WINDOW = int(os.environ.get("RATE_WINDOW_SECONDS", "60"))

# ---------------------------------------------------------------------------
# Simple TTL cache for /api/stats (30-second window)
# ---------------------------------------------------------------------------
_stats_cache: dict = {"ts": 0.0, "public": None, "admin": None}
_STATS_TTL = 30.0


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------------------
# Request ID
# ---------------------------------------------------------------------------

@app.before_request
def assign_request_id():
    g.request_id = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Supabase PostgreSQL helpers
# ---------------------------------------------------------------------------

def get_supabase_conn():
    if not SUPABASE_DB_URL or not HAS_PSYCOPG2:
        return None
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL, connect_timeout=5)
        return conn
    except Exception:
        app.logger.error("Supabase connection failed", exc_info=True)
        return None


def init_supabase_users():
    conn = get_supabase_conn()
    if not conn:
        print("[Supabase] No connection — using local SQLite for auth")
        return False
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(300) NOT NULL,
                role VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        default_users = [
            ("admin",     "admin123",   "admin"),
            ("volunteer", "vol123",     "volunteer"),
            ("family",    "family123",  "family"),
        ]
        for username, password, role in default_users:
            cur.execute("SELECT 1 FROM users WHERE username=%s", (username,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                    (username, generate_password_hash(password), role),
                )
        conn.commit()
        cur.close()
        conn.close()
        print("[Supabase] Users table ready — credentials encrypted with PBKDF2")
        return True
    except Exception as e:
        app.logger.error("Supabase init failed: %s", e, exc_info=True)
        conn.close()
        return False


def supabase_get_user(username):
    conn = get_supabase_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT username, password_hash, role FROM users WHERE username=%s", (username,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row
    except Exception:
        app.logger.error("supabase_get_user failed", exc_info=True)
        conn.close()
        return None


def supabase_create_user(username, password, role):
    conn = get_supabase_conn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING",
            (username, generate_password_hash(password), role),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception:
        app.logger.error("supabase_create_user failed", exc_info=True)
        conn.close()
        return False


_supabase_available = init_supabase_users()


# ---------------------------------------------------------------------------
# In-memory rate limiter: IP -> list of timestamps
# ---------------------------------------------------------------------------
_rate_limit_store: dict = {}


def rate_limit(max_per_window: int):
    """Decorator: allow at most max_per_window requests per IP per TIME_WINDOW seconds."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                ip = request.remote_addr or "unknown"
                now = time.time()
                hits = _rate_limit_store.get(ip, [])
                hits = [t for t in hits if now - t < TIME_WINDOW]
                if len(hits) >= max_per_window:
                    return jsonify({
                        "ok": False,
                        "error": "rate_limit_exceeded",
                        "message": "Rate limit exceeded. Try again shortly.",
                        "request_id": getattr(g, "request_id", None),
                    }), 429
                hits.append(now)
                _rate_limit_store[ip] = hits
            except Exception:
                # Log error but do not block the request
                app.logger.error("Rate limiter error", exc_info=True)
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db_connection():
    """Open a raw SQLite connection with WAL mode enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def get_db():
    if "db" not in g:
        g.db = get_db_connection()
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db:
        db.close()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(*roles):
    """Decorator factory. If roles is empty, any authenticated user is allowed."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "username" not in session:
                return jsonify({
                    "ok": False,
                    "error": "unauthenticated",
                    "message": "Authentication required",
                    "request_id": getattr(g, "request_id", None),
                }), 401
            if roles and session.get("role") not in roles:
                return jsonify({
                    "ok": False,
                    "error": "forbidden",
                    "message": "Insufficient permissions",
                    "request_id": getattr(g, "request_id", None),
                }), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def validate_input(data: dict) -> tuple[dict, list[str]]:
    """
    Sanitise and validate common input fields.
    Returns (cleaned_data, errors).
    """
    errors = []
    out = {}

    text_fields = [
        "person_name", "found_location", "reporting_center", "state", "district",
        "language", "last_seen_location", "last_seen_time", "physical_description",
        "remarks", "reporter_name", "reporter_relationship", "special_needs",
        "aadhaar_last4", "age_band", "gender",
    ]
    for field in text_fields:
        val = data.get(field, "")
        if val:
            val = str(val).strip()[:500]
        out[field] = val

    # Gender validation
    gender_val = out.get("gender", "")
    if gender_val and gender_val not in ("Male", "Female", "Unknown", ""):
        errors.append(f"gender must be Male, Female, Unknown, or empty (got '{gender_val}')")

    # Phone validation — handle reporter_mobile and contact_mobile independently
    def _validate_mobile(field_name):
        raw_val = str(data.get(field_name, "") or "").strip()
        if raw_val:
            digits = "".join(ch for ch in raw_val if ch.isdigit())
            if not (10 <= len(digits) <= 13):
                errors.append(
                    f"{field_name} must be 10-13 digits (got {len(digits)} digits)"
                )
                return ""
            return digits
        return ""

    out["reporter_mobile"] = _validate_mobile("reporter_mobile")
    out["contact_mobile"] = _validate_mobile("contact_mobile")

    # Photo size validation (base64 string length proxy for 500 KB)
    photo_val = data.get("photo", "") or ""
    # 500 KB binary → ~666 KB base64 chars; use 700 000 chars as ceiling
    if len(photo_val) > 700_000:
        errors.append("Photo exceeds 500 KB limit")
        out["photo"] = ""
    else:
        out["photo"] = photo_val

    return out, errors


# ---------------------------------------------------------------------------
# Audit log helper
# ---------------------------------------------------------------------------

def log_audit(db, case_id, action, details, actor=None):
    if actor is None:
        actor = session.get("username", "system")
    db.execute(
        "INSERT INTO audit_log (case_id, action, details, actor, timestamp) VALUES (?, ?, ?, ?, ?)",
        (case_id, action, details, actor, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )


# ---------------------------------------------------------------------------
# DB initialisation
# ---------------------------------------------------------------------------

def init_db():
    needs_data = not os.path.exists(DB_PATH)
    conn = get_db_connection()

    # Always ensure tables exist (idempotent on subsequent startups)
    conn.execute("""CREATE TABLE IF NOT EXISTS report_missing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reported_at TEXT,
        person_name TEXT,
        gender TEXT,
        age_band TEXT,
        state TEXT,
        district TEXT,
        language TEXT,
        last_seen_location TEXT,
        last_seen_time TEXT,
        physical_description TEXT,
        photo TEXT,
        aadhaar_last4 TEXT,
        reporter_name TEXT,
        reporter_mobile TEXT,
        reporter_relationship TEXT,
        special_needs TEXT,
        status TEXT DEFAULT 'Searching',
        matched_found_id INTEGER
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS callback_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        found_person_id INTEGER,
        requested_at TEXT,
        status TEXT DEFAULT 'pending'
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT,
        action TEXT,
        details TEXT,
        actor TEXT,
        timestamp TEXT
    )""")

    # Seed default users if not already present
    default_users = [
        ("admin",     "admin123",   "admin"),
        ("volunteer", "vol123",     "volunteer"),
        ("family",    "family123",  "family"),
    ]
    for username, password, role in default_users:
        exists = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), role),
            )

    conn.commit()

    row_count = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='missing_persons'"
    ).fetchone()[0]
    if row_count > 0:
        # Tables already exist — run migrations for columns added after initial schema
        _migrate_schema(conn)
        # Still add indexes in case they're missing
        _add_indexes(conn)
        conn.close()
        return

    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS missing_persons (
        case_id TEXT PRIMARY KEY,
        reported_at TEXT,
        missing_person_name TEXT,
        gender TEXT,
        age_band TEXT,
        state TEXT,
        district TEXT,
        language TEXT,
        last_seen_location TEXT,
        reporting_center TEXT,
        reporter_mobile TEXT,
        physical_description TEXT,
        status TEXT,
        resolution_hours REAL,
        is_duplicate_report INTEGER,
        remarks TEXT,
        aadhaar_last4 TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS cctv (
        camera_id TEXT PRIMARY KEY,
        longitude REAL,
        latitude REAL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS zones (
        zone_name TEXT PRIMARY KEY,
        centroid_lat REAL,
        centroid_lng REAL,
        approx_boundary_points INTEGER
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS police_stations (
        station_name TEXT PRIMARY KEY,
        longitude REAL,
        latitude REAL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS chokepoints (
        location_name TEXT PRIMARY KEY,
        category TEXT,
        longitude REAL,
        latitude REAL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS found_persons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        found_at TEXT,
        found_location TEXT,
        reporting_center TEXT,
        person_name TEXT,
        gender TEXT,
        age_band TEXT,
        state TEXT,
        district TEXT,
        language TEXT,
        physical_description TEXT,
        contact_mobile TEXT,
        status TEXT DEFAULT 'Pending',
        matched_case_id TEXT,
        remarks TEXT,
        photo TEXT
    )""")

    with open(os.path.join(DATA_DIR, "Synthetic_Missing_Persons_2500.csv")) as f:
        reader = csv.DictReader(f)
        for row in reader:
            c.execute(
                "INSERT OR IGNORE INTO missing_persons VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["case_id"], row["reported_at"], row["missing_person_name"],
                    row["gender"], row["age_band"], row["state"], row["district"],
                    row["language"], row["last_seen_location"], row["reporting_center"],
                    row["reporter_mobile"], row["physical_description"], row["status"],
                    float(row["resolution_hours"]) if row["resolution_hours"] else None,
                    1 if row["is_duplicate_report"] == "True" else 0,
                    row["remarks"],
                    row.get("aadhaar_last4", ""),
                ),
            )

    with open(os.path.join(DATA_DIR, "CCTV_Locations.csv")) as f:
        for row in csv.DictReader(f):
            c.execute("INSERT OR IGNORE INTO cctv VALUES (?,?,?)",
                      (row["camera_id"], float(row["longitude"]), float(row["latitude"])))

    with open(os.path.join(DATA_DIR, "Zone_Boundaries.csv")) as f:
        for row in csv.DictReader(f):
            c.execute("INSERT OR IGNORE INTO zones VALUES (?,?,?,?)",
                      (row["zone_name"], float(row["centroid_lat"]),
                       float(row["centroid_lng"]), int(row["approx_boundary_points"])))

    with open(os.path.join(DATA_DIR, "Police_Stations.csv")) as f:
        for row in csv.DictReader(f):
            c.execute("INSERT OR IGNORE INTO police_stations VALUES (?,?,?)",
                      (row["station_name"], float(row["longitude"]), float(row["latitude"])))

    with open(os.path.join(DATA_DIR, "Chokepoints_Parking.csv")) as f:
        for row in csv.DictReader(f):
            c.execute("INSERT OR IGNORE INTO chokepoints VALUES (?,?,?,?)",
                      (row["location_name"], row["category"],
                       float(row["longitude"]), float(row["latitude"])))

    _add_indexes(conn)
    conn.commit()
    conn.close()


def _migrate_schema(conn):
    """Apply incremental schema changes to existing databases."""
    # Add aadhaar_last4 column if missing (added after initial schema)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(missing_persons)")}
    if "aadhaar_last4" not in cols:
        conn.execute("ALTER TABLE missing_persons ADD COLUMN aadhaar_last4 TEXT")
        app.logger.info("Migration: added aadhaar_last4 column to missing_persons")
    conn.commit()


def _add_indexes(conn):
    """Create performance indexes if they don't already exist."""
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_missing_status ON missing_persons(status)",
        "CREATE INDEX IF NOT EXISTS idx_missing_case_id ON missing_persons(case_id)",
        "CREATE INDEX IF NOT EXISTS idx_missing_gender_age ON missing_persons(gender, age_band)",
        "CREATE INDEX IF NOT EXISTS idx_found_status ON found_persons(status)",
        "CREATE INDEX IF NOT EXISTS idx_found_gender_age ON found_persons(gender, age_band)",
        "CREATE INDEX IF NOT EXISTS idx_missing_aadhaar ON missing_persons(aadhaar_last4)",
    ]
    for sql in indexes:
        try:
            conn.execute(sql)
        except Exception:
            app.logger.error("Failed to create index: %s", sql, exc_info=True)
    conn.commit()


# ---------------------------------------------------------------------------
# Static routes
# ---------------------------------------------------------------------------

@app.route("/")
def landing():
    return send_from_directory("static", "landing.html")


@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js", mimetype="application/javascript")


@app.route("/control")
def control():
    return send_from_directory("static", "control.html")


@app.route("/volunteer")
def volunteer():
    return send_from_directory("static", "volunteer.html")


@app.route("/family")
def family():
    return send_from_directory("static", "family.html")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return jsonify({"status": "ok", "db": "ok"}), 200
    except Exception as e:
        app.logger.error("Health check DB error", exc_info=True)
        return jsonify({"status": "error", "db": str(e)}), 503


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.route("/api/login", methods=["POST"])
@rate_limit(30)
def api_login():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    requested_role = data.get("role") or ""

    if not username or not password:
        return jsonify({
            "ok": False,
            "error": "missing_credentials",
            "message": "Username and password are required",
            "request_id": g.request_id,
        }), 400

    user = None
    auth_source = "sqlite"

    # Try Supabase first (encrypted credentials in cloud PostgreSQL)
    if _supabase_available:
        sb_user = supabase_get_user(username)
        if sb_user and check_password_hash(sb_user["password_hash"], password):
            user = sb_user
            auth_source = "supabase"

    # Fallback to local SQLite (offline mode)
    if not user:
        db = get_db()
        row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            user = {"username": row["username"], "password_hash": row["password_hash"], "role": row["role"]}
            auth_source = "sqlite"

    if not user:
        return jsonify({
            "ok": False,
            "error": "invalid_credentials",
            "message": "Invalid credentials",
            "request_id": g.request_id,
        }), 401

    actual_role = user["role"]
    if requested_role and requested_role != actual_role:
        return jsonify({
            "ok": False,
            "error": "role_mismatch",
            "message": "Role mismatch",
            "request_id": g.request_id,
        }), 403

    session.clear()
    session["username"] = username
    session["role"] = actual_role
    session["auth_source"] = auth_source
    return jsonify({"ok": True, "role": actual_role, "username": username})


@app.route("/api/register", methods=["POST"])
@login_required("admin")
@rate_limit(10)
def api_register():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "").strip()

    if not username or not password or role not in ("admin", "volunteer", "family"):
        return jsonify({
            "ok": False,
            "error": "invalid_input",
            "message": "Valid username, password, and role (admin/volunteer/family) required",
            "request_id": g.request_id,
        }), 400
    if len(password) < 6:
        return jsonify({
            "ok": False,
            "error": "password_too_short",
            "message": "Password must be at least 6 characters",
            "request_id": g.request_id,
        }), 400

    created = False
    if _supabase_available:
        created = supabase_create_user(username, password, role)

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), role),
        )
        db.commit()
        created = True
    except sqlite3.IntegrityError:
        if not created:
            return jsonify({
                "ok": False,
                "error": "username_exists",
                "message": "Username already exists",
                "request_id": g.request_id,
            }), 409

    return jsonify({"ok": True, "message": f"User '{username}' created with role '{role}'"})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/me")
def api_me():
    if "username" not in session:
        return jsonify({
            "ok": False,
            "error": "unauthenticated",
            "message": "Not authenticated",
            "request_id": g.request_id,
        }), 401
    return jsonify({"ok": True, "username": session["username"], "role": session["role"]})


# ---------------------------------------------------------------------------
# Stats (public subset vs admin full view) — TTL cached for 30 s
# ---------------------------------------------------------------------------

@app.route("/api/stats")
def stats():
    now = time.time()
    is_admin = session.get("role") == "admin"
    cache_key = "admin" if is_admin else "public"

    if now - _stats_cache["ts"] < _STATS_TTL and _stats_cache.get(cache_key) is not None:
        return jsonify(_stats_cache[cache_key])

    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM missing_persons").fetchone()[0]
    reunited = db.execute("SELECT COUNT(*) FROM missing_persons WHERE status='Reunited'").fetchone()[0]
    avg_hours_row = db.execute(
        "SELECT AVG(resolution_hours) FROM missing_persons WHERE resolution_hours IS NOT NULL"
    ).fetchone()[0]
    avg_resolution_hours = round(avg_hours_row, 1) if avg_hours_row else 0

    # Public callers only get the summary
    if not is_admin:
        result = {
            "total": total,
            "reunited": reunited,
            "avg_resolution_hours": avg_resolution_hours,
        }
        _stats_cache["public"] = result
        _stats_cache["ts"] = now
        return jsonify(result)

    # Admin gets the full picture
    pending = db.execute("SELECT COUNT(*) FROM missing_persons WHERE status='Pending'").fetchone()[0]
    unresolved = db.execute("SELECT COUNT(*) FROM missing_persons WHERE status='Unresolved'").fetchone()[0]
    hospital = db.execute("SELECT COUNT(*) FROM missing_persons WHERE status='Transferred to hospital'").fetchone()[0]
    duplicates = db.execute("SELECT COUNT(*) FROM missing_persons WHERE is_duplicate_report=1").fetchone()[0]
    found_total = db.execute("SELECT COUNT(*) FROM found_persons").fetchone()[0]
    found_matched = db.execute("SELECT COUNT(*) FROM found_persons WHERE matched_case_id IS NOT NULL").fetchone()[0]
    family_reports = db.execute("SELECT COUNT(*) FROM report_missing").fetchone()[0]
    family_matched = db.execute("SELECT COUNT(*) FROM report_missing WHERE matched_found_id IS NOT NULL").fetchone()[0]

    by_center = db.execute("""
        SELECT reporting_center, COUNT(*) as cnt,
               SUM(CASE WHEN status='Reunited' THEN 1 ELSE 0 END) as reunited
        FROM missing_persons GROUP BY reporting_center ORDER BY cnt DESC
    """).fetchall()

    by_age = db.execute("""
        SELECT age_band, COUNT(*) as cnt FROM missing_persons GROUP BY age_band ORDER BY cnt DESC
    """).fetchall()

    by_date = db.execute("""
        SELECT DATE(reported_at) as dt, COUNT(*) as cnt
        FROM missing_persons GROUP BY dt ORDER BY dt
    """).fetchall()

    result = {
        "total": total, "pending": pending, "reunited": reunited,
        "unresolved": unresolved, "hospital": hospital, "duplicates": duplicates,
        "avg_resolution_hours": avg_resolution_hours,
        "found_total": found_total, "found_matched": found_matched,
        "family_reports": family_reports, "family_matched": family_matched,
        "by_center": [{"center": r[0], "count": r[1], "reunited": r[2]} for r in by_center],
        "by_age": [{"age_band": r[0], "count": r[1]} for r in by_age],
        "by_date": [{"date": r[0], "count": r[1]} for r in by_date],
    }
    _stats_cache["admin"] = result
    _stats_cache["ts"] = now
    return jsonify(result)


# ---------------------------------------------------------------------------
# Search (public)
# ---------------------------------------------------------------------------

@app.route("/api/search")
def search():
    db = get_db()
    q = request.args.get("q", "").strip()
    gender = request.args.get("gender", "")
    age_band = request.args.get("age_band", "")
    state = request.args.get("state", "")
    language = request.args.get("language", "")
    center = request.args.get("center", "")
    status = request.args.get("status", "")
    limit = min(int(request.args.get("limit", 50)), 200)

    conditions = []
    params = []

    if gender:
        conditions.append("gender = ?")
        params.append(gender)
    if age_band:
        conditions.append("age_band = ?")
        params.append(age_band)
    if state:
        conditions.append("state = ?")
        params.append(state)
    if language:
        conditions.append("language = ?")
        params.append(language)
    if center:
        conditions.append("reporting_center = ?")
        params.append(center)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = " AND ".join(conditions) if conditions else "1=1"
    query = f"SELECT * FROM missing_persons WHERE {where} ORDER BY reported_at DESC LIMIT ?"
    params.append(limit * 4 if q else limit)

    rows = db.execute(query, params).fetchall()
    results = [dict(r) for r in rows]

    if q:
        scored = []
        for r in results:
            name_score = fuzz.partial_ratio(q.lower(), (r["missing_person_name"] or "").lower())
            desc_score = fuzz.partial_ratio(q.lower(), (r["physical_description"] or "").lower())
            loc_score = fuzz.partial_ratio(q.lower(), (r["last_seen_location"] or "").lower())
            case_score = 100 if q.lower() in (r["case_id"] or "").lower() else 0
            mobile_score = 100 if q in (r["reporter_mobile"] or "") else 0
            best = max(name_score, desc_score, loc_score, case_score, mobile_score)
            if best >= 45:
                r["match_score"] = round(best, 1)
                scored.append(r)
        scored.sort(key=lambda x: x["match_score"], reverse=True)
        results = scored[:limit]

    return jsonify({"results": results, "count": len(results)})


# ---------------------------------------------------------------------------
# Fuzzy match (volunteer/admin) — pre-filtered by gender + age_band in SQL
# ---------------------------------------------------------------------------

@app.route("/api/fuzzy-match", methods=["POST"])
@login_required("volunteer", "admin")
@rate_limit(30)
def fuzzy_match():
    """Find potential matches for a found person against all missing reports."""
    db = get_db()
    data = request.json or {}
    gender = data.get("gender", "")
    age_band = data.get("age_band", "")
    state = data.get("state", "")
    language = data.get("language", "")
    name = data.get("name", "")
    description = data.get("description", "")

    # Pre-filter in SQL on exact-match fields before loading into Python
    conditions = ["status IN ('Pending', 'Unresolved')"]
    params = []
    if gender and gender != "Unknown":
        conditions.append("gender = ?")
        params.append(gender)
    if age_band:
        conditions.append("age_band = ?")
        params.append(age_band)

    where = " AND ".join(conditions)
    rows = db.execute(f"SELECT * FROM missing_persons WHERE {where}", params).fetchall()
    candidates = [dict(r) for r in rows]

    scored = []
    for c in candidates:
        score = 0
        reasons = []

        if name and c["missing_person_name"]:
            ns = fuzz.token_sort_ratio(name.lower(), c["missing_person_name"].lower())
            if ns > 60:
                score += ns * 0.35
                reasons.append(f"Name: {round(ns)}%")

        if state and c["state"] and state.lower() == c["state"].lower():
            score += 15
            reasons.append("State match")

        if language and c["language"] and language.lower() == c["language"].lower():
            score += 10
            reasons.append("Language match")

        if description and c["physical_description"]:
            ds = fuzz.token_set_ratio(description.lower(), c["physical_description"].lower())
            if ds > 40:
                score += ds * 0.25
                reasons.append(f"Description: {round(ds)}%")

        if age_band and c["age_band"] == age_band:
            score += 10
            reasons.append("Age match")

        if score >= 35:
            c["match_score"] = round(score, 1)
            c["match_reasons"] = reasons
            scored.append(c)

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return jsonify({"matches": scored[:20]})


# ---------------------------------------------------------------------------
# Report found (volunteer)
# ---------------------------------------------------------------------------

@app.route("/api/report-found", methods=["POST"])
@login_required("volunteer", "admin")
@rate_limit(30)
def report_found():
    db = get_db()
    raw = request.json or {}
    cleaned, errors = validate_input(raw)
    if errors:
        return jsonify({
            "ok": False,
            "error": "validation_error",
            "message": "; ".join(errors),
            "errors": errors,
            "request_id": g.request_id,
        }), 400

    db.execute("""INSERT INTO found_persons
        (found_at, found_location, reporting_center, person_name, gender,
         age_band, state, district, language, physical_description,
         contact_mobile, remarks, photo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            cleaned.get("found_location", ""),
            cleaned.get("reporting_center", ""),
            cleaned.get("person_name", ""),
            cleaned.get("gender", ""),
            cleaned.get("age_band", ""),
            cleaned.get("state", ""),
            cleaned.get("district", ""),
            cleaned.get("language", ""),
            cleaned.get("physical_description", ""),
            cleaned.get("contact_mobile", ""),
            cleaned.get("remarks", ""),
            cleaned.get("photo", ""),
        ))
    db.commit()
    new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    log_audit(db, str(new_id), "found_person_logged",
              f"Found person reported at {cleaned.get('found_location', '')}")
    db.commit()
    return jsonify({"ok": True, "id": new_id})


# ---------------------------------------------------------------------------
# Confirm match (admin) — with existence checks and rowcount validation
# ---------------------------------------------------------------------------

@app.route("/api/confirm-match", methods=["POST"])
@login_required("admin")
@rate_limit(30)
def confirm_match():
    db = get_db()
    data = request.json or {}
    found_id = data.get("found_id")
    case_id = data.get("case_id")

    if found_id is None or case_id is None:
        return jsonify({
            "ok": False,
            "error": "missing_params",
            "message": "found_id and case_id are required",
            "request_id": g.request_id,
        }), 400

    # Verify both records exist before updating
    fp_row = db.execute("SELECT id FROM found_persons WHERE id=?", (found_id,)).fetchone()
    if not fp_row:
        return jsonify({
            "ok": False,
            "error": "not_found",
            "message": f"Found person id={found_id} does not exist",
            "request_id": g.request_id,
        }), 404

    mp_row = db.execute("SELECT case_id FROM missing_persons WHERE case_id=?", (case_id,)).fetchone()
    if not mp_row:
        return jsonify({
            "ok": False,
            "error": "not_found",
            "message": f"Missing person case_id={case_id} does not exist",
            "request_id": g.request_id,
        }), 404

    cursor = db.execute(
        "UPDATE found_persons SET matched_case_id=?, status='Matched' WHERE id=?",
        (case_id, found_id)
    )
    if cursor.rowcount == 0:
        return jsonify({
            "ok": False,
            "error": "update_failed",
            "message": "Failed to update found_persons record",
            "request_id": g.request_id,
        }), 500

    cursor2 = db.execute(
        "UPDATE missing_persons SET status='Reunited' WHERE case_id=?", (case_id,)
    )
    if cursor2.rowcount == 0:
        app.logger.warning("confirm_match: missing_persons update rowcount=0 for case_id=%s", case_id)

    log_audit(db, case_id, "match_confirmed",
              f"Found person id={found_id} matched to case {case_id}")
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Report missing (family)
# ---------------------------------------------------------------------------

@app.route("/api/report-missing", methods=["POST"])
@login_required("family", "admin")
@rate_limit(30)
def report_missing():
    db = get_db()
    raw = request.json or {}
    cleaned, errors = validate_input(raw)
    if errors:
        return jsonify({
            "ok": False,
            "error": "validation_error",
            "message": "; ".join(errors),
            "errors": errors,
            "request_id": g.request_id,
        }), 400

    db.execute("""INSERT INTO report_missing
        (reported_at, person_name, gender, age_band, state, district, language,
         last_seen_location, last_seen_time, physical_description, photo,
         aadhaar_last4, reporter_name, reporter_mobile, reporter_relationship,
         special_needs)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            cleaned.get("person_name", ""),
            cleaned.get("gender", ""),
            cleaned.get("age_band", ""),
            cleaned.get("state", ""),
            cleaned.get("district", ""),
            cleaned.get("language", ""),
            cleaned.get("last_seen_location", ""),
            cleaned.get("last_seen_time", ""),
            cleaned.get("physical_description", ""),
            cleaned.get("photo", ""),
            cleaned.get("aadhaar_last4", ""),
            cleaned.get("reporter_name", ""),
            cleaned.get("reporter_mobile", ""),
            cleaned.get("reporter_relationship", ""),
            cleaned.get("special_needs", ""),
        ))
    db.commit()
    new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    case_ref = f"FM-{new_id:04d}"
    log_audit(db, case_ref, "report_created",
              f"Missing report filed for '{cleaned.get('person_name', '')}' by '{cleaned.get('reporter_name', '')}'")
    db.commit()
    return jsonify({"ok": True, "id": new_id, "case_ref": case_ref})


# ---------------------------------------------------------------------------
# Track case (family / admin)
# ---------------------------------------------------------------------------

@app.route("/api/track")
@login_required("family", "admin")
def track_case():
    db = get_db()
    case_ref = request.args.get("case_ref", "").strip()
    case_id = request.args.get("case_id", "").strip()
    mobile = request.args.get("mobile", "").strip()

    if not case_ref and not case_id and not mobile:
        return jsonify({
            "ok": False,
            "error": "missing_params",
            "message": "case_id, case_ref, or mobile required",
            "request_id": g.request_id,
        }), 400

    results = []

    # Support both legacy case_ref and direct case_id param
    effective_case_ref = case_ref or case_id

    if effective_case_ref:
        if effective_case_ref.startswith("FM-"):
            try:
                fm_id = int(effective_case_ref.replace("FM-", ""))
                row = db.execute("SELECT * FROM report_missing WHERE id=?", (fm_id,)).fetchone()
                if row:
                    results.append({**dict(row), "source": "family_report", "case_ref": effective_case_ref})
            except ValueError:
                pass
        else:
            row = db.execute("SELECT * FROM missing_persons WHERE case_id=?", (effective_case_ref,)).fetchone()
            if row:
                results.append({**dict(row), "source": "missing_persons", "case_ref": effective_case_ref})

    if mobile:
        like_pattern = "%" + mobile + "%"
        rows = db.execute(
            "SELECT * FROM report_missing WHERE reporter_mobile LIKE ?", (like_pattern,)
        ).fetchall()
        for r in rows:
            d = dict(r)
            d["source"] = "family_report"
            d["case_ref"] = f"FM-{d['id']:04d}"
            results.append(d)

        rows2 = db.execute(
            "SELECT * FROM missing_persons WHERE reporter_mobile LIKE ?", (like_pattern,)
        ).fetchall()
        for r in rows2:
            d = dict(r)
            d["source"] = "missing_persons"
            d["case_ref"] = d["case_id"]
            results.append(d)

    return jsonify({"results": results, "count": len(results)})


# ---------------------------------------------------------------------------
# Found persons (public) — photo blobs stripped from list view
# ---------------------------------------------------------------------------

@app.route("/api/found-persons")
def list_found_persons():
    db = get_db()
    gender = request.args.get("gender", "")
    age_band = request.args.get("age_band", "")
    limit = min(int(request.args.get("limit", 50)), 200)

    conditions = ["status != 'Matched'"]
    params = []
    if gender:
        conditions.append("gender = ?")
        params.append(gender)
    if age_band:
        conditions.append("age_band = ?")
        params.append(age_band)

    where = " AND ".join(conditions)
    rows = db.execute(
        f"SELECT id, found_at, found_location, reporting_center, person_name, gender, "
        f"age_band, state, language, physical_description, photo, status "
        f"FROM found_persons WHERE {where} ORDER BY found_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    result_list = []
    for r in rows:
        p = dict(r)
        # Strip photo blobs from list view
        if p.get("photo") and len(str(p["photo"])) > 200:
            p["photo_available"] = True
            p["photo"] = None
        result_list.append(p)

    return jsonify({"results": result_list, "count": len(result_list)})


# ---------------------------------------------------------------------------
# Match against found (family)
# ---------------------------------------------------------------------------

@app.route("/api/match-found", methods=["POST"])
@login_required("family", "admin")
@rate_limit(30)
def match_against_found():
    """Match a family's missing person report against found persons."""
    db = get_db()
    data = request.json or {}
    name = data.get("name", "")
    gender = data.get("gender", "")
    age_band = data.get("age_band", "")
    state = data.get("state", "")
    language = data.get("language", "")
    description = data.get("description", "")

    conditions = ["status != 'Matched'"]
    params = []
    if gender and gender != "Unknown":
        conditions.append("gender = ?")
        params.append(gender)
    if age_band:
        conditions.append("age_band = ?")
        params.append(age_band)

    where = " AND ".join(conditions)
    rows = db.execute(f"SELECT * FROM found_persons WHERE {where}", params).fetchall()
    candidates = [dict(r) for r in rows]

    scored = []
    for c in candidates:
        score = 0
        reasons = []

        if name and c.get("person_name"):
            ns = fuzz.token_sort_ratio(name.lower(), c["person_name"].lower())
            if ns > 60:
                score += ns * 0.35
                reasons.append(f"Name: {round(ns)}%")

        if state and c.get("state") and state.lower() == c["state"].lower():
            score += 15
            reasons.append("State match")

        if language and c.get("language") and language.lower() == c["language"].lower():
            score += 10
            reasons.append("Language match")

        if description and c.get("physical_description"):
            ds = fuzz.token_set_ratio(description.lower(), c["physical_description"].lower())
            if ds > 40:
                score += ds * 0.25
                reasons.append(f"Description: {round(ds)}%")

        if age_band and c.get("age_band") == age_band:
            score += 10
            reasons.append("Age match")

        if score >= 20:
            c["match_score"] = round(score, 1)
            c["match_reasons"] = reasons
            # Mask the contact mobile for privacy
            mobile = c.get("contact_mobile", "")
            if mobile and len(mobile) > 4:
                c["contact_mobile"] = mobile[:3] + "****" + mobile[-3:]
            scored.append(c)

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return jsonify({"matches": scored[:20]})


# ---------------------------------------------------------------------------
# Duplicates (admin)
# ---------------------------------------------------------------------------

@app.route("/api/duplicates")
@login_required("admin")
def find_duplicates():
    db = get_db()
    rows = db.execute("""
        SELECT * FROM missing_persons
        WHERE status='Pending' AND missing_person_name != ''
        ORDER BY missing_person_name
    """).fetchall()
    persons = [dict(r) for r in rows]

    groups = []
    seen = set()
    for i, p in enumerate(persons):
        if p["case_id"] in seen:
            continue
        cluster = [p]
        for j in range(i + 1, len(persons)):
            q = persons[j]
            if q["case_id"] in seen:
                continue
            name_sim = fuzz.token_sort_ratio(
                (p["missing_person_name"] or "").lower(),
                (q["missing_person_name"] or "").lower()
            )
            same_gender = p["gender"] == q["gender"]
            same_age = p["age_band"] == q["age_band"]
            if name_sim > 75 and same_gender and same_age:
                cluster.append(q)
                seen.add(q["case_id"])
        if len(cluster) > 1:
            groups.append(cluster)
            seen.add(p["case_id"])

    return jsonify({"duplicate_groups": groups, "count": len(groups)})


# ---------------------------------------------------------------------------
# Geo data (public)
# ---------------------------------------------------------------------------

@app.route("/api/geo")
def geo_data():
    db = get_db()
    cctv = [dict(r) for r in db.execute("SELECT * FROM cctv").fetchall()]
    zones = [dict(r) for r in db.execute("SELECT * FROM zones").fetchall()]
    police = [dict(r) for r in db.execute("SELECT * FROM police_stations").fetchall()]
    chokepoints = [dict(r) for r in db.execute("SELECT * FROM chokepoints").fetchall()]
    return jsonify({
        "cctv": cctv, "zones": zones,
        "police_stations": police, "chokepoints": chokepoints
    })


# ---------------------------------------------------------------------------
# Hotspots — enhanced with geo coordinates
# ---------------------------------------------------------------------------

@app.route("/api/hotspots")
def hotspots():
    db = get_db()
    rows = db.execute("""
        SELECT last_seen_location, COUNT(*) as cnt,
               SUM(CASE WHEN status='Pending' OR status='Unresolved' THEN 1 ELSE 0 END) as active
        FROM missing_persons
        GROUP BY last_seen_location ORDER BY cnt DESC LIMIT 20
    """).fetchall()

    hotspot_list = [dict(r) for r in rows]

    chokepoints = db.execute(
        "SELECT location_name, latitude, longitude FROM chokepoints"
    ).fetchall()
    zones = db.execute(
        "SELECT zone_name, centroid_lat, centroid_lng FROM zones"
    ).fetchall()

    geo_sources = []
    for cp in chokepoints:
        geo_sources.append({
            "name": (cp["location_name"] or "").lower(),
            "lat": cp["latitude"],
            "lng": cp["longitude"],
        })
    for z in zones:
        geo_sources.append({
            "name": (z["zone_name"] or "").lower(),
            "lat": z["centroid_lat"],
            "lng": z["centroid_lng"],
        })

    for h in hotspot_list:
        loc_lower = (h.get("last_seen_location") or "").lower()
        best_score = 0
        best_lat = None
        best_lng = None
        for gs in geo_sources:
            score = fuzz.partial_ratio(loc_lower, gs["name"])
            if score > best_score and score >= 50:
                best_score = score
                best_lat = gs["lat"]
                best_lng = gs["lng"]
        if best_lat is not None:
            h["lat"] = best_lat
            h["lng"] = best_lng
            h["geo_confidence"] = best_score
        else:
            h["lat"] = None
            h["lng"] = None
            h["geo_confidence"] = 0

    return jsonify({"hotspots": hotspot_list})


# ---------------------------------------------------------------------------
# Filters (public)
# ---------------------------------------------------------------------------

@app.route("/api/filters")
def filters():
    db = get_db()
    genders = [r[0] for r in db.execute("SELECT DISTINCT gender FROM missing_persons ORDER BY gender").fetchall()]
    ages = [r[0] for r in db.execute("SELECT DISTINCT age_band FROM missing_persons ORDER BY age_band").fetchall()]
    states = [r[0] for r in db.execute("SELECT DISTINCT state FROM missing_persons WHERE state != '' ORDER BY state").fetchall()]
    languages = [r[0] for r in db.execute("SELECT DISTINCT language FROM missing_persons WHERE language != '' ORDER BY language").fetchall()]
    centers = [r[0] for r in db.execute("SELECT DISTINCT reporting_center FROM missing_persons ORDER BY reporting_center").fetchall()]
    return jsonify({"genders": genders, "ages": ages, "states": states, "languages": languages, "centers": centers})


# ---------------------------------------------------------------------------
# Callback request (any authenticated user)
# ---------------------------------------------------------------------------

@app.route("/api/request-callback", methods=["POST"])
@login_required()
@rate_limit(30)
def request_callback():
    data = request.json or {}
    found_person_id = data.get("found_person_id")

    # Validate found_person_id is an integer
    if found_person_id is None:
        return jsonify({
            "ok": False,
            "error": "missing_params",
            "message": "found_person_id is required",
            "request_id": g.request_id,
        }), 400
    try:
        found_person_id = int(found_person_id)
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "error": "invalid_param",
            "message": "found_person_id must be an integer",
            "request_id": g.request_id,
        }), 400

    db = get_db()
    db.execute(
        "INSERT INTO callback_requests (found_person_id, requested_at, status) VALUES (?, ?, 'pending')",
        (found_person_id, datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    log_audit(db, str(found_person_id), "callback_requested",
              f"Callback requested for found_person_id={found_person_id}")
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Audit log endpoint (admin)
# ---------------------------------------------------------------------------

@app.route("/api/audit-log")
@login_required("admin")
def audit_log():
    db = get_db()
    case_id = request.args.get("case_id", "").strip()
    if case_id:
        rows = db.execute(
            "SELECT * FROM audit_log WHERE case_id=? ORDER BY timestamp ASC",
            (case_id,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 200"
        ).fetchall()
    return jsonify({"timeline": [dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

init_db()

if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5050)),
    )
