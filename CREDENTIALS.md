# Drishti — User Credentials & Role Permissions

> **Dev only. Do not commit to a public repo.**

---

## Users

| Role | Email | Password |
|---|---|---|
| Admin | admin@drishti.in | Admin1234 |
| Volunteer | volunteer@drishti.in | Volun1234 |
| Pre-registree | registree@drishti.in | Regis1234 |

---

## Role Permissions

### Admin
Full access to every table and every operation (SELECT / INSERT / UPDATE / DELETE).
Can also view and manage all user profiles.

### Volunteer
| Table | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|
| missing_persons | All rows | Yes | Yes | No |
| zones | Yes | No | No | No |
| cctv_cameras | Yes | No | No | No |
| police_stations | Yes | No | No | No |
| chokepoints_parking | Yes | No | No | No |
| profiles | Own row only | No | No | No |

### Pre-registree
| Table | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|
| missing_persons | All rows | Yes (file a report) | No | No |
| zones | Yes | No | No | No |
| cctv_cameras | Yes | No | No | No |
| police_stations | Yes | No | No | No |
| chokepoints_parking | Yes | No | No | No |
| profiles | Own row only | No | No | No |

---

## How It Works

- All permissions are enforced via **Postgres Row Level Security (RLS)** on each table.
- A `profiles` table links `auth.users.id` to a `user_role` enum (`admin`, `volunteer`, `pre_registree`).
- A `SECURITY DEFINER` function `current_user_role()` reads the caller's role without recursing into RLS.
- Reference tables (zones, cameras, stations, chokepoints) are **read-only** for non-admins.
- Only **admin** can delete missing_persons records.

---

## Supabase Project

- **URL:** https://dtqbturxigckqiqfzdnb.supabase.co
- **Project ID:** dtqbturxigckqiqfzdnb
