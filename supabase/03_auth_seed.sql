-- ============================================================================
-- Drishti — seed the three demo auth accounts.
-- Emails map from the bare usernames used in the login UI:
--   admin     / admin123    -> admin@drishti.local      (role: admin)
--   volunteer / vol123      -> volunteer@drishti.local  (role: volunteer)
--   family    / family123   -> family@drishti.local     (role: family)
--
-- Run AFTER 01_schema.sql. Inserts into auth.users + auth.identities; the
-- on_auth_user_created trigger creates the matching public.profiles row with
-- the role taken from raw_user_meta_data.
-- ============================================================================

do $$
declare
  u record;
  uid uuid;
  seed jsonb := '[
    {"email":"admin@drishti.local",     "pw":"admin123",  "role":"admin"},
    {"email":"volunteer@drishti.local", "pw":"vol123",     "role":"volunteer"},
    {"email":"family@drishti.local",    "pw":"family123",  "role":"family"}
  ]'::jsonb;
begin
  for u in select * from jsonb_array_elements(seed) as x(v) loop
    if exists (select 1 from auth.users where email = (u.v->>'email')) then
      continue;
    end if;
    uid := gen_random_uuid();

    insert into auth.users (
      instance_id, id, aud, role, email, encrypted_password,
      email_confirmed_at, created_at, updated_at,
      raw_app_meta_data, raw_user_meta_data, is_super_admin
    ) values (
      '00000000-0000-0000-0000-000000000000', uid, 'authenticated', 'authenticated',
      u.v->>'email', crypt(u.v->>'pw', gen_salt('bf')),
      now(), now(), now(),
      '{"provider":"email","providers":["email"]}'::jsonb,
      jsonb_build_object('role', u.v->>'role'),
      false
    );

    insert into auth.identities (
      provider_id, user_id, identity_data, provider, last_sign_in_at, created_at, updated_at
    ) values (
      uid, uid,
      jsonb_build_object('sub', uid::text, 'email', u.v->>'email', 'email_verified', true),
      'email', now(), now(), now()
    );

    -- ensure profile role (trigger already inserts; keep idempotent)
    insert into public.profiles (id, username, role)
    values (uid, split_part(u.v->>'email','@',1), u.v->>'role')
    on conflict (id) do update set role = excluded.role, username = excluded.username;
  end loop;
end $$;
