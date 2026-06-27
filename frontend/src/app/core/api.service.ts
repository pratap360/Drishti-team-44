import { Injectable, inject } from '@angular/core';
import { Observable, from } from 'rxjs';
import { SupabaseService } from './supabase.service';
import { partialRatio, scoreMatch, tokenSortRatio } from './fuzzy';
import {
  AdminStats, Filters, FoundPerson, GeoData, Hotspot, MatchResponse,
  MissingPerson, PublicStats, ReportFoundPayload, ReportMissingPayload,
  ReportMissingResponse, SearchResponse, TrackResult,
} from './models';

function nowStamp(): string {
  return new Date().toISOString().slice(0, 16).replace('T', ' ');
}

/**
 * Serverless data layer — talks to Supabase directly (PostgREST + RPC).
 * Method names/return types match the previous Flask-backed service so the
 * feature components are unchanged. Fuzzy matching runs client-side (fuzzy.ts).
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private sb = inject(SupabaseService).client;

  // ─── Stats / filters (RPC) ────────────────────────────────────────────
  publicStats(): Observable<PublicStats> {
    return from((async () => {
      const { data } = await this.sb.rpc('app_public_stats');
      return (data ?? { total: 0, reunited: 0, avg_resolution_hours: 0 }) as PublicStats;
    })());
  }

  adminStats(): Observable<AdminStats> {
    return from((async () => {
      const { data } = await this.sb.rpc('app_admin_stats');
      return data as AdminStats;
    })());
  }

  filters(): Observable<Filters> {
    return from((async () => {
      const { data } = await this.sb.rpc('app_filters');
      return (data ?? { genders: [], ages: [], states: [], languages: [], centers: [] }) as Filters;
    })());
  }

  // ─── Search missing_persons ───────────────────────────────────────────
  search(params: Record<string, string | number | undefined>): Observable<SearchResponse<MissingPerson>> {
    return from((async () => {
      const q = String(params['q'] ?? '').trim();
      let query = this.sb.from('missing_persons').select('*').order('reported_at', { ascending: false });
      const eqMap: Record<string, string> = {
        gender: 'gender', age_band: 'age_band', state: 'state',
        language: 'language', center: 'reporting_center', status: 'status',
      };
      for (const [key, col] of Object.entries(eqMap)) {
        const v = params[key];
        if (v !== undefined && v !== '') query = query.eq(col, String(v));
      }
      query = query.limit(q ? 400 : 50);
      const { data } = await query;
      let results = (data ?? []) as MissingPerson[];

      if (q) {
        const ql = q.toLowerCase();
        const scored: MissingPerson[] = [];
        for (const r of results) {
          const best = Math.max(
            partialRatio(q, r.missing_person_name || ''),
            partialRatio(q, r.physical_description || ''),
            partialRatio(q, r.last_seen_location || ''),
            (r.case_id || '').toLowerCase().includes(ql) ? 100 : 0,
            (r.reporter_mobile || '').includes(q) ? 100 : 0,
          );
          if (best >= 45) { r.match_score = Math.round(best * 10) / 10; scored.push(r); }
        }
        scored.sort((a, b) => (b.match_score || 0) - (a.match_score || 0));
        results = scored.slice(0, 50);
      }
      return { results, count: results.length };
    })());
  }

  foundPersons(params: Record<string, string | number | undefined> = {}): Observable<SearchResponse<FoundPerson>> {
    return from((async () => {
      let query = this.sb.from('found_persons')
        .select('id,found_at,found_location,reporting_center,person_name,gender,age_band,state,language,physical_description,photo,status')
        .neq('status', 'Matched').order('found_at', { ascending: false });
      if (params['gender']) query = query.eq('gender', String(params['gender']));
      if (params['age_band']) query = query.eq('age_band', String(params['age_band']));
      query = query.limit(Number(params['limit'] ?? 50));
      const { data } = await query;
      const results = (data ?? []) as FoundPerson[];
      return { results, count: results.length };
    })());
  }

  // ─── Fuzzy matching (client-side) ──────────────────────────────────────
  fuzzyMatch(body: Record<string, string>): Observable<MatchResponse<MissingPerson>> {
    return from((async () => {
      let query = this.sb.from('missing_persons').select('*').in('status', ['Pending', 'Unresolved']);
      if (body['gender'] && body['gender'] !== 'Unknown') query = query.eq('gender', body['gender']);
      if (body['age_band']) query = query.eq('age_band', body['age_band']);
      const { data } = await query;
      const out: MissingPerson[] = [];
      for (const c of (data ?? []) as MissingPerson[]) {
        const { score, reasons } = scoreMatch(body, {
          name: c.missing_person_name, gender: c.gender, age_band: c.age_band,
          state: c.state, language: c.language, description: c.physical_description,
        });
        if (score >= 35) { c.match_score = score; c.match_reasons = reasons; out.push(c); }
      }
      out.sort((a, b) => (b.match_score || 0) - (a.match_score || 0));
      return { matches: out.slice(0, 20) };
    })());
  }

  matchFound(body: Record<string, string>): Observable<MatchResponse<FoundPerson>> {
    return from((async () => {
      let query = this.sb.from('found_persons').select('*').neq('status', 'Matched');
      if (body['gender'] && body['gender'] !== 'Unknown') query = query.eq('gender', body['gender']);
      if (body['age_band']) query = query.eq('age_band', body['age_band']);
      const { data } = await query;
      const out: FoundPerson[] = [];
      for (const c of (data ?? []) as FoundPerson[]) {
        const { score, reasons } = scoreMatch(body, {
          name: c.person_name, gender: c.gender, age_band: c.age_band,
          state: c.state, language: c.language, description: c.physical_description,
        });
        if (score >= 20) {
          c.match_score = score; c.match_reasons = reasons;
          const m = c.contact_mobile || '';
          if (m.length > 4) c.contact_mobile = m.slice(0, 3) + '****' + m.slice(-3);
          out.push(c);
        }
      }
      out.sort((a, b) => (b.match_score || 0) - (a.match_score || 0));
      return { matches: out.slice(0, 20) };
    })());
  }

  confirmMatch(found_id: number, case_id: string): Observable<{ ok: boolean }> {
    return from((async () => {
      await this.sb.from('found_persons').update({ matched_case_id: case_id, status: 'Matched' }).eq('id', found_id);
      await this.sb.from('missing_persons').update({ status: 'Reunited' }).eq('case_id', case_id);
      return { ok: true };
    })());
  }

  // ─── Reports ──────────────────────────────────────────────────────────
  reportFound(body: ReportFoundPayload): Observable<{ ok: boolean; id?: number; errors?: string[] }> {
    return from((async () => {
      const row = {
        found_at: nowStamp(), found_location: body.found_location || '', reporting_center: body.reporting_center || '',
        person_name: body.person_name || '', gender: body.gender || '', age_band: body.age_band || '',
        state: body.state || '', district: body.district || '', language: body.language || '',
        physical_description: body.physical_description || '', contact_mobile: body.contact_mobile || '',
        remarks: body.remarks || '', photo: body.photo || '', status: 'Pending',
      };
      const { data, error } = await this.sb.from('found_persons').insert(row).select('id').single();
      if (error) return { ok: false, errors: [error.message] };
      return { ok: true, id: (data as { id: number }).id };
    })());
  }

  reportMissing(body: ReportMissingPayload): Observable<ReportMissingResponse> {
    return from((async () => {
      const row = {
        reported_at: nowStamp(), person_name: body.person_name || '', gender: body.gender || '',
        age_band: body.age_band || '', state: body.state || '', district: body.district || '',
        language: body.language || '', last_seen_location: body.last_seen_location || '',
        last_seen_time: body.last_seen_time || '', physical_description: body.physical_description || '',
        photo: body.photo || '', aadhaar_last4: body.aadhaar_last4 || '', reporter_name: body.reporter_name || '',
        reporter_mobile: body.reporter_mobile || '', reporter_relationship: body.reporter_relationship || '',
        special_needs: body.special_needs || '', status: 'Searching',
      };
      const { data, error } = await this.sb.from('report_missing').insert(row).select('id').single();
      if (error) return { ok: false, errors: [error.message] };
      const id = (data as { id: number }).id;
      return { ok: true, id, case_ref: 'FM-' + String(id).padStart(4, '0') };
    })());
  }

  // ─── Track ────────────────────────────────────────────────────────────
  track(params: { case_ref?: string; mobile?: string }): Observable<SearchResponse<TrackResult>> {
    return from((async () => {
      const results: TrackResult[] = [];
      const ref = (params.case_ref || '').trim();
      const mobile = (params.mobile || '').trim();

      if (ref) {
        if (ref.toUpperCase().startsWith('FM-')) {
          const id = parseInt(ref.replace(/FM-/i, ''), 10);
          if (!isNaN(id)) {
            const { data } = await this.sb.from('report_missing').select('*').eq('id', id).maybeSingle();
            if (data) results.push({ ...(data as TrackResult), source: 'family_report', case_ref: ref });
          }
        } else {
          const { data } = await this.sb.from('missing_persons').select('*').eq('case_id', ref).maybeSingle();
          if (data) results.push({ ...(data as TrackResult), source: 'missing_persons', case_ref: ref });
        }
      }

      if (mobile) {
        const like = `%${mobile}%`;
        const { data: rm } = await this.sb.from('report_missing').select('*').ilike('reporter_mobile', like);
        for (const r of (rm ?? []) as TrackResult[]) {
          results.push({ ...r, source: 'family_report', case_ref: 'FM-' + String(r.id).padStart(4, '0') });
        }
        const { data: mp } = await this.sb.from('missing_persons').select('*').ilike('reporter_mobile', like);
        for (const r of (mp ?? []) as TrackResult[]) {
          results.push({ ...r, source: 'missing_persons', case_ref: r.case_id });
        }
      }
      return { results, count: results.length };
    })());
  }

  requestCallback(found_person_id: number): Observable<{ ok: boolean }> {
    return from((async () => {
      await this.sb.from('callback_requests').insert({ found_person_id, requested_at: nowStamp(), status: 'pending' });
      return { ok: true };
    })());
  }

  // ─── Duplicates (admin, client-side clustering) ────────────────────────
  duplicates(): Observable<{ duplicate_groups: MissingPerson[][]; count: number }> {
    return from((async () => {
      const { data } = await this.sb.from('missing_persons').select('*')
        .eq('status', 'Pending').neq('missing_person_name', '').order('missing_person_name');
      const persons = (data ?? []) as MissingPerson[];
      const groups: MissingPerson[][] = [];
      const seen = new Set<string>();
      for (let i = 0; i < persons.length; i++) {
        const p = persons[i];
        if (seen.has(p.case_id!)) continue;
        const cluster = [p];
        for (let j = i + 1; j < persons.length; j++) {
          const q = persons[j];
          if (seen.has(q.case_id!)) continue;
          const sim = tokenSortRatio(p.missing_person_name || '', q.missing_person_name || '');
          if (sim > 75 && p.gender === q.gender && p.age_band === q.age_band) {
            cluster.push(q); seen.add(q.case_id!);
          }
        }
        if (cluster.length > 1) { groups.push(cluster); seen.add(p.case_id!); }
      }
      return { duplicate_groups: groups, count: groups.length };
    })());
  }

  // ─── Geo / hotspots ───────────────────────────────────────────────────
  geo(): Observable<GeoData> {
    return from((async () => {
      const [cctv, zones, police, choke] = await Promise.all([
        this.sb.from('cctv').select('*'),
        this.sb.from('zones').select('*'),
        this.sb.from('police_stations').select('*'),
        this.sb.from('chokepoints').select('*'),
      ]);
      return {
        cctv: cctv.data ?? [], zones: zones.data ?? [],
        police_stations: police.data ?? [], chokepoints: choke.data ?? [],
      } as GeoData;
    })());
  }

  hotspots(): Observable<{ hotspots: Hotspot[] }> {
    return from((async () => {
      const { data } = await this.sb.rpc('app_hotspots');
      return { hotspots: (data ?? []) as Hotspot[] };
    })());
  }
}
