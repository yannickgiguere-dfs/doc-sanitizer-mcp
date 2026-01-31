"""Configuration schema for PII types and profile settings."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class PIIType(str, Enum):
    """Types of PII that can be detected and handled."""
    PERSON_NAME = "person_name"
    EMAIL = "email"
    PHONE = "phone"
    COMPANY = "company"
    ADDRESS = "address"
    FINANCIAL = "financial"
    ID_NUMBERS = "id_numbers"
    DATE_OF_BIRTH = "date_of_birth"


class PIIAction(str, Enum):
    """Actions that can be taken on detected PII."""
    DELETE = "delete"
    INVENT = "invent"
    KEEP_PART = "keep_part"


# Valid actions for each PII type
VALID_ACTIONS: dict[PIIType, list[PIIAction]] = {
    PIIType.PERSON_NAME: [PIIAction.DELETE, PIIAction.INVENT, PIIAction.KEEP_PART],
    PIIType.EMAIL: [PIIAction.DELETE, PIIAction.KEEP_PART],
    PIIType.PHONE: [PIIAction.DELETE, PIIAction.INVENT, PIIAction.KEEP_PART],
    PIIType.COMPANY: [PIIAction.KEEP_PART, PIIAction.INVENT],
    PIIType.ADDRESS: [PIIAction.DELETE, PIIAction.INVENT],
    PIIType.FINANCIAL: [PIIAction.DELETE, PIIAction.INVENT],
    PIIType.ID_NUMBERS: [PIIAction.DELETE, PIIAction.INVENT],
    PIIType.DATE_OF_BIRTH: [PIIAction.DELETE, PIIAction.INVENT],
}


# Human-readable descriptions for each action per PII type
ACTION_DESCRIPTIONS: dict[PIIType, dict[PIIAction, str]] = {
    PIIType.PERSON_NAME: {
        PIIAction.DELETE: "Remove name completely, replace with [NAME_REMOVED]",
        PIIAction.INVENT: "Replace with consistent synthetic name",
        PIIAction.KEEP_PART: "Keep first name only, number duplicates (e.g., John 1, John 2)",
    },
    PIIType.EMAIL: {
        PIIAction.DELETE: "Remove email completely, replace with [EMAIL_REMOVED]",
        PIIAction.KEEP_PART: "Keep domain only (e.g., [EMAIL_REDACTED]@company.com)",
    },
    PIIType.PHONE: {
        PIIAction.DELETE: "Remove phone completely, replace with [PHONE_REMOVED]",
        PIIAction.INVENT: "Replace with synthetic phone number",
        PIIAction.KEEP_PART: "Keep country/area code only (e.g., +1 (555) [REDACTED])",
    },
    PIIType.COMPANY: {
        PIIAction.KEEP_PART: "Keep company name as-is",
        PIIAction.INVENT: "Replace with consistent synthetic company name",
    },
    PIIType.ADDRESS: {
        PIIAction.DELETE: "Remove address completely, replace with [ADDRESS_REMOVED]",
        PIIAction.INVENT: "Replace with synthetic address",
    },
    PIIType.FINANCIAL: {
        PIIAction.DELETE: "Remove financial data, replace with [FINANCIAL_REMOVED]",
        PIIAction.INVENT: "Replace with synthetic financial data",
    },
    PIIType.ID_NUMBERS: {
        PIIAction.DELETE: "Remove ID numbers, replace with [ID_REMOVED]",
        PIIAction.INVENT: "Replace with synthetic ID numbers",
    },
    PIIType.DATE_OF_BIRTH: {
        PIIAction.DELETE: "Remove date of birth, replace with [DOB_REMOVED]",
        PIIAction.INVENT: "Replace with synthetic date of birth",
    },
}


class PIIConfig(BaseModel):
    """Configuration for a single PII type."""
    action: PIIAction
    description: Optional[str] = None

    def get_description(self, pii_type: PIIType) -> str:
        """Get the description for this action."""
        if self.description:
            return self.description
        return ACTION_DESCRIPTIONS.get(pii_type, {}).get(self.action, "")


class ProfileConfig(BaseModel):
    """Full PII configuration for a profile."""
    person_name: PIIConfig = Field(default_factory=lambda: PIIConfig(action=PIIAction.KEEP_PART))
    email: PIIConfig = Field(default_factory=lambda: PIIConfig(action=PIIAction.KEEP_PART))
    phone: PIIConfig = Field(default_factory=lambda: PIIConfig(action=PIIAction.DELETE))
    company: PIIConfig = Field(default_factory=lambda: PIIConfig(action=PIIAction.KEEP_PART))
    address: PIIConfig = Field(default_factory=lambda: PIIConfig(action=PIIAction.DELETE))
    financial: PIIConfig = Field(default_factory=lambda: PIIConfig(action=PIIAction.DELETE))
    id_numbers: PIIConfig = Field(default_factory=lambda: PIIConfig(action=PIIAction.DELETE))
    date_of_birth: PIIConfig = Field(default_factory=lambda: PIIConfig(action=PIIAction.DELETE))

    def get_config_for_type(self, pii_type: PIIType) -> PIIConfig:
        """Get the configuration for a specific PII type."""
        return getattr(self, pii_type.value)

    def set_action(self, pii_type: PIIType, action: PIIAction) -> None:
        """Set the action for a specific PII type."""
        if action not in VALID_ACTIONS[pii_type]:
            valid = [a.value for a in VALID_ACTIONS[pii_type]]
            raise ValueError(f"Invalid action '{action}' for {pii_type.value}. Valid: {valid}")
        setattr(self, pii_type.value, PIIConfig(action=action))

    def to_summary_table(self) -> list[dict]:
        """Convert config to a summary table format."""
        rows = []
        for pii_type in PIIType:
            config = self.get_config_for_type(pii_type)
            rows.append({
                "pii_type": pii_type.value,
                "action": config.action.value,
                "description": config.get_description(pii_type),
            })
        return rows


class Profile(BaseModel):
    """A named sanitization profile."""
    id: int
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    config: ProfileConfig = Field(default_factory=ProfileConfig)

    def update_config(self, pii_type: PIIType, action: PIIAction) -> None:
        """Update a specific PII type's action."""
        self.config.set_action(pii_type, action)
        self.modified_at = lambda: datetime.now(timezone.utc)()


class ProfileStore(BaseModel):
    """Storage model for all profiles."""
    profiles: list[Profile] = Field(default_factory=list)
    next_id: int = 1


def get_default_profile() -> Profile:
    """Create the default profile with standard settings."""
    return Profile(
        id=1,
        name="default",
        config=ProfileConfig(),  # Uses default values from ProfileConfig
    )


def validate_profile_name(name: str) -> tuple[bool, str]:
    """Validate a profile name.

    Returns (is_valid, error_message).
    """
    import re

    if not name:
        return False, "Profile name cannot be empty"

    if len(name) > 50:
        return False, "Profile name must be 50 characters or less"

    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return False, "Profile name must contain only letters, numbers, underscores, and hyphens"

    return True, ""
