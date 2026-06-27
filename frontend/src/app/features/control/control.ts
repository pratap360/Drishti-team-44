import { Component, ElementRef, OnInit, ViewChild, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LanguageService } from '../../core/language.service';
import { GeoTraceService, Sighting, TrajStep } from '../../core/geo-trace.service';
import { AGE_BANDS, GENDERS, badgeClass } from '../../core/constants';
import { AdminStats, Filters, GeoData, Hotspot, MissingPerson, ReportFoundPayload } from '../../core/models';
import { TranslatePipe } from '../../core/translate.pipe';
import { LangToggle } from '../../shared/lang-toggle';
import { PhotoCapture } from '../../shared/photo-capture';
import { ConfirmDialog } from '../../shared/confirm-dialog';

type Tab = 'dashboard' | 'unified' | 'search' | 'trace' | 'report' | 'duplicates' | 'map' | 'hotspots';

@Component({
  selector: 'app-control',
  imports: [
    FormsModule, MatToolbarModule, MatButtonModule, MatIconModule, MatCardModule,
    MatFormFieldModule, MatInputModule, MatSelectModule, MatTableModule,
    MatProgressSpinnerModule, MatCheckboxModule, TranslatePipe, LangToggle, PhotoCapture,
  ],
  templateUrl: './control.html',
  styleUrl: './control.scss',
})
export class Control implements OnInit {
  private api = inject(ApiService);
  private dialog = inject(MatDialog);
  private snack = inject(MatSnackBar);
  private router = inject(Router);
  auth = inject(AuthService);
  lang = inject(LanguageService);
  geo = inject(GeoTraceService);

  ageBands = AGE_BANDS;
  genders = GENDERS;
  badgeClass = badgeClass;

  tab = signal<Tab>('dashboard');
  tabs: { key: Tab; label: string; icon: string }[] = [
    { key: 'dashboard', label: 'ctrl.dashboard', icon: 'dashboard' },
    { key: 'unified', label: 'ctrl.unified', icon: 'travel_explore' },
    { key: 'search', label: 'ctrl.searchMissing', icon: 'search' },
    { key: 'trace', label: 'ctrl.trace', icon: 'videocam' },
    { key: 'report', label: 'ctrl.reportFound', icon: 'person_add' },
    { key: 'duplicates', label: 'ctrl.duplicates', icon: 'content_copy' },
    { key: 'map', label: 'ctrl.map', icon: 'map' },
    { key: 'hotspots', label: 'ctrl.hotspots', icon: 'local_fire_department' },
  ];

  stats = signal<AdminStats | null>(null);
  filters = signal<Filters | null>(null);

  // search
  q = ''; sGender = ''; sAge = ''; sState = ''; sLang = ''; sCenter = ''; sStatus = '';
  results = signal<MissingPerson[]>([]);
  searching = signal(false);
  cols = ['score', 'case_id', 'name', 'gender', 'age', 'location', 'center', 'status'];

  // report found
  form: ReportFoundPayload = this.blank();
  photo = '';
  matches = signal<MissingPerson[]>([]);
  lastFoundId = signal<number | null>(null);
  submitting = signal(false);

  // duplicates
  duplicateGroups = signal<MissingPerson[][]>([]);
  scanning = signal(false);

  // hotspots
  hotspots = signal<Hotspot[]>([]);

  // map
  private geoData?: GeoData;
  private map?: any;
  private layers: Record<string, any> = {};
  layerOn: Record<string, boolean> = { cctv: true, police: true, chokepoints: true, zones: false, heatmap: true };
  @ViewChild('mapEl') mapEl?: ElementRef<HTMLDivElement>;

  // ─── unified search ────────────────────────────────────────────────────
  seenOptions: string[] = [];
  uName = ''; uGender = ''; uAge = ''; uLang = ''; uSeen = ''; uStatus = '';
  uText = '';                         // free-text "smart fill"
  uResults = signal<{ r: MissingPerson; sc: number }[]>([]);
  uInfo = signal('');
  uSelected = signal<MissingPerson | null>(null);

  // ─── CCTV trace ────────────────────────────────────────────────────────
  trLoc = ''; trTime = '09:00'; trMode = 'none'; trGender = ''; trAge = ''; trColor = '';
  trCands = signal<Sighting[]>([]);
  trZone = signal<string | null>(null);
  trTrack = signal<'A' | 'B'>('B');
  trWindow = signal('');
  trTraj = signal<TrajStep[]>([]);
  trResult = signal<string>('');
  private traceMap?: any;
  private traceTrajLayer?: any;
  @ViewChild('traceMapEl') traceMapEl?: ElementRef<HTMLDivElement>;

  ngOnInit(): void {
    this.api.adminStats().subscribe(s => this.stats.set(s));
    this.api.filters().subscribe(f => this.filters.set(f));
  }

  go(t: Tab): void {
    this.tab.set(t);
    if (t === 'map') setTimeout(() => this.initMap(), 80);
    if (t === 'hotspots' && !this.hotspots().length) this.api.hotspots().subscribe(r => this.hotspots.set(r.hotspots || []));
    if (t === 'unified' || t === 'trace') {
      this.geo.load().then(() => { this.seenOptions = this.geo.seenLocations(); if (t === 'trace') setTimeout(() => this.initTraceMap(), 80); });
    }
  }

  logout(): void { this.auth.logout().subscribe(() => this.router.navigate(['/'])); }

  // ─── charts helpers ─────────────────────────────────────────────────────
  maxOf(arr: { count: number }[] | undefined): number {
    return Math.max(1, ...(arr || []).map(x => x.count));
  }

  // ─── search ──────────────────────────────────────────────────────────
  search(): void {
    this.searching.set(true);
    this.api.search({ q: this.q, gender: this.sGender, age_band: this.sAge, state: this.sState,
      language: this.sLang, center: this.sCenter, status: this.sStatus }).subscribe({
      next: r => { this.results.set(r.results || []); this.searching.set(false); },
      error: () => this.searching.set(false),
    });
  }

  // ─── report found + match + confirm ─────────────────────────────────────
  blank(): ReportFoundPayload {
    return { person_name: '', gender: '', age_band: '', state: '', language: '',
      found_location: '', reporting_center: '', contact_mobile: '', physical_description: '', remarks: '' };
  }

  submit(): void {
    const payload = { ...this.form, photo: this.photo };
    this.submitting.set(true);
    this.api.reportFound(payload).subscribe({
      next: res => {
        this.submitting.set(false);
        if (res.ok && res.id != null) {
          this.lastFoundId.set(res.id);
          this.api.fuzzyMatch({
            name: payload.person_name || '', gender: payload.gender || '', age_band: payload.age_band || '',
            state: payload.state || '', language: payload.language || '', description: payload.physical_description || '',
          }).subscribe(m => this.matches.set(m.matches || []));
          this.snack.open('Found person registered', 'OK', { duration: 3000, panelClass: 'snack-success' });
        } else {
          this.snack.open((res.errors || []).join(', ') || 'Failed', 'OK', { duration: 4000, panelClass: 'snack-error' });
        }
      },
      error: () => { this.submitting.set(false); this.snack.open(this.lang.t('common.networkError'), 'OK', { duration: 4000, panelClass: 'snack-error' }); },
    });
  }

  confirm(m: MissingPerson): void {
    const foundId = this.lastFoundId();
    if (foundId == null || !m.case_id) return;
    this.dialog.open(ConfirmDialog, {
      data: { title: this.lang.t('vol.confirmMatch'), message: this.lang.t('vol.confirmMatchMsg'),
        confirmLabel: this.lang.t('common.confirm'), cancelLabel: this.lang.t('common.cancel') },
    }).afterClosed().subscribe(ok => {
      if (!ok) return;
      this.api.confirmMatch(foundId, m.case_id!).subscribe(() => {
        this.snack.open(this.lang.t('vol.reuniteConfirmed'), 'OK', { duration: 3500, panelClass: 'snack-success' });
        this.matches.set([]);
        this.api.adminStats().subscribe(s => this.stats.set(s));
      });
    });
  }

  // ─── duplicates ────────────────────────────────────────────────────────
  scanDuplicates(): void {
    this.scanning.set(true);
    this.api.duplicates().subscribe({
      next: r => { this.duplicateGroups.set(r.duplicate_groups || []); this.scanning.set(false); },
      error: () => this.scanning.set(false),
    });
  }

  // ─── map (leaflet, lazy) ─────────────────────────────────────────────────
  async initMap(): Promise<void> {
    if (!this.mapEl) return;
    const L = await import('leaflet');
    await import('leaflet.heat');
    if (!this.map) {
      this.map = L.map(this.mapEl.nativeElement).setView([20.0, 73.78], 12);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap', maxZoom: 19,
      }).addTo(this.map);
    }
    if (!this.geoData) {
      this.api.geo().subscribe(g => { this.geoData = g; this.buildLayers(L); });
    } else {
      this.buildLayers(L);
    }
    setTimeout(() => this.map?.invalidateSize(), 100);
  }

  private buildLayers(L: any): void {
    if (!this.geoData) return;
    Object.values(this.layers).forEach(l => this.map?.removeLayer(l));
    this.layers = {};

    this.layers['cctv'] = L.layerGroup((this.geoData.cctv || []).map(c =>
      L.circleMarker([c.latitude, c.longitude], { radius: 4, color: '#1565c0', fillOpacity: 0.7 })
        .bindPopup(`CCTV: ${c.camera_id ?? ''}`)));
    this.layers['police'] = L.layerGroup((this.geoData.police_stations || []).map(p =>
      L.circleMarker([p.latitude, p.longitude], { radius: 7, color: '#2e7d32', fillOpacity: 0.8 })
        .bindPopup(`Police: ${p.station_name ?? ''}`)));
    this.layers['chokepoints'] = L.layerGroup((this.geoData.chokepoints || []).map(c =>
      L.circleMarker([c.latitude, c.longitude], { radius: 6, color: '#c62828', fillOpacity: 0.7 })
        .bindPopup(`${c.location_name ?? ''} (${c.category ?? ''})`)));
    this.layers['zones'] = L.layerGroup((this.geoData.zones || []).map(z =>
      L.circle([z.centroid_lat, z.centroid_lng], { radius: 800, color: '#e65100', fillOpacity: 0.08 })
        .bindPopup(`Zone: ${z.zone_name ?? ''}`)));

    const heatPts = (this.geoData.chokepoints || []).map(c => [c.latitude, c.longitude, 0.6]);
    this.layers['heatmap'] = (L as any).heatLayer(heatPts, { radius: 25, blur: 18 });

    this.applyLayers();
  }

  toggleLayer(key: string): void {
    this.layerOn[key] = !this.layerOn[key];
    this.applyLayers();
  }

  private applyLayers(): void {
    if (!this.map) return;
    for (const [key, layer] of Object.entries(this.layers)) {
      if (this.layerOn[key]) layer.addTo(this.map);
      else this.map.removeLayer(layer);
    }
  }

  // ─── Unified Search (ranked cross-center match engine) ───────────────────
  scorePillClass(v: number): string { return v >= 70 ? 'p-hi' : v >= 50 ? 'p-md' : 'p-lo'; }

  /** Lightweight free-text → filters parser (serverless stand-in for "Smart fill"). */
  smartFill(): void {
    const t = this.uText.toLowerCase();
    if (/\b(male|man|boy|पुरुष)\b/.test(t)) this.uGender = 'Male';
    else if (/\b(female|woman|girl|lady|महिला)\b/.test(t)) this.uGender = 'Female';
    const age = t.match(/\b(\d{1,3})\s*(?:yrs?|years?|year-old|साल)?\b/);
    if (age) {
      const n = +age[1];
      this.uAge = n <= 12 ? '0-12' : n <= 17 ? '13-17' : n <= 40 ? '18-40' : n <= 60 ? '41-60' : n <= 70 ? '61-70' : n <= 80 ? '71-80' : '80+';
    }
    const loc = this.seenOptions.find(l => t.includes(l.toLowerCase()));
    if (loc) this.uSeen = loc;
    this.unifiedSearch();
  }

  unifiedSearch(): void {
    const q = { name: this.uName.trim(), g: this.uGender, age: this.uAge, lang: this.uLang, seen: this.uSeen };
    this.api.searchRaw({
      gender: this.uGender || undefined, age_band: this.uAge || undefined,
      language: this.uLang || undefined, status: this.uStatus || undefined,
    }, 1000).subscribe(rows => {
      let scored = rows.map(r => ({
        r,
        sc: this.geo.matchScore(q, {
          name: r.missing_person_name, g: r.gender, age: r.age_band,
          lang: r.language, seen: r.last_seen_location, t: r.reported_at,
        }),
      }));
      if (q.name) {
        scored = scored.filter(x =>
          this.geo.lev(q.name, x.r.missing_person_name || '') > 0.34 ||
          (x.r.missing_person_name || '').toLowerCase().includes(q.name.toLowerCase()));
      }
      scored = scored.filter(x => x.sc > 0).sort((a, b) => b.sc - a.sc).slice(0, 40);
      const centers = new Set(rows.map(r => r.reporting_center)).size;
      this.uInfo.set(`${scored.length} ranked result${scored.length !== 1 ? 's' : ''} across ${centers} centers`);
      this.uResults.set(scored);
    });
  }

  pickResult(r: MissingPerson): void { this.uSelected.set(this.uSelected() === r ? null : r); }

  /** Coverage summary for a selected record (nearest police + cameras in zone). */
  coverageOf(r: MissingPerson): string {
    const loc = r.last_seen_location || '';
    const c = this.geo.coordOf(loc);
    if (!c) return 'No mapped coordinates for this last-seen location.';
    const ps = this.geo.nearestPolice(c);
    const zone = this.geo.zoneOf(loc);
    const zc = this.geo.camsInZone(zone).length;
    const ncam = this.geo.d.cameras.filter(cm => this.geo.haversine(c, cm) < 0.8).length;
    return `Nearest police: ${ps.p.name} (${ps.d.toFixed(1)} km). ${ncam} cameras within 800 m of ${loc}. ` +
      (r.photo ? 'Photo on file → face-match enabled.' : `No photo → ${zc} cameras in ${zone} available for footage review.`);
  }

  clearUnified(): void {
    this.uName = this.uGender = this.uAge = this.uLang = this.uSeen = this.uStatus = this.uText = '';
    this.uResults.set([]); this.uInfo.set(''); this.uSelected.set(null);
  }

  // ─── CCTV Trace ──────────────────────────────────────────────────────────
  traceSearch(): void {
    const { zone, t0, track, cands } = this.geo.candidateSightings(this.trLoc, this.trTime, this.trMode);
    this.trZone.set(zone);
    this.trTrack.set(track);
    this.trWindow.set(`${this.geo.fmtTime(t0 - 15)}–${this.geo.fmtTime(t0 + 15)}`);
    this.trCands.set(cands);
    this.trTraj.set([]);
    this.trResult.set('');
    this.renderTrajectory();
  }

  confirmSighting(c: Sighting): void {
    const zone = this.trZone();
    if (!zone) return;
    const traj = this.geo.buildTrajectory(zone, c.cam, c.t);
    this.trTraj.set(traj);
    const last = traj[traj.length - 1];
    const lastZ = this.geo.zoneObj(last.zone)!;
    const ps = this.geo.nearestPolice(lastZ);
    this.trResult.set(
      `Sighting confirmed from cam ${c.cam} (${zone}) at ${this.geo.fmtTime(c.t)}. ` +
      `Tracked across ${traj.length} zones (each step gated to walking-reachable zones). ` +
      `Current estimate: ${last.zone} — cam ${last.cam} at ${this.geo.fmtTime(last.t)} ` +
      `(${last.t - c.t} min after confirmation). Nearest help-point: ${ps.p.name} (${ps.d.toFixed(1)} km).`,
    );
    this.renderTrajectory();
  }

  scorePct(sc: number): number { return Math.round(sc * 100); }

  private async initTraceMap(): Promise<void> {
    if (!this.traceMapEl) return;
    const L = await import('leaflet');
    if (!this.traceMap) {
      this.traceMap = L.map(this.traceMapEl.nativeElement).setView([20.0, 73.78], 12);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap', maxZoom: 19 }).addTo(this.traceMap);
      // static zone + police context
      this.geo.d.zones.forEach(z => L.circleMarker([z.lat, z.lng], { radius: 3, color: '#a371f7', fillOpacity: 0.4, stroke: false }).addTo(this.traceMap).bindPopup(z.name));
      this.geo.d.police.forEach(p => L.circleMarker([p.lat, p.lng], { radius: 5, color: '#fff', weight: 1, fillColor: '#2f81f7', fillOpacity: 1 }).addTo(this.traceMap).bindPopup('🚓 ' + p.name));
    }
    setTimeout(() => this.traceMap?.invalidateSize(), 100);
    this.renderTrajectory();
  }

  private async renderTrajectory(): Promise<void> {
    if (!this.traceMap) return;
    const L = await import('leaflet');
    if (this.traceTrajLayer) { this.traceMap.removeLayer(this.traceTrajLayer); this.traceTrajLayer = undefined; }
    const traj = this.trTraj();
    if (!traj.length) return;
    const pts = traj.map(s => { const z = this.geo.zoneObj(s.zone)!; return [z.lat, z.lng] as [number, number]; });
    const group = L.layerGroup();
    L.polyline(pts, { color: '#FF6A00', weight: 3 }).addTo(group);
    const lastZ = this.geo.zoneObj(traj[traj.length - 1].zone)!;
    const ps = this.geo.nearestPolice(lastZ);
    L.polyline([pts[pts.length - 1], [ps.p.lat, ps.p.lng]], { color: '#2f81f7', weight: 2, dashArray: '6,5' }).addTo(group);
    traj.forEach((s, i) => {
      const last = i === traj.length - 1;
      L.circleMarker(pts[i], { radius: last ? 8 : 6, weight: 2, color: '#fff', fillColor: i === 0 ? '#2ea043' : last ? '#e5484d' : '#FF6A00', fillOpacity: 1 })
        .bindTooltip(`${i + 1} · ${this.geo.fmtTime(s.t)}`, { permanent: true, direction: 'right', offset: [6, 0] })
        .bindPopup(`#${i + 1} <b>${s.zone}</b><br>cam ${s.cam} · ${this.geo.fmtTime(s.t)}`).addTo(group);
    });
    group.addTo(this.traceMap);
    this.traceTrajLayer = group;
    try { this.traceMap.fitBounds(L.latLngBounds(pts).pad(0.4)); } catch { /* single point */ }
  }
}
