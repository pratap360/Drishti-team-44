import { Component, ElementRef, OnInit, ViewChild, inject, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LanguageService } from '../../core/language.service';
import { GeoService } from '../../core/geo.service';
import { QrService, SharePayload } from '../../core/qr.service';
import { OfflineQueueService } from '../../core/offline-queue.service';
import { AGE_BANDS, GENDERS, badgeClass } from '../../core/constants';
import { Chokepoint, MissingPerson, PoliceStation, ReportFoundPayload } from '../../core/models';
import { TranslatePipe } from '../../core/translate.pipe';
import { LangToggle } from '../../shared/lang-toggle';
import { PhotoCapture } from '../../shared/photo-capture';

type Page = 'home' | 'report' | 'search' | 'share' | 'nearby';

@Component({
  selector: 'app-volunteer',
  imports: [
    FormsModule, NgTemplateOutlet, MatToolbarModule, MatButtonModule, MatIconModule, MatCardModule,
    MatFormFieldModule, MatInputModule, MatSelectModule, MatProgressSpinnerModule,
    TranslatePipe, LangToggle, PhotoCapture,
  ],
  templateUrl: './volunteer.html',
  styleUrl: './volunteer.scss',
})
export class Volunteer implements OnInit {
  private api = inject(ApiService);
  private geoSvc = inject(GeoService);
  private qr = inject(QrService);
  private snack = inject(MatSnackBar);
  private router = inject(Router);
  auth = inject(AuthService);
  lang = inject(LanguageService);
  offline = inject(OfflineQueueService);

  ageBands = AGE_BANDS;
  genders = GENDERS;
  badgeClass = badgeClass;

  page = signal<Page>('home');

  // stats
  total = signal('—'); reunited = signal('—'); avg = signal('—');

  // report
  form: ReportFoundPayload = this.blank();
  photo = '';
  submitting = signal(false);
  registered = signal(false);
  matches = signal<MissingPerson[]>([]);
  private lastReport: ReportFoundPayload | null = null;

  // search
  q = ''; sGender = ''; sAge = ''; sLang = ''; sState = '';
  results = signal<MissingPerson[]>([]);
  searching = signal(false);

  // share / scan
  scanning = signal(false);
  scanResult = signal<ReportFoundPayload | null>(null);
  private stopScan?: () => void;

  // nearby
  police = signal<PoliceStation[]>([]);
  chokepoints = signal<Chokepoint[]>([]);

  @ViewChild('qrCanvas') qrCanvas?: ElementRef<HTMLCanvasElement>;
  @ViewChild('scanVideo') scanVideo?: ElementRef<HTMLVideoElement>;
  @ViewChild('scanCanvas') scanCanvas?: ElementRef<HTMLCanvasElement>;

  ngOnInit(): void {
    this.api.publicStats().subscribe(d => {
      this.total.set(String(d.total ?? '—'));
      this.reunited.set(String(d.reunited ?? '—'));
      this.avg.set(d.avg_resolution_hours != null ? `${d.avg_resolution_hours.toFixed(1)}` : '—');
    });
  }

  blank(): ReportFoundPayload {
    return { person_name: '', gender: '', age_band: '', state: '', language: '',
      found_location: '', reporting_center: '', contact_mobile: '', physical_description: '', remarks: '' };
  }

  nav(p: Page): void {
    this.page.set(p);
    if (p === 'nearby' && !this.police().length) this.loadNearby();
    if (p === 'share') setTimeout(() => this.renderQr(), 50);
  }

  exit(): void { this.router.navigate(['/']); }
  logout(): void { this.auth.logout().subscribe(() => this.router.navigate(['/'])); }

  // ─── GPS ──────────────────────────────────────────────────────────────
  async fillGps(): Promise<void> {
    try {
      const { lat, lng } = await this.geoSvc.getCurrentPosition();
      this.form.found_location = `Lat: ${lat.toFixed(5)}, Lng: ${lng.toFixed(5)}`;
    } catch {
      this.snack.open('Could not get location', 'OK', { duration: 3000 });
    }
  }

  // ─── Report found ───────────────────────────────────────────────────────
  submit(): void {
    const payload: ReportFoundPayload = { ...this.form, photo: this.photo };
    this.lastReport = payload;
    this.submitting.set(true);

    if (!this.offline.online()) {
      this.offline.queueReport(payload).then(() => {
        this.submitting.set(false);
        this.registered.set(true);
        this.matches.set([]);
        this.snack.open(this.lang.t('vol.offline'), 'OK', { duration: 4000, panelClass: 'snack-info' });
      });
      return;
    }

    this.api.reportFound(payload).subscribe({
      next: res => {
        this.submitting.set(false);
        if (res.ok) {
          this.registered.set(true);
          this.api.fuzzyMatch({
            name: payload.person_name || '', gender: payload.gender || '', age_band: payload.age_band || '',
            state: payload.state || '', language: payload.language || '', description: payload.physical_description || '',
          }).subscribe(m => this.matches.set(m.matches || []));
        } else {
          this.snack.open((res.errors || []).join(', ') || 'Submit failed', 'OK', { duration: 4000, panelClass: 'snack-error' });
        }
      },
      error: () => {
        // network failure → queue offline
        this.offline.queueReport(payload).then(() => {
          this.submitting.set(false);
          this.registered.set(true);
          this.snack.open(this.lang.t('vol.offline'), 'OK', { duration: 4000, panelClass: 'snack-info' });
        });
      },
    });
  }

  reset(): void { this.form = this.blank(); this.photo = ''; this.registered.set(false); this.matches.set([]); }

  lastReportExists(): boolean { return !!this.lastReport; }

  async sync(): Promise<void> {
    const n = await this.offline.sync();
    this.snack.open(`${this.lang.t('vol.synced')} (${n})`, 'OK', { duration: 3000, panelClass: 'snack-success' });
  }

  // ─── Search missing ─────────────────────────────────────────────────────
  search(): void {
    this.searching.set(true);
    this.api.search({ q: this.q, gender: this.sGender, age_band: this.sAge, language: this.sLang, state: this.sState })
      .subscribe({
        next: r => { this.results.set(r.results || []); this.searching.set(false); },
        error: () => { this.searching.set(false); },
      });
  }

  // ─── Share / QR ─────────────────────────────────────────────────────────
  async renderQr(): Promise<void> {
    if (this.lastReport && this.qrCanvas) {
      await this.qr.toCanvas(this.qrCanvas.nativeElement, this.qr.encodeReport(this.lastReport));
    }
  }

  async startScan(): Promise<void> {
    this.scanning.set(true);
    this.scanResult.set(null);
    setTimeout(async () => {
      if (!this.scanVideo || !this.scanCanvas) return;
      this.stopScan = await this.qr.startScan(
        this.scanVideo.nativeElement, this.scanCanvas.nativeElement,
        (p: SharePayload) => {
          this.scanning.set(false);
          const report = this.qr.decodeReport(p);
          this.scanResult.set(report);
          this.offline.saveShare(report);
          if (this.offline.online()) {
            this.api.reportFound(report).subscribe(() =>
              this.snack.open('Imported & synced', 'OK', { duration: 3000, panelClass: 'snack-success' }));
          } else {
            this.snack.open('Saved locally — will sync', 'OK', { duration: 3000, panelClass: 'snack-info' });
          }
        },
        () => { this.scanning.set(false); this.snack.open('Camera access denied', 'OK', { duration: 3000, panelClass: 'snack-error' }); },
      );
    }, 50);
  }

  cancelScan(): void { this.stopScan?.(); this.scanning.set(false); }

  // ─── Nearby ───────────────────────────────────────────────────────────
  loadNearby(): void {
    this.api.geo().subscribe(g => {
      this.police.set(g.police_stations || []);
      this.chokepoints.set(g.chokepoints || []);
    });
  }

  navigateTo(lat: number, lng: number): void {
    window.open(`https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`, '_blank');
  }
}
