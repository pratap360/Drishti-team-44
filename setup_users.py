#!/usr/bin/env python3
"""Create roles, RLS policies, and 3 auth users in Supabase."""

import json
import os
import urllib.request
import urllib.error
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
DATABASE_URL = os.environ["DATABASE_POOLER_URL"]

USERS = [
    {"email": "admin@drishti.in",     "password": "Admin1234",  "role": "admin",         "full_name": "Drishti Admin"},
    {"email": "volunteer@drishti.in", "password": "Volun1234",  "role": "volunteer",     "full_name": "Field Volunteer"},
    {"email": "registree@drishti.in", "password": "Regis1234",  "role": "pre_registree", "full_name": "Pre Registree"},
]

# Each entry is a (label, sql) tuple executed individually
STATEMENTS = [
    ("create user_role enum", """
        DO $$ BEGIN
            CREATE TYPE user_role AS ENUM ('admin', 'volunteer', 'pre_registree');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """),

    ("create profiles table", """
        CREATE TABLE IF NOT EXISTS profiles (
            id         UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
            role       user_role NOT NULL DEFAULT 'pre_registree',
            full_name  TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """),

    ("enable RLS: profiles",            "ALTER TABLE profiles ENABLE ROW LEVEL SECURITY"),
    ("enable RLS: missing_persons",     "ALTER TABLE missing_persons ENABLE ROW LEVEL SECURITY"),
    ("enable RLS: zones",               "ALTER TABLE zones ENABLE ROW LEVEL SECURITY"),
    ("enable RLS: cctv_cameras",        "ALTER TABLE cctv_cameras ENABLE ROW LEVEL SECURITY"),
    ("enable RLS: police_stations",     "ALTER TABLE police_stations ENABLE ROW LEVEL SECURITY"),
    ("enable RLS: chokepoints_parking", "ALTER TABLE chokepoints_parking ENABLE ROW LEVEL SECURITY"),

    # Security-definer helper avoids RLS recursion when policies read profiles
    ("create current_user_role()", """
        CREATE OR REPLACE FUNCTION current_user_role()
        RETURNS user_role
        LANGUAGE sql STABLE SECURITY DEFINER
        AS 'SELECT role FROM profiles WHERE id = auth.uid()'
    """),

    # ── profiles policies ──────────────────────────────────────────────────
    ("drop profiles policies", """
        DO $$ BEGIN
            DROP POLICY IF EXISTS "profiles: own row"   ON profiles;
            DROP POLICY IF EXISTS "profiles: admin all" ON profiles;
        END $$
    """),
    ("policy profiles own row", """
        CREATE POLICY "profiles: own row"
            ON profiles FOR SELECT USING (id = auth.uid())
    """),
    ("policy profiles admin all", """
        CREATE POLICY "profiles: admin all"
            ON profiles FOR ALL USING (current_user_role() = 'admin')
    """),

    # ── zones ──────────────────────────────────────────────────────────────
    ("drop zones policies", """
        DO $$ BEGIN
            DROP POLICY IF EXISTS "zones: authenticated read" ON zones;
            DROP POLICY IF EXISTS "zones: admin write"        ON zones;
        END $$
    """),
    ("policy zones read", "CREATE POLICY \"zones: authenticated read\" ON zones FOR SELECT TO authenticated USING (true)"),
    ("policy zones admin write", "CREATE POLICY \"zones: admin write\" ON zones FOR ALL USING (current_user_role() = 'admin')"),

    # ── cctv_cameras ────────────────────────────────────────────────────────
    ("drop cctv policies", """
        DO $$ BEGIN
            DROP POLICY IF EXISTS "cctv: authenticated read" ON cctv_cameras;
            DROP POLICY IF EXISTS "cctv: admin write"        ON cctv_cameras;
        END $$
    """),
    ("policy cctv read",       "CREATE POLICY \"cctv: authenticated read\" ON cctv_cameras FOR SELECT TO authenticated USING (true)"),
    ("policy cctv admin write","CREATE POLICY \"cctv: admin write\" ON cctv_cameras FOR ALL USING (current_user_role() = 'admin')"),

    # ── police_stations ─────────────────────────────────────────────────────
    ("drop police policies", """
        DO $$ BEGIN
            DROP POLICY IF EXISTS "police: authenticated read" ON police_stations;
            DROP POLICY IF EXISTS "police: admin write"        ON police_stations;
        END $$
    """),
    ("policy police read",       "CREATE POLICY \"police: authenticated read\" ON police_stations FOR SELECT TO authenticated USING (true)"),
    ("policy police admin write","CREATE POLICY \"police: admin write\" ON police_stations FOR ALL USING (current_user_role() = 'admin')"),

    # ── chokepoints_parking ─────────────────────────────────────────────────
    ("drop choke policies", """
        DO $$ BEGIN
            DROP POLICY IF EXISTS "choke: authenticated read" ON chokepoints_parking;
            DROP POLICY IF EXISTS "choke: admin write"        ON chokepoints_parking;
        END $$
    """),
    ("policy choke read",       "CREATE POLICY \"choke: authenticated read\" ON chokepoints_parking FOR SELECT TO authenticated USING (true)"),
    ("policy choke admin write","CREATE POLICY \"choke: admin write\" ON chokepoints_parking FOR ALL USING (current_user_role() = 'admin')"),

    # ── missing_persons ─────────────────────────────────────────────────────
    ("drop mp policies", """
        DO $$ BEGIN
            DROP POLICY IF EXISTS "mp: admin all"        ON missing_persons;
            DROP POLICY IF EXISTS "mp: volunteer select" ON missing_persons;
            DROP POLICY IF EXISTS "mp: volunteer insert" ON missing_persons;
            DROP POLICY IF EXISTS "mp: volunteer update" ON missing_persons;
            DROP POLICY IF EXISTS "mp: registree select" ON missing_persons;
            DROP POLICY IF EXISTS "mp: registree insert" ON missing_persons;
        END $$
    """),
    ("policy mp admin all", """
        CREATE POLICY "mp: admin all"
            ON missing_persons FOR ALL
            USING (current_user_role() = 'admin')
    """),
    ("policy mp volunteer select", """
        CREATE POLICY "mp: volunteer select"
            ON missing_persons FOR SELECT
            USING (current_user_role() IN ('admin', 'volunteer'))
    """),
    ("policy mp volunteer insert", """
        CREATE POLICY "mp: volunteer insert"
            ON missing_persons FOR INSERT
            WITH CHECK (current_user_role() IN ('admin', 'volunteer'))
    """),
    ("policy mp volunteer update", """
        CREATE POLICY "mp: volunteer update"
            ON missing_persons FOR UPDATE
            USING (current_user_role() IN ('admin', 'volunteer'))
    """),
    ("policy mp registree select", """
        CREATE POLICY "mp: registree select"
            ON missing_persons FOR SELECT
            USING (current_user_role() = 'pre_registree')
    """),
    ("policy mp registree insert", """
        CREATE POLICY "mp: registree insert"
            ON missing_persons FOR INSERT
            WITH CHECK (current_user_role() = 'pre_registree')
    """),
]


def admin_request(method, path, body=None):
    url = f"{SUPABASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {SERVICE_KEY}",
        "apikey": SERVICE_KEY,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def create_or_get_user(email, password, full_name):
    result = admin_request("POST", "/auth/v1/admin/users", {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"full_name": full_name},
    })
    if "id" in result:
        return result["id"]
    # Already exists — find and reset password
    users = admin_request("GET", "/auth/v1/admin/users?per_page=1000")
    for u in users.get("users", []):
        if u["email"] == email:
            admin_request("PUT", f"/auth/v1/admin/users/{u['id']}", {"password": password})
            return u["id"]
    raise RuntimeError(f"Could not create or find user {email}: {result}")


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    print("Applying schema and RLS policies...")
    for label, sql in STATEMENTS:
        try:
            cur.execute(sql)
            print(f"  OK  {label}")
        except Exception as e:
            print(f"  ERR {label}: {e!s:.100}")

    print("\nCreating auth users and profiles...")
    for u in USERS:
        uid = create_or_get_user(u["email"], u["password"], u["full_name"])
        cur.execute("""
            INSERT INTO profiles (id, role, full_name)
            VALUES (%s, %s::user_role, %s)
            ON CONFLICT (id) DO UPDATE
                SET role = EXCLUDED.role, full_name = EXCLUDED.full_name
        """, (uid, u["role"], u["full_name"]))
        print(f"  {u['role']:15s}  {u['email']:30s}  uid={uid[:8]}…")

    print("\nFinal profiles:")
    cur.execute("SELECT role, full_name, id FROM profiles ORDER BY role")
    for row in cur.fetchall():
        print(f"  {str(row[0]):15s}  {row[1]:20s}  {str(row[2])[:8]}…")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
