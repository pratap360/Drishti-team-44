import { Component, OnInit, computed, inject, signal } from '@angular/core';
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
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatTabsModule } from '@angular/material/tabs';
import { MatBottomSheet, MatBottomSheetModule } from '@angular/material/bottom-sheet';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LanguageService } from '../../core/language.service';
import { AGE_BANDS, GENDERS, HELPLINES, RELATIONSHIPS, badgeClass } from '../../core/constants';
import { FoundPerson, ReportMissingPayload, TrackResult } from '../../core/models';
import { TranslatePipe } from '../../core/translate.pipe';
import { LangToggle } from '../../shared/lang-toggle';
import { PhotoCapture } from '../../shared/photo-capture';
import { ContactSheet } from './contact-sheet';

type Page = 'home' | 'report' | 'search' | 'track';

@Component({
  selector: 'app-family',
  imports: [
    FormsModule, MatToolbarModule, MatButtonModule, MatIconModule, MatCardModule,
    MatFormFieldModule, MatInputModule, MatSelectModule, MatCheckboxModule, MatTabsModule,
    MatBottomSheetModule, MatProgressSpinnerModule, NgTemplateOutlet,
    TranslatePipe, LangToggle, PhotoCapture,
  ],
  templateUrl: './family.html',
  styleUrl: './family.scss',
})
export class Family implements OnInit {
  private api = inject(ApiService);
  private sheet = inject(MatBottomSheet);
  private snack = inject(MatSnackBar);
  private router = inject(Router);
  auth = inject(AuthService);
  lang = inject(LanguageService);

  ageBands = AGE_BANDS;
  genders = GENDERS;
  relationships = RELATIONSHIPS;
  helplines = HELPLINES;
  badgeClass = badgeClass;

  page = signal<Page>('home');
  isGuest = computed(() => !this.auth.isAuthenticated());

  // stats
  total = signal('—'); reunited = signal('—');

  // report form
  form: ReportMissingPayload & { medical?: boolean; disability?: boolean; elderly?: boolean } = this.blankForm();
  reportPhoto = '';
  submitting = signal(false);
  caseRef = signal('');
  reportMatches = signal<FoundPerson[]>([]);

  // search
  searchTab = signal(0);
  foundGrid = signal<FoundPerson[]>([]);
  detailsName = ''; detailsGender = ''; detailsAge = ''; detailsLang = ''; detailsState = '';
  detailMatches = signal<FoundPerson[]>([]);
  searching = signal(false);

  // track
  trackQuery = '';
  trackResults = signal<TrackResult[]>([]);
  tracking = signal(false);

  ngOnInit(): void {
    this.api.publicStats().subscribe(d => {
      this.total.set(String(d.total ?? '—'));
      this.reunited.set(String(d.reunited ?? '—'));
    });
    this.loadFoundGrid();
  }

  blankForm() {
    return {
      person_name: '', gender: '', age_band: '', state: '', language: '',
      last_seen_location: '', last_seen_time: '', physical_description: '',
      aadhaar_last4: '', reporter_name: '', reporter_mobile: '', reporter_relationship: '',
      medical: false, disability: false, elderly: false,
    } as ReportMissingPayload & { medical?: boolean; disability?: boolean; elderly?: boolean };
  }

  nav(p: Page): void {
    if ((p === 'report' || p === 'track') && this.isGuest()) { this.router.navigate(['/']); return; }
    this.page.set(p);
  }

  exit(): void { this.router.navigate(['/']); }
  logout(): void { this.auth.logout().subscribe(() => this.router.navigate(['/'])); }

  private loadFoundGrid(): void {
    this.api.foundPersons({ limit: 50 }).subscribe(r => this.foundGrid.set(r.results || []));
  }

  // ─── Report ───────────────────────────────────────────────────────────
  submitReport(): void {
    const specials: string[] = [];
    if (this.form.medical) specials.push('Medical');
    if (this.form.disability) specials.push('Disability');
    if (this.form.elderly) specials.push('Elderly');
    const payload: ReportMissingPayload = {
      person_name: this.form.person_name, gender: this.form.gender, age_band: this.form.age_band,
      state: this.form.state, language: this.form.language,
      last_seen_location: this.form.last_seen_location, last_seen_time: this.form.last_seen_time,
      physical_description: this.form.physical_description, photo: this.reportPhoto,
      aadhaar_last4: this.form.aadhaar_last4, reporter_name: this.form.reporter_name,
      reporter_mobile: this.form.reporter_mobile, reporter_relationship: this.form.reporter_relationship,
      special_needs: specials.join(', '),
    };
    this.submitting.set(true);
    this.api.reportMissing(payload).subscribe({
      next: res => {
        this.submitting.set(false);
        if (res.ok && res.case_ref) {
          this.caseRef.set(res.case_ref);
          // fetch possible matches among found persons
          this.api.matchFound({
            name: payload.person_name || '', gender: payload.gender || '', age_band: payload.age_band || '',
            state: payload.state || '', language: payload.language || '', description: payload.physical_description || '',
          }).subscribe(m => this.reportMatches.set(m.matches || []));
        } else {
          this.snack.open((res.errors || []).join(', ') || 'Submit failed', 'OK', { duration: 4000, panelClass: 'snack-error' });
        }
      },
      error: () => { this.submitting.set(false); this.snack.open(this.lang.t('common.networkError'), 'OK', { duration: 4000, panelClass: 'snack-error' }); },
    });
  }

  resetReport(): void {
    this.form = this.blankForm();
    this.reportPhoto = '';
    this.caseRef.set('');
    this.reportMatches.set([]);
  }

  // ─── Search ───────────────────────────────────────────────────────────
  searchDetails(): void {
    if (this.isGuest()) { this.snack.open('Please log in to search by details.', 'Login', { duration: 4000 }); return; }
    this.searching.set(true);
    this.api.matchFound({
      name: this.detailsName, gender: this.detailsGender, age_band: this.detailsAge,
      state: this.detailsState, language: this.detailsLang, description: '',
    }).subscribe({
      next: m => { this.detailMatches.set(m.matches || []); this.searching.set(false); },
      error: () => { this.searching.set(false); },
    });
  }

  // ─── Track ────────────────────────────────────────────────────────────
  doTrack(): void {
    const q = this.trackQuery.trim();
    if (!q) return;
    this.tracking.set(true);
    const params = /^\d{6,}$/.test(q) ? { mobile: q } : { case_ref: q };
    this.api.track(params).subscribe({
      next: r => { this.trackResults.set(r.results || []); this.tracking.set(false); },
      error: () => { this.tracking.set(false); },
    });
  }

  timelineStep(status?: string): number {
    switch ((status || '').toLowerCase()) {
      case 'reunited': return 4;
      case 'matched': return 3;
      case 'searching': case 'pending': return 2;
      default: return 1;
    }
  }

  contact(p: FoundPerson): void {
    this.sheet.open(ContactSheet, { data: { foundId: p.id, mobile: p.contact_mobile } });
  }

  call(num: string): void { window.location.href = `tel:${num}`; }
}
