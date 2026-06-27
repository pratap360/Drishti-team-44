import { Injectable } from '@angular/core';

// Geo + CCTV-trace data and algorithms, ported from DRISHTI-Kumbh-Finder
// (app_data.js + index.html). Data is bundled as a static asset and loaded once.

export interface Camera { id: string; lng: number; lat: number; zone: string; }
export interface TraceZone { name: string; lat: number; lng: number; pts: number; cams: number; }
export interface Police { name: string; lng: number; lat: number; }
export interface Choke { name: string; cat: string; lng: number; lat: number; }
export interface SeenCoord { lat: number; lng: number; zone: string; }
export interface BBox { latMin: number; latMax: number; lngMin: number; lngMax: number; }

export interface GeoTraceData {
  cameras: Camera[]; zones: TraceZone[]; police: Police[]; choke: Choke[];
  seenCoords: Record<string, SeenCoord>; bbox: BBox;
}

/** A candidate CCTV sighting (simulated for the demo). */
export interface Sighting { cam: string; t: number; sc: number; }
/** A confirmed trajectory step. */
export interface TrajStep { zone: string; cam: string; t: number; }

export const AGES = ['0-12', '13-17', '18-40', '41-60', '61-70', '71-80', '80+'];

/** Record shape used by the match engine. */
export interface MatchRecord {
  name?: string; g?: string; age?: string; lang?: string; seen?: string; t?: string;
}

@Injectable({ providedIn: 'root' })
export class GeoTraceService {
  private data?: GeoTraceData;
  private loading?: Promise<GeoTraceData>;

  /** Load the bundled geo asset once (idempotent). */
  load(): Promise<GeoTraceData> {
    if (this.data) return Promise.resolve(this.data);
    if (!this.loading) {
      this.loading = fetch('data/geo-trace.json')
        .then(r => r.json())
        .then((d: GeoTraceData) => { this.data = d; return d; });
    }
    return this.loading;
  }

  get d(): GeoTraceData {
    if (!this.data) throw new Error('GeoTraceService.load() not awaited');
    return this.data;
  }

  // ─── geometry / lookups ─────────────────────────────────────────────────
  haversine(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
    const R = 6371, dLat = (b.lat - a.lat) * Math.PI / 180, dLng = (b.lng - a.lng) * Math.PI / 180;
    const s = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * Math.PI / 180) * Math.cos(b.lat * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(s));
  }
  coordOf(loc: string): SeenCoord | null { return this.d.seenCoords[loc] || null; }
  zoneOf(loc: string): string | null { return (this.d.seenCoords[loc] || {} as SeenCoord).zone || null; }
  zoneObj(name: string): TraceZone | undefined { return this.d.zones.find(z => z.name === name); }
  camsInZone(zone: string | null): Camera[] { return zone ? this.d.cameras.filter(c => c.zone === zone) : []; }
  nearestCams(c: { lat: number; lng: number } | null, n: number): { cm: Camera; d: number }[] {
    return c ? this.d.cameras.map(cm => ({ cm, d: this.haversine(c, cm) })).sort((a, b) => a.d - b.d).slice(0, n) : [];
  }
  nearestPolice(c: { lat: number; lng: number }): { p: Police; d: number } {
    return this.d.police.map(p => ({ p, d: this.haversine(c, p) })).sort((a, b) => a.d - b.d)[0];
  }
  seenLocations(): string[] { return Object.keys(this.d.seenCoords).sort(); }

  // ─── string similarity ──────────────────────────────────────────────────
  lev(a: string, b: string): number {
    a = (a || '').toLowerCase().trim(); b = (b || '').toLowerCase().trim();
    if (!a || !b) return 0; if (a === b) return 1;
    const m = a.length, n = b.length;
    const dp: number[][] = Array.from({ length: m + 1 }, (_, i) => [i, ...Array(n).fill(0)]);
    for (let j = 0; j <= n; j++) dp[0][j] = j;
    for (let i = 1; i <= m; i++) for (let j = 1; j <= n; j++)
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    return 1 - dp[m][n] / Math.max(m, n);
  }

  /** Likelihood (0..100) that two records are the same person — the match engine. */
  matchScore(q: MatchRecord, r: MatchRecord): number {
    let s = 0, max = 0;
    max += 20; if (q.g && r.g && q.g !== 'Unknown' && r.g !== 'Unknown') { s += q.g === r.g ? 20 : 0; } else max -= 10;
    max += 20; if (q.age && r.age) { s += q.age === r.age ? 20 : (Math.abs(AGES.indexOf(q.age) - AGES.indexOf(r.age)) === 1 ? 8 : 0); }
    max += 14; if (q.lang && r.lang) { s += q.lang === r.lang ? 14 : 0; } else max -= 7;
    max += 22;
    if (q.seen && r.seen) {
      if (q.seen === r.seen) s += 22;
      else { const ca = this.coordOf(q.seen), cb = this.coordOf(r.seen);
        if (ca && cb) { const d = this.haversine(ca, cb); s += d < 1 ? 16 : d < 3 ? 10 : d < 6 ? 4 : 0; } }
    }
    max += 18; if (q.name && r.name) { s += Math.round(18 * this.lev(q.name, r.name)); } else max -= 9;
    max += 6; if (q.t && r.t) { const dh = Math.abs(+new Date(q.t) - +new Date(r.t)) / 36e5; s += dh < 6 ? 6 : dh < 24 ? 4 : dh < 72 ? 2 : 0; }
    return Math.round(100 * s / Math.max(max, 1));
  }

  // ─── trace simulation ───────────────────────────────────────────────────
  private hashStr(s: string): number { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h) || 1; }
  private mkRng(seed: number): () => number { let x = seed % 2147483647; if (x <= 0) x += 2147483646; return () => (x = x * 16807 % 2147483647) / 2147483647; }
  parseTime(s: string): number { const p = (s || '09:00').split(':').map(Number); return (p[0] || 0) * 60 + (p[1] || 0); }
  fmtTime(mins: number): string {
    const m = ((mins % 1440) + 1440) % 1440;
    return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
  }

  /** Ranked candidate sightings in a zone within ±15 min (simulated for demo). */
  candidateSightings(loc: string, timeStr: string, mode: string): { zone: string | null; t0: number; track: 'A' | 'B'; cands: Sighting[] } {
    const zone = this.zoneOf(loc);
    const t0 = this.parseTime(timeStr);
    const track: 'A' | 'B' = mode === 'contains' ? 'A' : 'B';
    if (!zone) return { zone: null, t0, track, cands: [] };
    const zcams = this.camsInZone(zone);
    const rnd = this.mkRng(this.hashStr(loc + timeStr + mode));
    const cands: Sighting[] = [];
    for (let i = 0; i < 8; i++) {
      const cam = zcams.length ? zcams[Math.floor(rnd() * zcams.length)] : ({ id: '?' } as Camera);
      const sc = i === 0 ? (track === 'A' ? 0.88 + rnd() * 0.08 : 0.70 + rnd() * 0.10) : (track === 'A' ? 0.30 : 0.42) + rnd() * 0.22;
      cands.push({ cam: cam.id, t: t0 + Math.round(rnd() * 30 - 15), sc: Math.min(0.98, sc) });
    }
    cands.sort((a, b) => b.sc - a.sc);
    return { zone, t0, track, cands };
  }

  /** Greedy walk across walking-reachable zones (gated cross-zone search). */
  buildTrajectory(startZone: string, startCam: string, startT: number): TrajStep[] {
    const traj: TrajStep[] = [{ zone: startZone, cam: startCam, t: startT }];
    const visited = new Set([startZone]);
    let cur = this.zoneObj(startZone)!, t = startT, rnd = this.mkRng(this.hashStr(startZone + startCam));
    for (let i = 0; i < 5; i++) {
      t += 5;
      const near = this.d.zones.filter(z => !visited.has(z.name))
        .map(z => ({ z, d: this.haversine(cur, z) })).sort((a, b) => a.d - b.d).slice(0, 4);
      if (!near.length) break;
      const pick = near[Math.floor(rnd() * Math.min(3, near.length))].z;
      const cams = this.camsInZone(pick.name);
      traj.push({ zone: pick.name, cam: cams.length ? cams[Math.floor(rnd() * cams.length)].id : '?', t });
      visited.add(pick.name); cur = pick;
    }
    return traj;
  }
}
