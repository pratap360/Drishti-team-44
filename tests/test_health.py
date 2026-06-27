"""Tests for health, stats, and infrastructure endpoints."""
import pytest
import time


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        """GET /health returns 200 with status ok."""
        rv = client.get('/health')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['status'] == 'ok'
        assert data['db'] == 'ok'

    def test_health_content_type_json(self, client):
        """Health endpoint returns JSON."""
        rv = client.get('/health')
        assert 'application/json' in rv.content_type


class TestStatsEndpoint:
    def test_stats_public_returns_basic_fields(self, client):
        """Public (unauthenticated) stats returns total, reunited, avg_resolution_hours."""
        rv = client.get('/api/stats')
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'total' in data
        assert 'reunited' in data
        assert 'avg_resolution_hours' in data

    def test_stats_public_no_admin_fields(self, client):
        """Public stats does not leak admin-only fields."""
        rv = client.get('/api/stats')
        data = rv.get_json()
        assert 'by_center' not in data
        assert 'by_age' not in data
        assert 'duplicates' not in data

    def test_stats_admin_returns_full_structure(self, auth_client):
        """Admin stats includes extended breakdown fields."""
        rv = auth_client.get('/api/stats')
        assert rv.status_code == 200
        data = rv.get_json()
        # Admin-only keys
        assert 'by_center' in data
        assert 'by_age' in data
        assert 'by_date' in data
        assert 'found_total' in data
        assert 'family_reports' in data

    def test_stats_reflects_seeded_data(self, client):
        """Stats total includes the seeded missing person."""
        rv = client.get('/api/stats')
        data = rv.get_json()
        assert data['total'] >= 1

    def test_stats_after_new_found_report(self, volunteer_client, auth_client):
        """After adding a found person, found_total increases."""
        rv1 = auth_client.get('/api/stats')
        initial_found = rv1.get_json().get('found_total', 0)

        volunteer_client.post('/api/report-found', json={
            'found_location': 'Stats Gate',
            'person_name': 'Stats Test Person',
        })

        # Invalidate stats cache by waiting (or just check directly)
        import app as app_module
        app_module._stats_cache['ts'] = 0  # force cache miss

        rv2 = auth_client.get('/api/stats')
        new_found = rv2.get_json().get('found_total', 0)
        assert new_found == initial_found + 1


class TestRateLimiter:
    def test_login_rate_limit_allows_under_limit(self, client):
        """Multiple requests under the rate limit all succeed (or fail with 401, not 429)."""
        for _ in range(5):
            rv = client.post('/api/login', json={
                'username': 'admin',
                'password': 'admin123',
            })
            assert rv.status_code != 429, "Should not be rate-limited for first few requests"

    def test_rate_limiter_returns_429_structure(self, app, client):
        """When rate limit is exceeded, response has ok=False and error=rate_limit_exceeded."""
        import app as app_module

        # Override rate limit store to simulate exhausted quota
        from unittest.mock import patch
        import time as time_module

        ip = '127.0.0.1'
        now = time_module.time()
        # Fill up the store past the 30-request limit for login
        app_module._rate_limit_store[ip] = [now] * 30

        rv = client.post('/api/login', json={
            'username': 'admin',
            'password': 'admin123',
        })
        assert rv.status_code == 429
        data = rv.get_json()
        assert data['ok'] is False
        assert data['error'] == 'rate_limit_exceeded'

        # Clean up to avoid polluting other tests
        app_module._rate_limit_store.pop(ip, None)


class TestSecurityHeaders:
    def test_security_headers_present_on_api(self, client):
        """API responses include standard security headers."""
        rv = client.get('/api/stats')
        assert rv.headers.get('X-Content-Type-Options') == 'nosniff'
        assert rv.headers.get('X-Frame-Options') == 'DENY'

    def test_cache_control_no_store_on_api(self, client):
        """API responses set Cache-Control: no-store."""
        rv = client.get('/api/stats')
        assert 'no-store' in rv.headers.get('Cache-Control', '')

    def test_security_headers_on_health(self, client):
        """Health endpoint also gets security headers."""
        rv = client.get('/health')
        assert rv.headers.get('X-Content-Type-Options') == 'nosniff'


class TestFiltersEndpoint:
    def test_filters_returns_structure(self, client):
        """GET /api/filters returns genders, ages, states, languages, centers."""
        rv = client.get('/api/filters')
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'genders' in data
        assert 'ages' in data
        assert 'states' in data
        assert 'languages' in data
        assert 'centers' in data

    def test_filters_include_seeded_data(self, client):
        """Filters reflect the seeded 'Ramesh Kumar' record values."""
        rv = client.get('/api/filters')
        data = rv.get_json()
        assert 'Male' in data['genders']
        assert 'UP' in data['states']
        assert 'Hindi' in data['languages']


class TestRegisterEndpoint:
    def test_admin_can_register_new_user(self, auth_client):
        """Admin can register a new volunteer user."""
        rv = auth_client.post('/api/register', json={
            'username': 'newvolunteer',
            'password': 'pass123',
            'role': 'volunteer',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True

    def test_register_duplicate_username_409(self, auth_client):
        """Registering an existing username returns 409."""
        rv = auth_client.post('/api/register', json={
            'username': 'volunteer',
            'password': 'newpass123',
            'role': 'volunteer',
        })
        assert rv.status_code == 409
        data = rv.get_json()
        assert data['error'] == 'username_exists'

    def test_register_short_password_400(self, auth_client):
        """Password shorter than 6 chars returns 400."""
        rv = auth_client.post('/api/register', json={
            'username': 'shortpass',
            'password': '12345',  # 5 chars
            'role': 'volunteer',
        })
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['error'] == 'password_too_short'

    def test_register_invalid_role_400(self, auth_client):
        """Invalid role returns 400."""
        rv = auth_client.post('/api/register', json={
            'username': 'badrole',
            'password': 'pass123',
            'role': 'superadmin',
        })
        assert rv.status_code == 400

    def test_registered_user_can_login(self, auth_client, client):
        """After registering, the new user can log in successfully."""
        auth_client.post('/api/register', json={
            'username': 'freshuser',
            'password': 'freshpass',
            'role': 'family',
        })
        rv = client.post('/api/login', json={
            'username': 'freshuser',
            'password': 'freshpass',
        })
        assert rv.status_code == 200
        assert rv.get_json()['role'] == 'family'
