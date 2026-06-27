# Drishti — Supabase setup

The Drishti PWA is **serverless**: the Angular app talks to Supabase directly via
`@supabase/supabase-js` (PostgREST + RPC + Supabase Auth). There is no Flask
server to run. Project: `dtqbturxigckqiqfzdnb`.

## Files

| File | Purpose |
|------|---------|
| `01_schema.sql` | Tables, indexes, RLS policies, profile trigger. Idempotent (`create … if not exists`, `drop policy if exists`). |
| `02_functions.sql` | RPC aggregations: `app_public_stats`, `app_admin_stats`, `app_filters`, `app_hotspots`. |
| `03_auth_seed.sql` | Creates 3 demo auth users **for a brand-new project** (`@drishti.local`). *Not used here* — this project already has accounts. |
| `04_seed_data.sql` | Full data seed generated from `../data/*.csv` (2500 missing persons + all geo). **Truncates** first — only for a fresh project. |
| `05_seed_geo.sql` | Geo seed for **empty** tables only (`cctv`, `chokepoints`). Safe — no truncate. |
| `06_demo_passwords.sql` | (Re)sets passwords on the existing demo accounts so you can log in. |

## This project (already provisioned)

The database already has the schema, 2500 `missing_persons`, and three auth
accounts. What was applied to make the app work:

```
01_schema.sql     -- RLS policies + corrected profile trigger
02_functions.sql  -- RPC aggregations
05_seed_geo.sql   -- filled the empty cctv + chokepoints tables
06_demo_passwords.sql -- set known demo passwords
```

### Demo logins

| Portal | Username (type this) | Email | Password | Role |
|--------|----------------------|-------|----------|------|
| Control Centre | `admin` | admin@drishti.in | `admin123` | admin |
| Volunteer | `volunteer` | volunteer@drishti.in | `vol123` | volunteer |
| Family | `family` | registree@drishti.in | `family123` | pre_registree |

The login form accepts the bare username; the app maps it to the email
(`family` → `registree@drishti.in`). The Family portal also works in
guest mode (search only) without logging in.

## Fresh project from scratch

Run in the Supabase SQL editor in order: `01` → `02` → `04` → `03`.
(`04` seeds + truncates; `03` creates `@drishti.local` demo users.)

## Notes

- The anon key in `frontend/src/environments/environment.ts` is public and safe
  to ship **because RLS is enabled on every table**. Reads are public; writes
  require an authenticated session.
- Fuzzy matching runs **client-side** (`frontend/src/app/core/fuzzy.ts`) — no
  Python/rapidfuzz dependency.
