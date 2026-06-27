import csv
import sqlite3
import os
import json
import math
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, g
from rapidfuzz import fuzz

app = Flask(__name__, static_folder="static")
DB_PATH = os.path.join(os.path.dirname(__file__), "kumbh.db")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data-repo", "claude-impact-lab-mumbai-2026", "data")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    needs_data = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)

    # Always ensure report_missing table exists (even on subsequent startups)
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
    conn.commit()

    row_count = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='missing_persons'").fetchone()[0]
    if row_count > 0:
        conn.close()
        return
    conn.execute("PRAGMA journal_mode=WAL")
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
        remarks TEXT
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
                "INSERT OR IGNORE INTO missing_persons VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["case_id"], row["reported_at"], row["missing_person_name"],
                    row["gender"], row["age_band"], row["state"], row["district"],
                    row["language"], row["last_seen_location"], row["reporting_center"],
                    row["reporter_mobile"], row["physical_description"], row["status"],
                    float(row["resolution_hours"]) if row["resolution_hours"] else None,
                    1 if row["is_duplicate_report"] == "True" else 0,
                    row["remarks"]
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

    conn.commit()
    conn.close()


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


@app.route("/api/stats")
def stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM missing_persons").fetchone()[0]
    pending = db.execute("SELECT COUNT(*) FROM missing_persons WHERE status='Pending'").fetchone()[0]
    reunited = db.execute("SELECT COUNT(*) FROM missing_persons WHERE status='Reunited'").fetchone()[0]
    unresolved = db.execute("SELECT COUNT(*) FROM missing_persons WHERE status='Unresolved'").fetchone()[0]
    hospital = db.execute("SELECT COUNT(*) FROM missing_persons WHERE status='Transferred to hospital'").fetchone()[0]
    duplicates = db.execute("SELECT COUNT(*) FROM missing_persons WHERE is_duplicate_report=1").fetchone()[0]
    avg_hours = db.execute("SELECT AVG(resolution_hours) FROM missing_persons WHERE resolution_hours IS NOT NULL").fetchone()[0]
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

    return jsonify({
        "total": total, "pending": pending, "reunited": reunited,
        "unresolved": unresolved, "hospital": hospital, "duplicates": duplicates,
        "avg_resolution_hours": round(avg_hours, 1) if avg_hours else 0,
        "found_total": found_total, "found_matched": found_matched,
        "family_reports": family_reports, "family_matched": family_matched,
        "by_center": [{"center": r[0], "count": r[1], "reunited": r[2]} for r in by_center],
        "by_age": [{"age_band": r[0], "count": r[1]} for r in by_age],
        "by_date": [{"date": r[0], "count": r[1]} for r in by_date],
    })


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


@app.route("/api/fuzzy-match", methods=["POST"])
def fuzzy_match():
    """Find potential matches for a found person against all missing reports."""
    db = get_db()
    data = request.json
    gender = data.get("gender", "")
    age_band = data.get("age_band", "")
    state = data.get("state", "")
    language = data.get("language", "")
    name = data.get("name", "")
    description = data.get("description", "")

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

        if score >= 20:
            c["match_score"] = round(score, 1)
            c["match_reasons"] = reasons
            scored.append(c)

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return jsonify({"matches": scored[:20]})


@app.route("/api/report-found", methods=["POST"])
def report_found():
    db = get_db()
    data = request.json
    db.execute("""INSERT INTO found_persons
        (found_at, found_location, reporting_center, person_name, gender,
         age_band, state, district, language, physical_description,
         contact_mobile, remarks, photo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            data.get("found_location", ""),
            data.get("reporting_center", ""),
            data.get("person_name", ""),
            data.get("gender", ""),
            data.get("age_band", ""),
            data.get("state", ""),
            data.get("district", ""),
            data.get("language", ""),
            data.get("physical_description", ""),
            data.get("contact_mobile", ""),
            data.get("remarks", ""),
            data.get("photo", ""),
        ))
    db.commit()
    return jsonify({"ok": True, "id": db.execute("SELECT last_insert_rowid()").fetchone()[0]})


@app.route("/api/confirm-match", methods=["POST"])
def confirm_match():
    db = get_db()
    data = request.json
    found_id = data["found_id"]
    case_id = data["case_id"]
    db.execute("UPDATE found_persons SET matched_case_id=?, status='Matched' WHERE id=?",
               (case_id, found_id))
    db.execute("UPDATE missing_persons SET status='Reunited' WHERE case_id=?", (case_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/report-missing", methods=["POST"])
def report_missing():
    db = get_db()
    data = request.json
    db.execute("""INSERT INTO report_missing
        (reported_at, person_name, gender, age_band, state, district, language,
         last_seen_location, last_seen_time, physical_description, photo,
         aadhaar_last4, reporter_name, reporter_mobile, reporter_relationship,
         special_needs)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            data.get("person_name", ""),
            data.get("gender", ""),
            data.get("age_band", ""),
            data.get("state", ""),
            data.get("district", ""),
            data.get("language", ""),
            data.get("last_seen_location", ""),
            data.get("last_seen_time", ""),
            data.get("physical_description", ""),
            data.get("photo", ""),
            data.get("aadhaar_last4", ""),
            data.get("reporter_name", ""),
            data.get("reporter_mobile", ""),
            data.get("reporter_relationship", ""),
            data.get("special_needs", ""),
        ))
    db.commit()
    new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    return jsonify({"ok": True, "id": new_id, "case_ref": f"FM-{new_id:04d}"})


@app.route("/api/track")
def track_case():
    db = get_db()
    case_ref = request.args.get("case_ref", "").strip()
    mobile = request.args.get("mobile", "").strip()

    results = []

    # Search in missing_persons by case_id
    if case_ref:
        # Try FM- format (family portal reports)
        if case_ref.startswith("FM-"):
            try:
                fm_id = int(case_ref.replace("FM-", ""))
                row = db.execute("SELECT * FROM report_missing WHERE id=?", (fm_id,)).fetchone()
                if row:
                    results.append({**dict(row), "source": "family_report", "case_ref": case_ref})
            except ValueError:
                pass
        else:
            row = db.execute("SELECT * FROM missing_persons WHERE case_id=?", (case_ref,)).fetchone()
            if row:
                results.append({**dict(row), "source": "missing_persons", "case_ref": case_ref})

    # Search by mobile
    if mobile:
        rows = db.execute("SELECT * FROM report_missing WHERE reporter_mobile LIKE ?", (f"%{mobile}%",)).fetchall()
        for r in rows:
            d = dict(r)
            d["source"] = "family_report"
            d["case_ref"] = f"FM-{d['id']:04d}"
            results.append(d)

        rows2 = db.execute("SELECT * FROM missing_persons WHERE reporter_mobile LIKE ?", (f"%{mobile}%",)).fetchall()
        for r in rows2:
            d = dict(r)
            d["source"] = "missing_persons"
            d["case_ref"] = d["case_id"]
            results.append(d)

    return jsonify({"results": results, "count": len(results)})


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
    rows = db.execute(f"SELECT id, found_at, found_location, reporting_center, person_name, gender, age_band, state, language, physical_description, photo, status FROM found_persons WHERE {where} ORDER BY found_at DESC LIMIT ?", params + [limit]).fetchall()

    return jsonify({"results": [dict(r) for r in rows], "count": len([dict(r) for r in rows])})


@app.route("/api/match-found", methods=["POST"])
def match_against_found():
    """Match a family's missing person report against found persons."""
    db = get_db()
    data = request.json
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


@app.route("/api/duplicates")
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


@app.route("/api/hotspots")
def hotspots():
    db = get_db()
    rows = db.execute("""
        SELECT last_seen_location, COUNT(*) as cnt,
               SUM(CASE WHEN status='Pending' OR status='Unresolved' THEN 1 ELSE 0 END) as active
        FROM missing_persons
        GROUP BY last_seen_location ORDER BY cnt DESC LIMIT 20
    """).fetchall()
    return jsonify({"hotspots": [dict(r) for r in rows]})


@app.route("/api/filters")
def filters():
    db = get_db()
    genders = [r[0] for r in db.execute("SELECT DISTINCT gender FROM missing_persons ORDER BY gender").fetchall()]
    ages = [r[0] for r in db.execute("SELECT DISTINCT age_band FROM missing_persons ORDER BY age_band").fetchall()]
    states = [r[0] for r in db.execute("SELECT DISTINCT state FROM missing_persons WHERE state != '' ORDER BY state").fetchall()]
    languages = [r[0] for r in db.execute("SELECT DISTINCT language FROM missing_persons WHERE language != '' ORDER BY language").fetchall()]
    centers = [r[0] for r in db.execute("SELECT DISTINCT reporting_center FROM missing_persons ORDER BY reporting_center").fetchall()]
    return jsonify({"genders": genders, "ages": ages, "states": states, "languages": languages, "centers": centers})


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5050)
