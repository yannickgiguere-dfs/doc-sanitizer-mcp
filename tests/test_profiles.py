"""Tests for profile management."""

import json
import tempfile
from pathlib import Path

import pytest

from src.config_schema import PIIAction, PIIType, validate_profile_name
from src.profiles import (
    ProfileManager,
    ProfileNotFoundError,
    ProfileValidationError,
)


@pytest.fixture
def temp_storage():
    """Create a temporary storage file."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        yield f.name
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def manager(temp_storage):
    """Create a ProfileManager with temporary storage."""
    return ProfileManager(temp_storage)


class TestValidateProfileName:
    """Tests for profile name validation."""

    def test_valid_names(self):
        assert validate_profile_name("default")[0] is True
        assert validate_profile_name("high_privacy")[0] is True
        assert validate_profile_name("my-profile-1")[0] is True
        assert validate_profile_name("Test123")[0] is True

    def test_empty_name(self):
        is_valid, error = validate_profile_name("")
        assert is_valid is False
        assert "empty" in error.lower()

    def test_too_long_name(self):
        is_valid, error = validate_profile_name("a" * 51)
        assert is_valid is False
        assert "50" in error

    def test_invalid_characters(self):
        is_valid, error = validate_profile_name("test profile")
        assert is_valid is False

        is_valid, error = validate_profile_name("test@profile")
        assert is_valid is False


class TestProfileManager:
    """Tests for ProfileManager."""

    def test_default_profile_created(self, manager):
        """Default profile should be created on initialization."""
        profiles = manager.list_profiles()
        assert len(profiles) == 1
        assert profiles[0].name == "default"
        assert profiles[0].id == 1

    def test_get_default_profile(self, manager):
        """Should be able to get default profile."""
        profile = manager.get_default_profile()
        assert profile.name == "default"

    def test_get_profile_by_name(self, manager):
        """Should get profile by name (case-insensitive)."""
        profile = manager.get_profile("default")
        assert profile.name == "default"

        profile = manager.get_profile("DEFAULT")
        assert profile.name == "default"

    def test_get_profile_by_id(self, manager):
        """Should get profile by ID."""
        profile = manager.get_profile(1)
        assert profile.name == "default"

    def test_get_nonexistent_profile(self, manager):
        """Should raise error for nonexistent profile."""
        with pytest.raises(ProfileNotFoundError):
            manager.get_profile("nonexistent")

        with pytest.raises(ProfileNotFoundError):
            manager.get_profile(999)

    def test_create_profile(self, manager):
        """Should create a new profile."""
        profile = manager.create_profile("high_privacy")
        assert profile.name == "high_privacy"
        assert profile.id == 2

        profiles = manager.list_profiles()
        assert len(profiles) == 2

    def test_create_profile_from_existing(self, manager):
        """Should copy config from source profile."""
        # First modify the default profile
        manager.update_profile("default", {"person_name": PIIAction.DELETE})

        # Create new profile from default
        profile = manager.create_profile("copy_of_default", from_profile="default")
        assert profile.config.person_name.action == PIIAction.DELETE

    def test_create_duplicate_name(self, manager):
        """Should reject duplicate profile names."""
        manager.create_profile("test")

        with pytest.raises(ProfileValidationError):
            manager.create_profile("test")

        with pytest.raises(ProfileValidationError):
            manager.create_profile("TEST")  # Case-insensitive

    def test_update_profile(self, manager):
        """Should update profile settings."""
        profile = manager.update_profile("default", {"person_name": PIIAction.DELETE})
        assert profile.config.person_name.action == PIIAction.DELETE

    def test_update_invalid_action(self, manager):
        """Should reject invalid actions for PII types."""
        # Email doesn't support INVENT
        with pytest.raises(ProfileValidationError):
            manager.update_profile("default", {"email": PIIAction.INVENT})

    def test_delete_profile(self, manager):
        """Should delete non-default profiles."""
        manager.create_profile("to_delete")
        assert len(manager.list_profiles()) == 2

        manager.delete_profile("to_delete")
        assert len(manager.list_profiles()) == 1

    def test_cannot_delete_default(self, manager):
        """Should not be able to delete default profile."""
        with pytest.raises(ProfileValidationError):
            manager.delete_profile("default")

    def test_copy_profile(self, manager):
        """Should copy a profile with new name."""
        profile = manager.copy_profile("default", "my_copy")
        assert profile.name == "my_copy"
        assert profile.id == 2

    def test_persistence(self, temp_storage):
        """Profiles should persist across manager instances."""
        manager1 = ProfileManager(temp_storage)
        manager1.create_profile("persistent")
        manager1.update_profile("persistent", {"phone": PIIAction.INVENT})

        # Create new manager instance
        manager2 = ProfileManager(temp_storage)
        profile = manager2.get_profile("persistent")
        assert profile.config.phone.action == PIIAction.INVENT
