import { Component, HostListener, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LanguageService } from '../../core/language.service';
import { Role } from '../../core/models';
import { TranslatePipe } from '../../core/translate.pipe';
import { LangToggle } from '../../shared/lang-toggle';
import { LoginDialog, LoginDialogData, LoginDialogResult } from '../../shared/login-dialog';

interface PortalCard {
  key: 'family' | 'volunteer' | 'control';
  route: string;
  icon: string;
  cls: string;
  role: Role;
  allowGuest: boolean;
  features: string[];
}

@Component({
  selector: 'app-landing',
  imports: [MatButtonModule, TranslatePipe, LangToggle],
  templateUrl: './landing.html',
  styleUrl: './landing.scss',
})
export class Landing implements OnInit {
  private api = inject(ApiService);
  private dialog = inject(MatDialog);
  private router = inject(Router);
  auth = inject(AuthService);
  lang = inject(LanguageService);

  total = signal<string>('—');
  reunited = signal<string>('—');
  avg = signal<string>('—');

  private deferredPrompt: any = null;
  canInstall = signal(false);

  cards: PortalCard[] = [
    { key: 'family', route: '/family', icon: '👪', cls: 'card-family', role: 'pre_registree', allowGuest: true,
      features: ['landing.f1', 'landing.f2', 'landing.f3', 'landing.f4', 'landing.f5'] },
    { key: 'volunteer', route: '/volunteer', icon: '🤝', cls: 'card-volunteer', role: 'volunteer', allowGuest: false,
      features: ['landing.v1', 'landing.v2', 'landing.v3', 'landing.v4', 'landing.v5', 'landing.v6'] },
    { key: 'control', route: '/control', icon: '🏛️', cls: 'card-control', role: 'admin', allowGuest: false,
      features: ['landing.c1', 'landing.c2', 'landing.c3', 'landing.c4', 'landing.c5', 'landing.c6'] },
  ];

  ngOnInit(): void {
    this.api.publicStats().subscribe({
      next: d => {
        this.total.set(d.total != null ? String(d.total) : '—');
        this.reunited.set(d.reunited != null ? String(d.reunited) : '—');
        this.avg.set(d.avg_resolution_hours != null
          ? `${d.avg_resolution_hours.toFixed(1)} ${this.lang.t('landing.hrs')}` : '—');
      },
      error: () => {},
    });
  }

  @HostListener('window:beforeinstallprompt', ['$event'])
  onBeforeInstall(e: Event): void {
    e.preventDefault();
    this.deferredPrompt = e;
    this.canInstall.set(true);
  }

  async install(): Promise<void> {
    if (!this.deferredPrompt) return;
    this.deferredPrompt.prompt();
    await this.deferredPrompt.userChoice;
    this.deferredPrompt = null;
    this.canInstall.set(false);
  }

  titleFor(c: PortalCard): string { return `landing.${c.key}Title`; }
  descFor(c: PortalCard): string { return `landing.${c.key}Desc`; }

  open(c: PortalCard): void {
    if (this.auth.role() === c.role || (c.role === 'pre_registree' && this.auth.isAuthenticated())) {
      this.router.navigate([c.route]);
      return;
    }
    const data: LoginDialogData = {
      role: c.role,
      roleLabel: this.lang.t(`landing.${c.key}Title`),
      allowGuest: c.allowGuest,
    };
    this.dialog.open(LoginDialog, { data, width: '420px' })
      .afterClosed().subscribe((res: LoginDialogResult) => {
        if (!res) return;
        if ('guest' in res) { this.router.navigate(['/family']); return; }
        if (res.ok) this.router.navigate([c.route]);
      });
  }

  openLogin(): void {
    this.dialog.open(LoginDialog, {
      data: { role: 'pre_registree', roleLabel: this.lang.t('landing.familyTitle'), allowGuest: true } as LoginDialogData,
      width: '420px',
    }).afterClosed().subscribe((res: LoginDialogResult) => {
      if (res && 'guest' in res) this.router.navigate(['/family']);
    });
  }

  logout(): void { this.auth.logout().subscribe(); }
}
