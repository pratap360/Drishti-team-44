"""Tests for report and search endpoints."""
import pytest


class TestReportFound:
    def test_report_found_valid_data(self, volunteer_client):
        """Valid found-person report returns ok=True with an id."""
        rv = volunteer_client.post('/api/report-found', json={
            'person_name': 'Anita Devi',
            'found_location': 'Triveni Sangam',
            'reporting_center': 'Center B',
            'gender': 'Female',
            'age_band': 'Adult (18-60)',
            'state': 'UP',
            'language': 'Hindi',
            'contact_mobile': '9876543210',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True
        assert isinstance(data['id'], int)
        assert data['id'] > 0

    def test_report_found_minimal_data(self, volunteer_client):
        """Only location is needed; all other fields optional."""
        rv = volunteer_client.post('/api/report-found', json={
            'found_location': 'Gate 7',
        })
        assert rv.status_code == 200
        assert rv.get_json()['ok'] is True

    def test_report_found_invalid_gender(self, volunteer_client):
        """Invalid gender value returns 400 validation error."""
        rv = volunteer_client.post('/api/report-found', json={
            'person_name': 'Test Person',
            'gender': 'Alien',
            'found_location': 'Gate 3',
        })
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['ok'] is False
        assert data['error'] == 'validation_error'

    def test_report_found_invalid_mobile(self, volunteer_client):
        """Short mobile number triggers validation error."""
        rv = volunteer_client.post('/api/report-found', json={
            'contact_mobile': '123',
        })
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['ok'] is False

    def test_report_found_requires_volunteer_or_admin(self, client):
        """Unauthenticated → 401; family role → 403 (authenticated but wrong role)."""
        # Unauthenticated
        rv = client.post('/api/report-found', json={'found_location': 'Gate 1'})
        assert rv.status_code == 401

        # Log in as family and verify 403 (wrong role, not unauthenticated)
        client.post('/api/login', json={'username': 'family', 'password': 'family123'})
        rv = client.post('/api/report-found', json={'found_location': 'Gate 1'})
        assert rv.status_code == 403

    def test_report_found_admin_allowed(self, auth_client):
        """Admin can also submit found person reports."""
        rv = auth_client.post('/api/report-found', json={
            'found_location': 'Admin gate',
        })
        assert rv.status_code == 200
        assert rv.get_json()['ok'] is True


class TestReportMissing:
    def test_report_missing_valid_data(self, family_client):
        """Valid missing report returns ok=True with id and case_ref."""
        rv = family_client.post('/api/report-missing', json={
            'person_name': 'Vikram Patel',
            'gender': 'Male',
            'age_band': 'Adult (18-60)',
            'state': 'Gujarat',
            'reporter_name': 'Sunita Patel',
            'reporter_mobile': '8765432109',
            'reporter_relationship': 'Wife',
            'last_seen_location': 'Main Ghats',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True
        assert 'id' in data
        assert 'case_ref' in data
        assert data['case_ref'].startswith('FM-')

    def test_report_missing_case_ref_format(self, family_client):
        """case_ref should be FM-XXXX (zero-padded to 4 digits)."""
        rv = family_client.post('/api/report-missing', json={
            'person_name': 'Test Person',
        })
        data = rv.get_json()
        case_ref = data['case_ref']
        num_part = case_ref.replace('FM-', '')
        assert num_part.isdigit()
        assert len(num_part) >= 4

    def test_report_missing_invalid_gender(self, family_client):
        """Invalid gender returns 400."""
        rv = family_client.post('/api/report-missing', json={
            'person_name': 'Test Person',
            'gender': 'X',
        })
        assert rv.status_code == 400

    def test_report_missing_family_or_admin_only(self, client):
        """Volunteer → 403 (wrong role); unauthenticated → 401."""
        # Unauthenticated
        rv = client.post('/api/report-missing', json={'person_name': 'Test'})
        assert rv.status_code == 401

        # Volunteer role is authenticated but not authorised → 403
        client.post('/api/login', json={'username': 'volunteer', 'password': 'vol123'})
        rv = client.post('/api/report-missing', json={'person_name': 'Test'})
        assert rv.status_code == 403

    def test_report_missing_admin_allowed(self, auth_client):
        """Admin can file a missing report."""
        rv = auth_client.post('/api/report-missing', json={
            'person_name': 'Admin Test Person',
        })
        assert rv.status_code == 200
        assert rv.get_json()['ok'] is True


class TestSearch:
    def test_search_returns_structure(self, client):
        """GET /api/search returns results and count keys."""
        rv = client.get('/api/search')
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'results' in data
        assert 'count' in data
        assert isinstance(data['results'], list)

    def test_search_with_name_query(self, client):
        """Search for seeded 'Ramesh Kumar' returns a match."""
        rv = client.get('/api/search?q=Ramesh')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['count'] >= 1
        names = [r['missing_person_name'] for r in data['results']]
        assert any('Ramesh' in n for n in names)

    def test_search_by_case_id(self, client):
        """Searching by exact case_id returns the matching record."""
        rv = client.get('/api/search?q=CASE-0001')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['count'] >= 1
        case_ids = [r['case_id'] for r in data['results']]
        assert 'CASE-0001' in case_ids

    def test_search_gender_filter(self, client):
        """Gender filter applied to search returns only matching records."""
        rv = client.get('/api/search?gender=Male')
        assert rv.status_code == 200
        data = rv.get_json()
        for record in data['results']:
            assert record['gender'] == 'Male'

    def test_search_no_match_returns_empty(self, client):
        """Highly specific non-matching query returns empty results."""
        rv = client.get('/api/search?q=ZZZZNONEXISTENT9999')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['count'] == 0

    def test_search_limit_respected(self, client):
        """Limit parameter caps results."""
        rv = client.get('/api/search?limit=1')
        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data['results']) <= 1


class TestFoundPersonsList:
    def test_list_found_persons_structure(self, client):
        """GET /api/found-persons returns results list."""
        rv = client.get('/api/found-persons')
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'results' in data
        assert 'count' in data

    def test_list_found_persons_empty_initially(self, client):
        """Fresh DB has no found persons."""
        rv = client.get('/api/found-persons')
        data = rv.get_json()
        assert data['count'] == 0

    def test_list_found_persons_after_report(self, volunteer_client, client):
        """After reporting a found person, they appear in the list."""
        volunteer_client.post('/api/report-found', json={
            'person_name': 'Found Person X',
            'found_location': 'Gate 5',
            'gender': 'Female',
        })
        rv = client.get('/api/found-persons')
        data = rv.get_json()
        assert data['count'] >= 1

    def test_list_found_persons_photo_stripped_for_large_photos(self, volunteer_client, client):
        """Large photos are stripped from list view; photo_available=True is set instead."""
        big_photo = 'data:image/jpeg;base64,' + 'A' * 300
        volunteer_client.post('/api/report-found', json={
            'found_location': 'Gate 6',
            'photo': big_photo,
        })
        rv = client.get('/api/found-persons')
        data = rv.get_json()
        # Find the record with a photo
        for r in data['results']:
            if r.get('photo_available'):
                assert r['photo'] is None
                break


class TestTrackCase:
    def test_track_with_no_params_returns_400(self, family_client):
        """Tracking with no params returns 400."""
        rv = family_client.get('/api/track')
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['ok'] is False
        assert data['error'] == 'missing_params'

    def test_track_with_case_id_found(self, family_client):
        """Tracking CASE-0001 (seeded) returns the record."""
        rv = family_client.get('/api/track?case_id=CASE-0001')
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'results' in data
        assert data['count'] >= 1
        sources = [r['source'] for r in data['results']]
        assert 'missing_persons' in sources

    def test_track_with_nonexistent_case_id_returns_empty(self, family_client):
        """Tracking a non-existent case returns empty results (not 404)."""
        rv = family_client.get('/api/track?case_id=CASE-ZZZZ')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['count'] == 0

    def test_track_family_report_with_fm_ref(self, family_client, auth_client):
        """Track a family-submitted report by its FM- reference."""
        # First file a missing report
        rv = family_client.post('/api/report-missing', json={
            'person_name': 'Track Test Person',
        })
        case_ref = rv.get_json()['case_ref']

        # Now track it
        rv2 = family_client.get(f'/api/track?case_ref={case_ref}')
        assert rv2.status_code == 200
        data = rv2.get_json()
        assert data['count'] >= 1
        assert data['results'][0]['source'] == 'family_report'

    def test_track_requires_auth(self, client):
        """Unauthenticated track request returns 401."""
        rv = client.get('/api/track?case_id=CASE-0001')
        assert rv.status_code == 401

    def test_track_by_mobile(self, family_client):
        """Track by reporter mobile finds matching reports."""
        # File a report with a known mobile
        family_client.post('/api/report-missing', json={
            'person_name': 'Mobile Track Test',
            'reporter_mobile': '9000000001',
        })
        rv = family_client.get('/api/track?mobile=9000000001')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['count'] >= 1
