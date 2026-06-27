-- ============================================================================
-- Drishti — (re)set passwords for the existing demo auth accounts so the app
-- can be logged into. These accounts already exist in this project:
--   admin@drishti.in      -> admin123     (role: admin)
--   volunteer@drishti.in  -> vol123       (role: volunteer)
--   registree@drishti.in  -> family123    (role: pre_registree / Family portal)
-- Re-run any time to reset. Adjust passwords as you like.
-- ============================================================================
update auth.users set encrypted_password = crypt('admin123',  gen_salt('bf')),
       email_confirmed_at = coalesce(email_confirmed_at, now()) where email = 'admin@drishti.in';
update auth.users set encrypted_password = crypt('vol123',    gen_salt('bf')),
       email_confirmed_at = coalesce(email_confirmed_at, now()) where email = 'volunteer@drishti.in';
update auth.users set encrypted_password = crypt('family123', gen_salt('bf')),
       email_confirmed_at = coalesce(email_confirmed_at, now()) where email = 'registree@drishti.in';
