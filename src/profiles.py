"""Profile management system for PII sanitization profiles."""

import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from .config_schema import (
    Profile,
    ProfileStore,
    ProfileConfig,
    PIIType,
    PIIAction,
    get_default_profile,
    validate_profile_name,
    VALID_ACTIONS,
)


class ProfileError(Exception):
    """Base exception for profile operations."""
    pass


class ProfileNotFoundError(ProfileError):
    """Raised when a profile is not found."""
    pass


class ProfileValidationError(ProfileError):
    """Raised when profile validation fails."""
    pass


class ProfileManager:
    """Manages PII sanitization profiles with JSON persistence."""

    def __init__(self, storage_path: Optional[str] = None):
        """Initialize the profile manager.

        Args:
            storage_path: Path to the JSON storage file.
                          Defaults to PROFILE_STORAGE env var or /app/data/profiles.json
        """
        if storage_path is None:
            storage_path = os.environ.get(
                "PROFILE_STORAGE",
                "/app/data/profiles.json"
            )
        self.storage_path = Path(storage_path)
        self._store: Optional[ProfileStore] = None
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        """Ensure the storage directory and file exist."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            self._initialize_store()

    def _initialize_store(self) -> None:
        """Initialize the store with the default profile."""
        default_profile = get_default_profile()
        store = ProfileStore(profiles=[default_profile], next_id=2)
        self._save_store(store)
        self._store = store

    def _load_store(self) -> ProfileStore:
        """Load the profile store from disk."""
        if self._store is not None:
            return self._store

        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            self._store = ProfileStore.model_validate(data)
        except (FileNotFoundError, json.JSONDecodeError):
            self._initialize_store()

        return self._store

    def _save_store(self, store: Optional[ProfileStore] = None) -> None:
        """Save the profile store to disk."""
        if store is None:
            store = self._store
        if store is None:
            return

        with open(self.storage_path, 'w') as f:
            json.dump(store.model_dump(mode='json'), f, indent=2, default=str)
        self._store = store

    def list_profiles(self) -> list[Profile]:
        """List all profiles."""
        store = self._load_store()
        return store.profiles

    def get_profile(self, identifier: str | int) -> Profile:
        """Get a profile by name or ID.

        Args:
            identifier: Profile name (str) or ID (int)

        Returns:
            The matching profile

        Raises:
            ProfileNotFoundError: If no matching profile is found
        """
        store = self._load_store()

        for profile in store.profiles:
            if isinstance(identifier, int) and profile.id == identifier:
                return profile
            if isinstance(identifier, str) and profile.name.lower() == identifier.lower():
                return profile

        raise ProfileNotFoundError(f"Profile not found: {identifier}")

    def get_profile_by_id(self, profile_id: int) -> Profile:
        """Get a profile by ID."""
        return self.get_profile(profile_id)

    def get_profile_by_name(self, name: str) -> Profile:
        """Get a profile by name."""
        return self.get_profile(name)

    def create_profile(
        self,
        name: str,
        from_profile: Optional[str | int] = None
    ) -> Profile:
        """Create a new profile.

        Args:
            name: Name for the new profile
            from_profile: Optional profile to copy settings from (default: "default")

        Returns:
            The newly created profile

        Raises:
            ProfileValidationError: If the name is invalid or already exists
        """
        # Validate name
        is_valid, error = validate_profile_name(name)
        if not is_valid:
            raise ProfileValidationError(error)

        store = self._load_store()

        # Check for duplicate name
        for profile in store.profiles:
            if profile.name.lower() == name.lower():
                raise ProfileValidationError(f"Profile '{name}' already exists")

        # Get source profile for copying config
        if from_profile is None:
            from_profile = "default"

        try:
            source = self.get_profile(from_profile)
        except ProfileNotFoundError:
            raise ProfileValidationError(f"Source profile not found: {from_profile}")

        # Create new profile
        new_profile = Profile(
            id=store.next_id,
            name=name,
            config=source.config.model_copy(deep=True),
        )

        store.profiles.append(new_profile)
        store.next_id += 1
        self._save_store(store)

        return new_profile

    def update_profile(
        self,
        identifier: str | int,
        changes: dict[str, PIIAction]
    ) -> Profile:
        """Update a profile's PII settings.

        Args:
            identifier: Profile name or ID
            changes: Dict mapping PII type names to new actions

        Returns:
            The updated profile

        Raises:
            ProfileNotFoundError: If the profile doesn't exist
            ProfileValidationError: If changes are invalid
        """
        store = self._load_store()
        profile = self.get_profile(identifier)

        # Find and update the profile in the store
        for i, p in enumerate(store.profiles):
            if p.id == profile.id:
                for pii_type_str, action in changes.items():
                    try:
                        pii_type = PIIType(pii_type_str)
                    except ValueError:
                        raise ProfileValidationError(f"Invalid PII type: {pii_type_str}")

                    if action not in VALID_ACTIONS[pii_type]:
                        valid = [a.value for a in VALID_ACTIONS[pii_type]]
                        raise ProfileValidationError(
                            f"Invalid action '{action.value}' for {pii_type_str}. Valid: {valid}"
                        )

                    p.config.set_action(pii_type, action)

                p.modified_at = datetime.now(timezone.utc)
                store.profiles[i] = p
                self._save_store(store)
                return p

        raise ProfileNotFoundError(f"Profile not found: {identifier}")

    def delete_profile(self, identifier: str | int) -> bool:
        """Delete a profile.

        Args:
            identifier: Profile name or ID

        Returns:
            True if deleted successfully

        Raises:
            ProfileNotFoundError: If the profile doesn't exist
            ProfileValidationError: If trying to delete the default profile
        """
        profile = self.get_profile(identifier)

        if profile.name.lower() == "default":
            raise ProfileValidationError("Cannot delete the default profile")

        store = self._load_store()
        store.profiles = [p for p in store.profiles if p.id != profile.id]
        self._save_store(store)

        return True

    def copy_profile(self, source: str | int, new_name: str) -> Profile:
        """Copy a profile with a new name.

        Args:
            source: Source profile name or ID
            new_name: Name for the new profile

        Returns:
            The newly created profile
        """
        return self.create_profile(new_name, from_profile=source)

    def get_default_profile(self) -> Profile:
        """Get the default profile."""
        return self.get_profile("default")

    def format_profiles_table(self) -> str:
        """Format all profiles as a text table for display."""
        profiles = self.list_profiles()

        # Header
        headers = ["ID", "Name", "person_name", "email", "phone", "company",
                   "address", "financial", "id_numbers", "date_of_birth"]

        # Calculate column widths
        widths = [len(h) for h in headers]
        rows = []
        for p in profiles:
            row = [
                str(p.id),
                p.name,
                p.config.person_name.action.value,
                p.config.email.action.value,
                p.config.phone.action.value,
                p.config.company.action.value,
                p.config.address.action.value,
                p.config.financial.action.value,
                p.config.id_numbers.action.value,
                p.config.date_of_birth.action.value,
            ]
            rows.append(row)
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell))

        # Build table
        lines = []
        header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
        lines.append(header_line)
        lines.append("-+-".join("-" * w for w in widths))

        for row in rows:
            lines.append(" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))

        return "\n".join(lines)

    def format_profile_detail(self, identifier: str | int) -> str:
        """Format a single profile's details for display."""
        profile = self.get_profile(identifier)

        lines = [
            f"Profile: {profile.name} (ID: {profile.id})",
            f"Created: {profile.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Modified: {profile.modified_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "PII Type        | Action    | Description",
            "----------------|-----------|" + "-" * 50,
        ]

        for row in profile.config.to_summary_table():
            pii_type = row["pii_type"].ljust(15)
            action = row["action"].ljust(9)
            description = row["description"]
            lines.append(f"{pii_type} | {action} | {description}")

        return "\n".join(lines)
