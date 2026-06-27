#!/usr/bin/env python3
"""Upload all Kumbh Mela datasets to Supabase."""

import csv
import os
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_POOLER_URL"]
DATA_DIR = "data"

SCHEMA_SQL = """
-- Drop tables if they exist (order matters for FK deps)
DROP TABLE IF EXISTS missing_persons CASCADE;
DROP TABLE IF EXISTS cctv_cameras CASCADE;
DROP TABLE IF EXISTS chokepoints_parking CASCADE;
DROP TABLE IF EXISTS police_stations CASCADE;
DROP TABLE IF EXISTS zones CASCADE;

-- Zones: 32 administrative zones across the mela grounds
CREATE TABLE zones (
    id            SERIAL PRIMARY KEY,
    zone_name     TEXT UNIQUE NOT NULL,
    centroid_lat  DOUBLE PRECISION,
    centroid_lng  DOUBLE PRECISION,
    approx_boundary_points INTEGER
);

-- CCTV cameras, each assigned to a zone
CREATE TABLE cctv_cameras (
    id         SERIAL PRIMARY KEY,
    camera_id  TEXT UNIQUE NOT NULL,
    longitude  DOUBLE PRECISION,
    latitude   DOUBLE PRECISION,
    zone_id    INTEGER REFERENCES zones(id) ON DELETE SET NULL
);

-- Police stations serving the mela area
CREATE TABLE police_stations (
    id           SERIAL PRIMARY KEY,
    station_name TEXT NOT NULL,
    longitude    DOUBLE PRECISION,
    latitude     DOUBLE PRECISION
);

-- Traffic chokepoints, transfer nodes, and parking zones
CREATE TABLE chokepoints_parking (
    id            SERIAL PRIMARY KEY,
    location_name TEXT NOT NULL,
    category      TEXT,
    longitude     DOUBLE PRECISION,
    latitude      DOUBLE PRECISION
);

-- Synthetic missing persons cases (2,500 records)
CREATE TABLE missing_persons (
    id                   SERIAL PRIMARY KEY,
    case_id              TEXT UNIQUE NOT NULL,
    reported_at          TIMESTAMP,
    missing_person_name  TEXT,
    gender               TEXT,
    age_band             TEXT,
    state                TEXT,
    district             TEXT,
    language             TEXT,
    last_seen_location   TEXT,
    reporting_center     TEXT,
    reporter_mobile      TEXT,
    physical_description TEXT,
    status               TEXT,
    resolution_hours     NUMERIC,
    is_duplicate_report  BOOLEAN,
    remarks              TEXT
);

-- Indexes for common query patterns
CREATE INDEX idx_missing_persons_status      ON missing_persons(status);
CREATE INDEX idx_missing_persons_reported_at ON missing_persons(reported_at);
CREATE INDEX idx_missing_persons_is_dup      ON missing_persons(is_duplicate_report);
CREATE INDEX idx_missing_persons_case_id     ON missing_persons(case_id);
CREATE INDEX idx_cctv_cameras_zone_id        ON cctv_cameras(zone_id);
CREATE INDEX idx_chokepoints_category        ON chokepoints_parking(category);
"""


def parse_bool(val):
    if val is None or val.strip() == "":
        return None
    return val.strip().lower() == "true"


def parse_float(val):
    if val is None or val.strip() == "":
        return None
    return float(val.strip())


def parse_int(val):
    if val is None or val.strip() == "":
        return None
    return int(val.strip())


def nullify(val):
    if val is None or val.strip() == "":
        return None
    return val.strip()


def load_zones(cur):
    rows = []
    with open(f"{DATA_DIR}/Zone_Boundaries.csv") as f:
        for r in csv.DictReader(f):
            rows.append((
                r["zone_name"].strip(),
                parse_float(r["centroid_lat"]),
                parse_float(r["centroid_lng"]),
                parse_int(r["approx_boundary_points"]),
            ))
    execute_batch(cur, """
        INSERT INTO zones (zone_name, centroid_lat, centroid_lng, approx_boundary_points)
        VALUES (%s, %s, %s, %s)
    """, rows)
    print(f"  zones: {len(rows)} rows inserted")


def load_cctv(cur):
    # Build zone_name → id map
    cur.execute("SELECT id, zone_name FROM zones")
    zone_map = {name: zid for zid, name in cur.fetchall()}

    rows = []
    with open(f"{DATA_DIR}/CCTV_Locations.csv") as f:
        for r in csv.DictReader(f):
            cam_id = r["camera_id"].strip()
            # Extract zone number: Z3-C12 → 3 → "Zone Area 3"
            zone_num = cam_id.split("-")[0][1:]
            zone_name = f"Zone Area {zone_num}"
            zone_id = zone_map.get(zone_name)
            rows.append((
                cam_id,
                parse_float(r["longitude"]),
                parse_float(r["latitude"]),
                zone_id,
            ))
    execute_batch(cur, """
        INSERT INTO cctv_cameras (camera_id, longitude, latitude, zone_id)
        VALUES (%s, %s, %s, %s)
    """, rows)
    print(f"  cctv_cameras: {len(rows)} rows inserted")


def load_police_stations(cur):
    rows = []
    with open(f"{DATA_DIR}/Police_Stations.csv") as f:
        for r in csv.DictReader(f):
            rows.append((
                r["station_name"].strip(),
                parse_float(r["longitude"]),
                parse_float(r["latitude"]),
            ))
    execute_batch(cur, """
        INSERT INTO police_stations (station_name, longitude, latitude)
        VALUES (%s, %s, %s)
    """, rows)
    print(f"  police_stations: {len(rows)} rows inserted")


def load_chokepoints(cur):
    rows = []
    with open(f"{DATA_DIR}/Chokepoints_Parking.csv") as f:
        for r in csv.DictReader(f):
            rows.append((
                r["location_name"].strip(),
                nullify(r.get("category", "")),
                parse_float(r["longitude"]),
                parse_float(r["latitude"]),
            ))
    execute_batch(cur, """
        INSERT INTO chokepoints_parking (location_name, category, longitude, latitude)
        VALUES (%s, %s, %s, %s)
    """, rows)
    print(f"  chokepoints_parking: {len(rows)} rows inserted")


def load_missing_persons(cur):
    rows = []
    with open(f"{DATA_DIR}/Synthetic_Missing_Persons_2500.csv") as f:
        for r in csv.DictReader(f):
            rows.append((
                r["case_id"].strip(),
                nullify(r["reported_at"]),
                nullify(r["missing_person_name"]),
                nullify(r["gender"]),
                nullify(r["age_band"]),
                nullify(r["state"]),
                nullify(r["district"]),
                nullify(r["language"]),
                nullify(r["last_seen_location"]),
                nullify(r["reporting_center"]),
                nullify(r["reporter_mobile"]),
                nullify(r["physical_description"]),
                nullify(r["status"]),
                parse_float(r["resolution_hours"]),
                parse_bool(r["is_duplicate_report"]),
                nullify(r["remarks"]),
            ))
    execute_batch(cur, """
        INSERT INTO missing_persons (
            case_id, reported_at, missing_person_name, gender, age_band,
            state, district, language, last_seen_location, reporting_center,
            reporter_mobile, physical_description, status, resolution_hours,
            is_duplicate_report, remarks
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, rows)
    print(f"  missing_persons: {len(rows)} rows inserted")


def main():
    print("Connecting to Supabase...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Creating schema...")
        cur.execute(SCHEMA_SQL)

        print("Loading data...")
        load_zones(cur)
        load_cctv(cur)
        load_police_stations(cur)
        load_chokepoints(cur)
        load_missing_persons(cur)

        conn.commit()
        print("\nAll data uploaded successfully.")

        # Quick verification
        print("\nRow counts:")
        for table in ["zones", "cctv_cameras", "police_stations", "chokepoints_parking", "missing_persons"]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table}: {cur.fetchone()[0]}")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
