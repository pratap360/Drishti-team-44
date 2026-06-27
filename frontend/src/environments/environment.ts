// Supabase config. The anon key is a public key — safe to ship in a client
// bundle as long as Row Level Security (RLS) is enabled on every table.
export const environment = {
  production: false,
  supabaseUrl: 'https://dtqbturxigckqiqfzdnb.supabase.co',
  supabaseAnonKey:
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR0cWJ0dXJ4aWdja3FpcWZ6ZG5iIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODI1MzczOTYsImV4cCI6MjA5ODExMzM5Nn0.8V8-vkE5PCZp5On8PWXNY0U_iVXEesSiTEHepCnXbjY',
  // Demo logins use bare usernames; we map them to emails with this domain.
  authEmailDomain: 'drishti.in',
};
