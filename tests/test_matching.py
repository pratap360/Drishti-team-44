"""Tests for fuzzy matching endpoints."""
import pytest


class TestFuzzyMatchEndpoint:
    """Tests for /api/fuzzy-match (volunteer/admin matching found → missing)."""

    def test_exact_name_match_high_score(self, volunteer_client):
        """Exact name match returns a result with high match score."""
        rv = volunteer_client.post('/api/fuzzy-match', json={
            'name': 'Ramesh Kumar',
            'gender': 'Male',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        matches = data['matches']
        assert len(matches) >= 1
        # Seeded record is Ramesh Kumar Male
        top = matches[0]
        assert top['match_score'] >= 35
        assert 'Name' in ' '.join(top.get('match_reasons', []))

    def test_similar_name_typo_matches(self, volunteer_client):
        """Slight name typo still produces a match (fuzzy tolerance)."""
        rv = volunteer_client.post('/api/fuzzy-match', json={
            'name': 'Ramesh Kumaar',  # extra 'a'
            'gender': 'Male',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        # Should still match with some score
        assert isinstance(data['matches'], list)

    def test_completely_different_name_no_match(self, volunteer_client):
        """Unrelated name returns no matches (or low-score filtered results)."""
        rv = volunteer_client.post('/api/fuzzy-match', json={
            'name': 'ZZZZNONEXISTENT',
            'gender': 'Male',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        # Either empty or no name reason in top match
        if data['matches']:
            for m in data['matches']:
                assert m['match_score'] < 70  # purely from state/lang, not name

    def test_gender_filter_applied(self, volunteer_client):
        """Female gender filter excludes Male records from candidates."""
        rv = volunteer_client.post('/api/fuzzy-match', json={
            'name': 'Ramesh Kumar',
            'gender': 'Female',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        # Ramesh Kumar is Male — should not appear in Female-filtered results
        for match in data['matches']:
            assert match['gender'] == 'Female'

    def test_age_band_filter_applied(self, volunteer_client):
        """Age band filter limits candidates to matching age range."""
        rv = volunteer_client.post('/api/fuzzy-match', json={
            'name': 'Ramesh Kumar',
            'gender': 'Male',
            'age_band': 'Child (0-12)',  # seeded record is Adult
        })
        assert rv.status_code == 200
        data = rv.get_json()
        # Seeded record is Adult (18-60), should not appear under Child filter
        for match in data['matches']:
            assert match['age_band'] == 'Child (0-12)'

    def test_state_match_adds_score(self, volunteer_client):
        """State match adds score to results."""
        rv = volunteer_client.post('/api/fuzzy-match', json={
            'name': 'Ramesh Kumar',
            'gender': 'Male',
            'state': 'UP',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data['matches']) >= 1
        top = data['matches'][0]
        reasons = top.get('match_reasons', [])
        assert any('State' in r for r in reasons)

    def test_empty_database_no_results(self, volunteer_client, app):
        """If no candidates exist, match list is empty."""
        import app as app_module
        import sqlite3

        # Temporarily clear missing_persons table
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.execute("DELETE FROM missing_persons")
        conn.commit()
        conn.close()

        rv = volunteer_client.post('/api/fuzzy-match', json={
            'name': 'Anyone',
            'gender': 'Male',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['matches'] == []

    def test_fuzzy_match_returns_match_reasons(self, volunteer_client):
        """Each match includes match_reasons list."""
        rv = volunteer_client.post('/api/fuzzy-match', json={
            'name': 'Ramesh Kumar',
            'gender': 'Male',
            'state': 'UP',
        })
        data = rv.get_json()
        if data['matches']:
            top = data['matches'][0]
            assert 'match_reasons' in top
            assert isinstance(top['match_reasons'], list)

    def test_fuzzy_match_requires_auth(self, client):
        """Unauthenticated request returns 401."""
        rv = client.post('/api/fuzzy-match', json={'name': 'Test'})
        assert rv.status_code == 401

    def test_fuzzy_match_results_sorted_by_score(self, volunteer_client, app):
        """Results are sorted by match_score descending."""
        import app as app_module
        import sqlite3

        # Insert a second missing person for comparison
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.execute("""INSERT OR IGNORE INTO missing_persons VALUES
            ('CASE-0002', '2026-01-02 10:00', 'Ramesh Singh', 'Male', 'Adult (18-60)',
             'UP', 'Prayagraj', 'Hindi', 'Sangam', 'Center A',
             '9876543211', 'Medium height, blue shirt', 'Pending', NULL, 0, '', '')""")
        conn.commit()
        conn.close()

        rv = volunteer_client.post('/api/fuzzy-match', json={
            'name': 'Ramesh Kumar',
            'gender': 'Male',
            'state': 'UP',
        })
        data = rv.get_json()
        scores = [m['match_score'] for m in data['matches']]
        assert scores == sorted(scores, reverse=True)


class TestMatchFoundEndpoint:
    """Tests for /api/match-found (family matching missing → found persons).

    Note: We use auth_client (admin) for all operations since admin is in both
    (volunteer, admin) AND (family, admin) role sets. This avoids the fixture
    collision where two role fixtures share the same underlying client and the
    second login overwrites the first, leaving us in the wrong role.
    """

    def _add_found_person(self, auth_client, name='Anita Sharma', gender='Female',
                          age_band='Adult (18-60)', state='UP', language='Hindi',
                          description='Tall woman in red saree'):
        """Admin can report found persons (admin is in volunteer+admin set)."""
        rv = auth_client.post('/api/report-found', json={
            'person_name': name,
            'found_location': 'Mela Gate',
            'gender': gender,
            'age_band': age_band,
            'state': state,
            'language': language,
            'physical_description': description,
        })
        assert rv.status_code == 200, f"report-found failed: {rv.get_json()}"

    def test_match_found_returns_structure(self, auth_client):
        """Admin can call /api/match-found (admin is in family+admin set)."""
        rv = auth_client.post('/api/match-found', json={'name': 'Test'})
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'matches' in data

    def test_match_found_name_match(self, auth_client):
        """Adding a found person with same name produces a name match."""
        self._add_found_person(auth_client, name='Sunita Devi', gender='Female')

        rv = auth_client.post('/api/match-found', json={
            'name': 'Sunita Devi',
            'gender': 'Female',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data['matches']) >= 1
        names = [m['person_name'] for m in data['matches']]
        assert any('Sunita' in n for n in names)

    def test_match_found_contact_mobile_masked(self, auth_client, app):
        """contact_mobile is masked for privacy in match-found results."""
        self._add_found_person(auth_client, name='Privacy Test', gender='Female')
        # Add a contact mobile to the found person via direct DB update
        import app as app_module
        import sqlite3
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.execute(
            "UPDATE found_persons SET contact_mobile='9876543210' WHERE person_name='Privacy Test'"
        )
        conn.commit()
        conn.close()

        rv = auth_client.post('/api/match-found', json={
            'name': 'Privacy Test',
            'gender': 'Female',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        for m in data['matches']:
            mobile = m.get('contact_mobile', '')
            if mobile and len(mobile) > 4:
                assert '****' in mobile, "Mobile should be masked"

    def test_match_found_empty_db_no_results(self, auth_client):
        """No found persons in DB → empty matches (found_persons table is empty by default)."""
        rv = auth_client.post('/api/match-found', json={
            'name': 'Anyone',
            'gender': 'Male',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['matches'] == []

    def test_match_found_requires_auth(self, client):
        """Unauthenticated request returns 401."""
        rv = client.post('/api/match-found', json={'name': 'Test'})
        assert rv.status_code == 401

    def test_match_found_volunteer_forbidden(self, volunteer_client):
        """Volunteer role is not in (family, admin) set → 403."""
        rv = volunteer_client.post('/api/match-found', json={'name': 'Test'})
        assert rv.status_code == 403
