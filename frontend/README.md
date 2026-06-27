# Drishti — Reunification System (Angular 20 PWA)

A serverless, installable Progressive Web App for reuniting missing persons at
the Nashik-Trimbakeshwar Simhastha Kumbh Mela. Built with **Angular 20** +
**Angular Material**, talking **directly to Supabase** (no backend server).

## Portals

| Route | Portal | Who | Notes |
|-------|--------|-----|-------|
| `/` | Landing | everyone | Portal chooser, live stats, install prompt |
| `/family` | Family | families (guest or `pre_registree`) | Report missing, search found, track case |
| `/volunteer` | Volunteer | `volunteer` / `admin` | Report found, search, QR share (offline), nearby |
| `/control` | Control Centre | `admin` | Dashboard, search, duplicates, Leaflet map, hotspots |

## Run

```bash
cd frontend
npm install
npm start          # ng serve → http://localhost:4200
```

No backend needed — the app reads/writes Supabase directly. See
[`../supabase/README.md`](../supabase/README.md) for the database setup and the
demo logins (e.g. `admin` / `admin123`).

## Build

```bash
npm run build      # production build with PWA service worker → dist/frontend/browser
```

Deploy `dist/frontend/browser` to any static host (Vercel, Netlify, Supabase
Hosting, GitHub Pages). It is a fully static PWA.

## Architecture

- **Data layer:** `src/app/core/api.service.ts` — typed wrapper over Supabase
  (PostgREST queries + `app_*` RPC functions). Fuzzy matching is client-side in
  `src/app/core/fuzzy.ts`.
- **Auth:** `src/app/core/auth.service.ts` — Supabase Auth; role comes from the
  `profiles` table. Route guards in `src/app/core/guards/`.
- **i18n:** `src/app/core/i18n.ts` + `LanguageService` — English / Hindi /
  Marathi, toggled in-app, persisted in `localStorage`.
- **PWA:** `public/manifest.webmanifest` + Angular service worker
  (`ngsw-config.json`). Installable from the browser; offline app shell.
- **Offline queue:** `src/app/core/offline-queue.service.ts` — volunteer
  found-person reports are queued in IndexedDB when offline and auto-synced.

## Config

Supabase URL + anon key live in `src/environments/environment.ts`. The anon key
is public and safe to ship because **RLS is enabled on every table**.
