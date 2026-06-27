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
import { AGE_BANDS, GENDERS, badgeClass } from '../../core/constants';
import { AdminStats, Filters, GeoData, Hotspot, MissingPerson, ReportFoundPayload } from '../../core/models';
import { TranslatePipe } from '../../core/translate.pipe';
import { LangToggle } from '../../shared/lang-toggle';
import { PhotoCapture } from '../../shared/photo-capture';
import { ConfirmDialog } from '../../shared/confirm-dialog';

type Tab = 'dashboard' | 'search' | 'report' | 'duplicates' | 'map' | 'hotspots';

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

  ageBands = AGE_BANDS;
  genders = GENDERS;
  badgeClass = badgeClass;

  tab = signal<Tab>('dashboard');
  tabs: { key: Tab; label: string; icon: string }[] = [
    { key: 'dashboard', label: 'ctrl.dashboard', icon: 'dashboard' },
    { key: 'search', label: 'ctrl.searchMissing', icon: 'search' },
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

  ngOnInit(): void {
    this.api.adminStats().subscribe(s => this.stats.set(s));
    this.api.filters().subscribe(f => this.filters.set(f));
  }

  go(t: Tab): void {
    this.tab.set(t);
    if (t === 'map') setTimeout(() => this.initMap(), 80);
    if (t === 'hotspots' && !this.hotspots().length) this.api.hotspots().subscribe(r => this.hotspots.set(r.hotspots || []));
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
}
