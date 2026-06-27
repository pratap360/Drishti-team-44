// Shared API model types — mirror the Flask /api response shapes (see app.py).

// Roles match the profiles.role enum in Supabase. The Family portal maps to
// the `pre_registree` role.
export type Role = 'admin' | 'volunteer' | 'pre_registree';

export interface MeResponse {
  ok: boolean;
  username?: string;
  role?: Role;
  error?: string;
}

export interface LoginResponse {
  ok: boolean;
  role?: Role;
  username?: string;
  error?: string;
}

export interface PublicStats {
  total: number;
  reunited: number;
  avg_resolution_hours: number;
}

export interface AdminStats extends PublicStats {
  pending: number;
  unresolved: number;
  hospital: number;
  duplicates: number;
  found_total: number;
  found_matched: number;
  family_reports: number;
  family_matched: number;
  by_center: { center: string; count: number; reunited: number }[];
  by_age: { age_band: string; count: number }[];
  by_date: { date: string; count: number }[];
}

export interface Filters {
  genders: string[];
  ages: string[];
  states: string[];
  languages: string[];
  centers: string[];
}

/** A missing_persons row (search / fuzzy-match results). */
export interface MissingPerson {
  id?: number;
  case_id?: string;
  missing_person_name?: string;
  gender?: string;
  age_band?: string;
  state?: string;
  language?: string;
  last_seen_location?: string;
  reporting_center?: string;
  physical_description?: string;
  reporter_mobile?: string;
  status?: string;
  reported_at?: string;
  photo?: string;
  match_score?: number;
  match_reasons?: string[];
  [k: string]: unknown;
}

/** A found_persons row (found-persons / match-found results). */
export interface FoundPerson {
  id?: number;
  found_at?: string;
  found_location?: string;
  reporting_center?: string;
  person_name?: string;
  gender?: string;
  age_band?: string;
  state?: string;
  language?: string;
  physical_description?: string;
  contact_mobile?: string;
  photo?: string;
  status?: string;
  match_score?: number;
  match_reasons?: string[];
  [k: string]: unknown;
}

export interface SearchResponse<T> {
  results: T[];
  count: number;
}

export interface MatchResponse<T> {
  matches: T[];
}

/** Payload accepted by /api/report-found. */
export interface ReportFoundPayload {
  person_name?: string;
  gender?: string;
  age_band?: string;
  state?: string;
  district?: string;
  language?: string;
  found_location?: string;
  reporting_center?: string;
  contact_mobile?: string;
  physical_description?: string;
  remarks?: string;
  photo?: string;
}

/** Payload accepted by /api/report-missing. */
export interface ReportMissingPayload {
  person_name?: string;
  gender?: string;
  age_band?: string;
  state?: string;
  district?: string;
  language?: string;
  last_seen_location?: string;
  last_seen_time?: string;
  physical_description?: string;
  photo?: string;
  aadhaar_last4?: string;
  reporter_name?: string;
  reporter_mobile?: string;
  reporter_relationship?: string;
  special_needs?: string;
}

export interface ReportMissingResponse {
  ok: boolean;
  id?: number;
  case_ref?: string;
  errors?: string[];
}

export interface TrackResult extends MissingPerson {
  source?: string;
  case_ref?: string;
  reported_at?: string;
  reporter_relationship?: string;
  /** report_missing rows use person_name; missing_persons use missing_person_name. */
  person_name?: string;
}

// Geo data
export interface Cctv { camera_id?: string; latitude: number; longitude: number; [k: string]: unknown; }
export interface PoliceStation { station_name?: string; latitude: number; longitude: number; [k: string]: unknown; }
export interface Chokepoint { location_name?: string; category?: string; latitude: number; longitude: number; [k: string]: unknown; }
export interface Zone { zone_name?: string; centroid_lat: number; centroid_lng: number; [k: string]: unknown; }

export interface GeoData {
  cctv: Cctv[];
  zones: Zone[];
  police_stations: PoliceStation[];
  chokepoints: Chokepoint[];
}

export interface Hotspot {
  last_seen_location: string;
  cnt: number;
  active: number;
  lat: number | null;
  lng: number | null;
  geo_confidence: number;
}
