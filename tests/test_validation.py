"""Tests for the validate_input function."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def import_validate():
    """Import validate_input once per test."""
    pass


def get_validate():
    """Return the validate_input function from the app module."""
    import app as app_module
    return app_module.validate_input


class TestTextFieldHandling:
    def test_normal_input_passes_through(self):
        validate_input = get_validate()
        data = {'person_name': 'Ramesh Kumar', 'state': 'UP'}
        cleaned, errors = validate_input(data)
        assert cleaned['person_name'] == 'Ramesh Kumar'
        assert cleaned['state'] == 'UP'
        assert errors == []

    def test_whitespace_stripped(self):
        validate_input = get_validate()
        data = {'person_name': '  Ramesh  '}
        cleaned, errors = validate_input(data)
        assert cleaned['person_name'] == 'Ramesh'

    def test_long_string_truncated_at_500(self):
        validate_input = get_validate()
        long_name = 'A' * 600
        data = {'person_name': long_name}
        cleaned, errors = validate_input(data)
        assert len(cleaned['person_name']) == 500

    def test_empty_optional_field_stays_empty(self):
        validate_input = get_validate()
        data = {}
        cleaned, errors = validate_input(data)
        assert cleaned['person_name'] == ''
        assert errors == []

    def test_html_tags_in_name_preserved_as_string(self):
        """validate_input does not strip HTML — it truncates and strips whitespace only.
        The app stores raw text (no HTML rendering), so tags are harmless in the DB."""
        validate_input = get_validate()
        data = {'person_name': '<script>alert(1)</script>'}
        cleaned, errors = validate_input(data)
        # The value is stored as-is (not rendered); no errors expected
        assert errors == []
        # Value should still be present (not blanked by validation)
        assert cleaned['person_name'] != ''

    def test_none_value_treated_as_falsy(self):
        """None value passes the `if val:` check as falsy; stored as-is (None)."""
        validate_input = get_validate()
        data = {'person_name': None}
        cleaned, errors = validate_input(data)
        # None is falsy, so the `if val:` branch is skipped; value stored as None
        assert not cleaned['person_name']  # None or empty string, both are falsy
        assert errors == []


class TestGenderValidation:
    def test_valid_gender_male(self):
        validate_input = get_validate()
        _, errors = validate_input({'gender': 'Male'})
        assert errors == []

    def test_valid_gender_female(self):
        validate_input = get_validate()
        _, errors = validate_input({'gender': 'Female'})
        assert errors == []

    def test_valid_gender_unknown(self):
        validate_input = get_validate()
        _, errors = validate_input({'gender': 'Unknown'})
        assert errors == []

    def test_empty_gender_valid(self):
        validate_input = get_validate()
        _, errors = validate_input({'gender': ''})
        assert errors == []

    def test_invalid_gender_raises_error(self):
        validate_input = get_validate()
        _, errors = validate_input({'gender': 'Other'})
        assert len(errors) == 1
        assert 'gender' in errors[0]

    def test_invalid_gender_lowercase(self):
        validate_input = get_validate()
        _, errors = validate_input({'gender': 'male'})
        assert len(errors) == 1


class TestMobileValidation:
    def test_valid_10_digit_reporter_mobile(self):
        validate_input = get_validate()
        cleaned, errors = validate_input({'reporter_mobile': '9876543210'})
        assert errors == []
        assert cleaned['reporter_mobile'] == '9876543210'

    def test_valid_10_digit_contact_mobile(self):
        validate_input = get_validate()
        cleaned, errors = validate_input({'contact_mobile': '8765432109'})
        assert errors == []
        assert cleaned['contact_mobile'] == '8765432109'

    def test_reporter_and_contact_mobile_independent(self):
        """Both fields validated independently — one invalid doesn't affect the other."""
        validate_input = get_validate()
        cleaned, errors = validate_input({
            'reporter_mobile': '9876543210',
            'contact_mobile': '123'  # too short → error
        })
        assert cleaned['reporter_mobile'] == '9876543210'
        assert cleaned['contact_mobile'] == ''
        assert any('contact_mobile' in e for e in errors)
        assert not any('reporter_mobile' in e for e in errors)

    def test_short_mobile_error(self):
        validate_input = get_validate()
        _, errors = validate_input({'reporter_mobile': '12345'})
        assert len(errors) == 1
        assert 'reporter_mobile' in errors[0]

    def test_mobile_with_spaces_stripped_and_counted(self):
        """Spaces are stripped from mobile; only digits are counted."""
        validate_input = get_validate()
        # "98765 43210" has 10 digits after removing space
        cleaned, errors = validate_input({'reporter_mobile': '98765 43210'})
        assert errors == []
        assert cleaned['reporter_mobile'] == '9876543210'

    def test_empty_mobile_allowed(self):
        validate_input = get_validate()
        cleaned, errors = validate_input({'reporter_mobile': ''})
        assert errors == []
        assert cleaned['reporter_mobile'] == ''

    def test_13_digit_mobile_allowed(self):
        """Up to 13 digits is valid (international format)."""
        validate_input = get_validate()
        cleaned, errors = validate_input({'reporter_mobile': '9198765432100'})
        assert errors == []

    def test_14_digit_mobile_rejected(self):
        """14+ digits should fail."""
        validate_input = get_validate()
        _, errors = validate_input({'reporter_mobile': '91987654321001'})
        assert len(errors) == 1


class TestPhotoValidation:
    def test_empty_photo_allowed(self):
        validate_input = get_validate()
        cleaned, errors = validate_input({'photo': ''})
        assert errors == []
        assert cleaned['photo'] == ''

    def test_none_photo_allowed(self):
        validate_input = get_validate()
        cleaned, errors = validate_input({'photo': None})
        assert errors == []

    def test_small_photo_passes(self):
        validate_input = get_validate()
        small_photo = 'data:image/jpeg;base64,' + 'A' * 1000
        cleaned, errors = validate_input({'photo': small_photo})
        assert errors == []
        assert cleaned['photo'] == small_photo

    def test_photo_exceeding_700k_chars_rejected(self):
        validate_input = get_validate()
        huge_photo = 'A' * 700_001
        cleaned, errors = validate_input({'photo': huge_photo})
        assert any('Photo' in e for e in errors)
        assert cleaned['photo'] == ''

    def test_photo_exactly_at_limit_passes(self):
        validate_input = get_validate()
        at_limit = 'A' * 700_000
        cleaned, errors = validate_input({'photo': at_limit})
        assert not any('Photo' in e for e in errors)


class TestMultipleErrors:
    def test_multiple_validation_errors_collected(self):
        """All errors are collected and returned together."""
        validate_input = get_validate()
        _, errors = validate_input({
            'gender': 'InvalidGender',
            'reporter_mobile': '123',  # too short
            'contact_mobile': '456',   # too short
        })
        assert len(errors) >= 3
