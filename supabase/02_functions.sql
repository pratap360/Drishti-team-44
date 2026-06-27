-- ============================================================================
-- Drishti — RPC functions (aggregations). SECURITY DEFINER so they can
-- aggregate across all rows regardless of the caller. Returns JSON.
-- ============================================================================

-- Public stats (landing / family / volunteer)
create or replace function public.app_public_stats()
returns json language sql security definer set search_path = public as $$
  select json_build_object(
    'total', (select count(*) from missing_persons),
    'reunited', (select count(*) from missing_persons where status = 'Reunited'),
    'avg_resolution_hours', coalesce(round((select avg(resolution_hours) from missing_persons where resolution_hours is not null)::numeric, 1), 0)
  );
$$;

-- Admin stats (control centre dashboard)
create or replace function public.app_admin_stats()
returns json language sql security definer set search_path = public as $$
  select json_build_object(
    'total',                 (select count(*) from missing_persons),
    'pending',               (select count(*) from missing_persons where status = 'Pending'),
    'reunited',              (select count(*) from missing_persons where status = 'Reunited'),
    'unresolved',            (select count(*) from missing_persons where status = 'Unresolved'),
    'hospital',              (select count(*) from missing_persons where status = 'Transferred to hospital'),
    'duplicates',            (select count(*) from missing_persons where is_duplicate_report = true),
    'avg_resolution_hours',  coalesce(round((select avg(resolution_hours) from missing_persons where resolution_hours is not null)::numeric, 1), 0),
    'found_total',           (select count(*) from found_persons),
    'found_matched',         (select count(*) from found_persons where matched_case_id is not null),
    'family_reports',        (select count(*) from report_missing),
    'family_matched',        (select count(*) from report_missing where matched_found_id is not null),
    'by_age',     coalesce((select json_agg(t) from (
        select age_band, count(*)::int as count from missing_persons group by age_band order by count(*) desc) t), '[]'::json),
    'by_center',  coalesce((select json_agg(t) from (
        select reporting_center as center, count(*)::int as count,
               sum(case when status='Reunited' then 1 else 0 end)::int as reunited
        from missing_persons group by reporting_center order by count(*) desc) t), '[]'::json),
    'by_date',    coalesce((select json_agg(t) from (
        select to_char(reported_at,'YYYY-MM-DD') as date, count(*)::int as count
        from missing_persons group by to_char(reported_at,'YYYY-MM-DD') order by 1) t), '[]'::json)
  );
$$;

-- Distinct filter values
create or replace function public.app_filters()
returns json language sql security definer set search_path = public as $$
  select json_build_object(
    'genders',   coalesce((select json_agg(g order by g) from (select distinct gender g from missing_persons where gender is not null) s), '[]'::json),
    'ages',      coalesce((select json_agg(a order by a) from (select distinct age_band a from missing_persons where age_band is not null) s), '[]'::json),
    'states',    coalesce((select json_agg(st order by st) from (select distinct state st from missing_persons where state is not null and state <> '') s), '[]'::json),
    'languages', coalesce((select json_agg(l order by l) from (select distinct language l from missing_persons where language is not null and language <> '') s), '[]'::json),
    'centers',   coalesce((select json_agg(c order by c) from (select distinct reporting_center c from missing_persons where reporting_center is not null) s), '[]'::json)
  );
$$;

-- Hotspots — top last-seen locations, geo-enriched from chokepoints/zones
create or replace function public.app_hotspots()
returns json language sql security definer set search_path = public as $$
  with agg as (
    select last_seen_location,
           count(*)::int as cnt,
           sum(case when status in ('Pending','Unresolved') then 1 else 0 end)::int as active
    from missing_persons
    group by last_seen_location
    order by count(*) desc
    limit 20
  ),
  geo as (
    select location_name as name, latitude as lat, longitude as lng from chokepoints
    union all
    select zone_name as name, centroid_lat as lat, centroid_lng as lng from zones
  ),
  enriched as (
    select a.*,
      (select g.lat from geo g where a.last_seen_location is not null
         and similarity(lower(a.last_seen_location), lower(g.name)) >= 0.5
         order by similarity(lower(a.last_seen_location), lower(g.name)) desc limit 1) as lat,
      (select g.lng from geo g where a.last_seen_location is not null
         and similarity(lower(a.last_seen_location), lower(g.name)) >= 0.5
         order by similarity(lower(a.last_seen_location), lower(g.name)) desc limit 1) as lng
    from agg a
  )
  select coalesce(json_agg(json_build_object(
    'last_seen_location', last_seen_location, 'cnt', cnt, 'active', active,
    'lat', lat, 'lng', lng, 'geo_confidence', case when lat is not null then 60 else 0 end
  )), '[]'::json) from enriched;
$$;

grant execute on function public.app_public_stats() to anon, authenticated;
grant execute on function public.app_admin_stats()  to anon, authenticated;
grant execute on function public.app_filters()       to anon, authenticated;
grant execute on function public.app_hotspots()       to anon, authenticated;
