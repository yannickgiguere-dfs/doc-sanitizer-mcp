"""Utility functions for Doc Sanitizer."""

import os
from pathlib import Path


def get_data_dir() -> Path:
    """Get the data directory path.

    Returns the path to the data directory, creating it if necessary.
    """
    # Check environment variable first
    if data_path := os.environ.get("DATA_DIR"):
        path = Path(data_path)
    elif os.path.exists("/app/data"):
        # Docker container
        path = Path("/app/data")
    else:
        # Local development - use home directory
        path = Path.home() / ".doc-sanitizer"

    path.mkdir(parents=True, exist_ok=True)
    return path


def get_profile_storage_path() -> Path:
    """Get the profile storage file path."""
    if storage_path := os.environ.get("PROFILE_STORAGE"):
        return Path(storage_path)
    return get_data_dir() / "profiles.json"
