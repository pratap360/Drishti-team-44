import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, from } from 'rxjs';
import { SupabaseService } from './supabase.service';
import { environment } from '../../environments/environment';
import { Role } from './models';

export interface CurrentUser {
  username: string;
  role: Role;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private sb = inject(SupabaseService).client;

  /** null = not authenticated, undefined = not yet checked. */
  readonly user = signal<CurrentUser | null | undefined>(undefined);
  readonly isAuthenticated = computed(() => !!this.user());
  readonly role = computed(() => this.user()?.role ?? null);

  constructor() {
    // Keep the signal in sync with Supabase session changes.
    this.sb.auth.onAuthStateChange((_evt, session) => {
      if (!session) { this.user.set(null); return; }
      this.loadProfile(session.user.id, session.user.email || '');
    });
  }

  /** Map a bare username to the seeded email (passes through real emails). */
  private toEmail(username: string): string {
    if (username.includes('@')) return username;
    // Family portal logins use the `registree` account.
    const alias: Record<string, string> = { family: 'registree', pre_registree: 'registree' };
    const local = alias[username.toLowerCase()] ?? username;
    return `${local}@${environment.authEmailDomain}`;
  }

  private async loadProfile(userId: string, email: string): Promise<CurrentUser | null> {
    const { data } = await this.sb.from('profiles').select('full_name,role').eq('id', userId).maybeSingle();
    const u: CurrentUser = {
      username: (data?.['full_name'] as string) || email.split('@')[0],
      role: ((data?.['role'] as Role) || 'pre_registree'),
    };
    this.user.set(u);
    return u;
  }

  refresh(): Observable<CurrentUser | null> {
    return from((async () => {
      const { data } = await this.sb.auth.getSession();
      if (!data.session) { this.user.set(null); return null; }
      return this.loadProfile(data.session.user.id, data.session.user.email || '');
    })());
  }

  login(username: string, password: string, role?: Role): Observable<{ ok: boolean; role?: Role; error?: string }> {
    return from((async () => {
      const { data, error } = await this.sb.auth.signInWithPassword({ email: this.toEmail(username.trim()), password });
      if (error || !data.session) return { ok: false, error: error?.message || 'Invalid credentials' };
      const u = await this.loadProfile(data.session.user.id, data.session.user.email || '');
      if (role && u && u.role !== role) {
        await this.sb.auth.signOut();
        this.user.set(null);
        return { ok: false, error: 'Role mismatch — use the matching portal account.' };
      }
      return { ok: true, role: u?.role };
    })());
  }

  logout(): Observable<unknown> {
    return from((async () => {
      await this.sb.auth.signOut();
      this.user.set(null);
      return null;
    })());
  }
}
