import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { AuthService } from '../core/auth.service';
import { LanguageService } from '../core/language.service';
import { Role } from '../core/models';
import { TranslatePipe } from '../core/translate.pipe';

export interface LoginDialogData {
  role?: Role;
  roleLabel?: string;
  allowGuest?: boolean;
}

export type LoginDialogResult = { ok: true; role: Role } | { guest: true } | undefined;

@Component({
  selector: 'app-login-dialog',
  imports: [
    FormsModule, MatDialogModule, MatFormFieldModule, MatInputModule,
    MatButtonModule, MatProgressSpinnerModule, TranslatePipe,
  ],
  template: `
    <h2 mat-dialog-title class="title">{{ 'landing.modalTitle' | t }}</h2>
    <mat-dialog-content>
      <p class="muted sub">{{ 'landing.modalSub' | t }}</p>
      @if (data.roleLabel) { <span class="role-badge">{{ data.roleLabel }}</span> }
      @if (error()) { <div class="err">{{ error() }}</div> }

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>{{ 'common.username' | t }}</mat-label>
        <input matInput [(ngModel)]="username" name="username" autocomplete="username"
               (keydown.enter)="submit()">
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>{{ 'common.password' | t }}</mat-label>
        <input matInput type="password" [(ngModel)]="password" name="password"
               autocomplete="current-password" (keydown.enter)="submit()">
      </mat-form-field>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      @if (data.allowGuest) {
        <button mat-button (click)="guest()">{{ 'landing.guestLink' | t }}</button>
      }
      <button mat-flat-button class="brand-btn" (click)="submit()" [disabled]="busy()">
        @if (busy()) { <mat-spinner diameter="18" /> } @else { {{ 'common.signIn' | t }} }
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .title { color: var(--brand-primary-dark); }
    .sub { margin-top: -8px; font-size: 13px; }
    .role-badge {
      display: inline-block; padding: 4px 12px; border-radius: 20px;
      font-size: 12px; font-weight: 600; margin-bottom: 14px; color: #fff;
      background: linear-gradient(135deg,#e65100,#880e4f);
    }
    .err {
      background: #ffebee; color: #c62828; border-radius: 8px;
      padding: 10px 14px; font-size: 13px; margin-bottom: 14px;
    }
    mat-dialog-content { display: flex; flex-direction: column; min-width: 280px; }
    .brand-btn { min-width: 96px; }
    mat-spinner { display: inline-block; }
  `],
})
export class LoginDialog {
  data = inject<LoginDialogData>(MAT_DIALOG_DATA);
  private ref = inject(MatDialogRef<LoginDialog, LoginDialogResult>);
  private auth = inject(AuthService);
  private langSvc = inject(LanguageService);

  username = '';
  password = '';
  busy = signal(false);
  error = signal('');

  submit(): void {
    if (!this.username || !this.password) {
      this.error.set(this.langSvc.t('common.invalidCreds'));
      return;
    }
    this.busy.set(true);
    this.error.set('');
    this.auth.login(this.username.trim(), this.password, this.data.role).subscribe(r => {
      this.busy.set(false);
      if (r.ok && r.role) {
        this.ref.close({ ok: true, role: r.role });
      } else {
        this.error.set(r.error || this.langSvc.t('common.invalidCreds'));
      }
    });
  }

  guest(): void {
    this.ref.close({ guest: true });
  }
}
