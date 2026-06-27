"""Tests for authentication endpoints."""
import pytest


class TestLogin:
    def test_login_admin_success(self, client):
        """Valid admin credentials return ok=True and role=admin."""
        rv = client.post('/api/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True
        assert data['role'] == 'admin'
        assert data['username'] == 'admin'

    def test_login_volunteer_success(self, client):
        """Valid volunteer credentials return ok=True and role=volunteer."""
        rv = client.post('/api/login', json={
            'username': 'volunteer',
            'password': 'vol123'
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True
        assert data['role'] == 'volunteer'

    def test_login_family_success(self, client):
        """Valid family credentials return ok=True and role=family."""
        rv = client.post('/api/login', json={
            'username': 'family',
            'password': 'family123'
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True
        assert data['role'] == 'family'

    def test_login_wrong_password(self, client):
        """Wrong password returns 401."""
        rv = client.post('/api/login', json={
            'username': 'admin',
            'password': 'wrongpassword'
        })
        assert rv.status_code == 401
        data = rv.get_json()
        assert data['ok'] is False
        assert data['error'] == 'invalid_credentials'

    def test_login_unknown_user(self, client):
        """Non-existent user returns 401."""
        rv = client.post('/api/login', json={
            'username': 'nobody',
            'password': 'whatever'
        })
        assert rv.status_code == 401
        data = rv.get_json()
        assert data['ok'] is False

    def test_login_empty_username(self, client):
        """Missing username returns 400."""
        rv = client.post('/api/login', json={
            'username': '',
            'password': 'admin123'
        })
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['ok'] is False
        assert data['error'] == 'missing_credentials'

    def test_login_empty_password(self, client):
        """Missing password returns 400."""
        rv = client.post('/api/login', json={
            'username': 'admin',
            'password': ''
        })
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['ok'] is False

    def test_login_empty_body(self, client):
        """Empty JSON body returns 400."""
        rv = client.post('/api/login', json={})
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['ok'] is False

    def test_login_role_mismatch(self, client):
        """Requesting a role that doesn't match actual role returns 403."""
        rv = client.post('/api/login', json={
            'username': 'volunteer',
            'password': 'vol123',
            'role': 'admin'
        })
        assert rv.status_code == 403
        data = rv.get_json()
        assert data['ok'] is False
        assert data['error'] == 'role_mismatch'

    def test_login_role_matches(self, client):
        """Requesting the correct role succeeds."""
        rv = client.post('/api/login', json={
            'username': 'volunteer',
            'password': 'vol123',
            'role': 'volunteer'
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True


class TestMe:
    def test_me_authenticated(self, auth_client):
        """Authenticated user gets their info from /api/me."""
        rv = auth_client.get('/api/me')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True
        assert data['username'] == 'admin'
        assert data['role'] == 'admin'

    def test_me_unauthenticated(self, client):
        """Unauthenticated request to /api/me returns 401."""
        rv = client.get('/api/me')
        assert rv.status_code == 401
        data = rv.get_json()
        assert data['ok'] is False
        assert data['error'] == 'unauthenticated'

    def test_me_after_login(self, client):
        """After login /api/me returns correct user info."""
        client.post('/api/login', json={'username': 'volunteer', 'password': 'vol123'})
        rv = client.get('/api/me')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['username'] == 'volunteer'
        assert data['role'] == 'volunteer'


class TestLogout:
    def test_logout_clears_session(self, auth_client):
        """Logout clears session; subsequent /api/me returns 401."""
        # Confirm logged in
        rv = auth_client.get('/api/me')
        assert rv.status_code == 200

        # Logout
        rv = auth_client.post('/api/logout')
        assert rv.status_code == 200
        assert rv.get_json()['ok'] is True

        # Now unauthenticated
        rv = auth_client.get('/api/me')
        assert rv.status_code == 401

    def test_logout_when_not_logged_in(self, client):
        """Logout without a session still returns ok (idempotent)."""
        rv = client.post('/api/logout')
        assert rv.status_code == 200
        assert rv.get_json()['ok'] is True


class TestProtectedRoutes:
    """Protected routes should return 401 when not authenticated."""

    def test_report_found_requires_auth(self, client):
        rv = client.post('/api/report-found', json={'person_name': 'Test'})
        assert rv.status_code == 401

    def test_report_missing_requires_auth(self, client):
        rv = client.post('/api/report-missing', json={'person_name': 'Test'})
        assert rv.status_code == 401

    def test_fuzzy_match_requires_auth(self, client):
        rv = client.post('/api/fuzzy-match', json={'name': 'Test'})
        assert rv.status_code == 401

    def test_confirm_match_requires_auth(self, client):
        rv = client.post('/api/confirm-match', json={'found_id': 1, 'case_id': 'CASE-0001'})
        assert rv.status_code == 401

    def test_track_requires_auth(self, client):
        rv = client.get('/api/track?case_id=CASE-0001')
        assert rv.status_code == 401

    def test_audit_log_requires_admin(self, client):
        """Audit log is admin-only; unauthenticated returns 401."""
        rv = client.get('/api/audit-log')
        assert rv.status_code == 401

    def test_audit_log_volunteer_forbidden(self, volunteer_client):
        """Audit log returns 403 for volunteer role."""
        rv = volunteer_client.get('/api/audit-log')
        assert rv.status_code == 403
        data = rv.get_json()
        assert data['error'] == 'forbidden'

    def test_register_requires_admin(self, volunteer_client):
        """Register endpoint is admin-only; volunteer gets 403."""
        rv = volunteer_client.post('/api/register', json={
            'username': 'newuser',
            'password': 'pass123',
            'role': 'family'
        })
        assert rv.status_code == 403
