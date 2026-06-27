import pytest
import os
import sys
import tempfile
import sqlite3
import time

# Make sure app module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _seed_test_db(db_path):
    """
    Seed the test SQLite DB with tables and default users.
    Mirrors init_db() but skips CSV loading (no data files needed).
    """
    from werkzeug.security import generate_password_hash

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

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

    conn.execute("""CREATE TABLE IF NOT EXISTS missing_persons (
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

    conn.execute("""CREATE TABLE IF NOT EXISTS found_persons (
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

    conn.execute("""CREATE TABLE IF NOT EXISTS cctv (
        camera_id TEXT PRIMARY KEY, longitude REAL, latitude REAL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS zones (
        zone_name TEXT PRIMARY KEY, centroid_lat REAL,
        centroid_lng REAL, approx_boundary_points INTEGER
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS police_stations (
        station_name TEXT PRIMARY KEY, longitude REAL, latitude REAL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS chokepoints (
        location_name TEXT PRIMARY KEY, category TEXT,
        longitude REAL, latitude REAL
    )""")

    # Seed default users
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

    # Seed one missing person so stats/search/filter tests have data
    conn.execute("""INSERT OR IGNORE INTO missing_persons VALUES
        ('CASE-0001', '2026-01-01 10:00', 'Ramesh Kumar', 'Male', 'Adult (18-60)',
         'UP', 'Prayagraj', 'Hindi', 'Sangam Ghat', 'Center A',
         '9876543210', 'Tall, dark shirt', 'Pending', NULL, 0, '', '')""")

    conn.commit()
    conn.close()


@pytest.fixture(scope="function")
def app():
    """
    Create Flask test application backed by a fresh temporary SQLite DB.

    Key concerns addressed:
    - SUPABASE_DB_URL may be set in .env (loaded at import time). We directly
      patch app._supabase_available = False so auth falls through to SQLite.
    - _rate_limit_store is a module-level dict; we clear it before each test
      so rate limits from earlier tests don't bleed into later ones.
    - _stats_cache is similarly cleared so stats reflect the current test DB.
    - DB_PATH is patched to point to the temp file AFTER the module is already
      imported (init_db ran against the real DB on import, but get_db() uses
      the module-level DB_PATH variable for every request).
    """
    db_fd, db_path = tempfile.mkstemp(suffix='.db')

    # Pre-seed the database BEFORE any request (so init_db's idempotent path
    # won't try to load CSV files — the tables already exist).
    _seed_test_db(db_path)

    import app as app_module

    # Redirect all SQLite connections to our temp DB
    original_db_path = app_module.DB_PATH
    app_module.DB_PATH = db_path

    # Disable Supabase so auth falls through to local SQLite
    original_supabase = app_module._supabase_available
    app_module._supabase_available = False

    # Clear rate limiter and stats cache so they don't carry over between tests
    app_module._rate_limit_store.clear()
    app_module._stats_cache.update({"ts": 0.0, "public": None, "admin": None})

    flask_app = app_module.app
    flask_app.config['TESTING'] = True
    flask_app.config['SECRET_KEY'] = 'test-secret-key-for-testing'

    yield flask_app

    # Teardown: restore module state
    app_module.DB_PATH = original_db_path
    app_module._supabase_available = original_supabase
    app_module._rate_limit_store.clear()
    app_module._stats_cache.update({"ts": 0.0, "public": None, "admin": None})

    os.close(db_fd)
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """Create authenticated admin client."""
    rv = client.post('/api/login', json={
        'username': 'admin',
        'password': 'admin123'
    })
    assert rv.status_code == 200, f"Admin login failed: {rv.get_json()}"
    return client


@pytest.fixture
def volunteer_client(client):
    """Create authenticated volunteer client."""
    rv = client.post('/api/login', json={
        'username': 'volunteer',
        'password': 'vol123'
    })
    assert rv.status_code == 200, f"Volunteer login failed: {rv.get_json()}"
    return client


@pytest.fixture
def family_client(client):
    """Create authenticated family client."""
    rv = client.post('/api/login', json={
        'username': 'family',
        'password': 'family123'
    })
    assert rv.status_code == 200, f"Family login failed: {rv.get_json()}"
    return client
