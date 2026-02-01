"""File storage management for binary file handling.

Provides UUID-based file storage with automatic cleanup of old files.
"""

import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Default TTL: 5 minutes
DEFAULT_FILE_TTL_SECONDS = 5 * 60


@dataclass
class StoredFile:
    """Metadata for a stored file."""
    file_id: str
    original_filename: str
    size: int
    created_at: datetime
    path: Path


class FileStore:
    """Manages file storage with UUID-based naming and automatic cleanup."""

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        ttl_seconds: int = DEFAULT_FILE_TTL_SECONDS,
        cleanup_interval_seconds: int = 60,
    ):
        """Initialize the file store.

        Args:
            storage_dir: Directory for file storage. Defaults to /app/uploads or ~/.doc-sanitizer/uploads
            ttl_seconds: Time-to-live for files in seconds (default: 5 minutes)
            cleanup_interval_seconds: How often to run cleanup (default: 60 seconds)
        """
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        elif os.path.exists("/app"):
            self.storage_dir = Path("/app/uploads")
        else:
            self.storage_dir = Path.home() / ".doc-sanitizer" / "uploads"

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds

        # File metadata stored in memory (could be extended to use SQLite)
        self._files: dict[str, StoredFile] = {}
        self._lock = threading.Lock()

        # Start background cleanup thread
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_cleanup = threading.Event()

        logger.info(f"FileStore initialized: {self.storage_dir} (TTL: {ttl_seconds}s)")

    def start_cleanup_thread(self) -> None:
        """Start the background cleanup thread."""
        if self._cleanup_thread is not None and self._cleanup_thread.is_alive():
            return

        self._stop_cleanup.clear()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
        logger.info("File cleanup thread started")

    def stop_cleanup_thread(self) -> None:
        """Stop the background cleanup thread."""
        self._stop_cleanup.set()
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
        logger.info("File cleanup thread stopped")

    def _cleanup_loop(self) -> None:
        """Background loop that periodically cleans up old files."""
        while not self._stop_cleanup.wait(timeout=self.cleanup_interval_seconds):
            try:
                self.cleanup_expired_files()
            except Exception as e:
                logger.exception(f"Error during file cleanup: {e}")

    def cleanup_expired_files(self) -> int:
        """Remove files older than TTL.

        Returns:
            Number of files deleted
        """
        now = datetime.now(timezone.utc)
        deleted_count = 0

        with self._lock:
            expired_ids = []
            for file_id, stored_file in self._files.items():
                age_seconds = (now - stored_file.created_at).total_seconds()
                if age_seconds > self.ttl_seconds:
                    expired_ids.append(file_id)

            for file_id in expired_ids:
                try:
                    self._delete_file_unsafe(file_id)
                    deleted_count += 1
                    logger.info(f"Cleaned up expired file: {file_id}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup file {file_id}: {e}")

        # Also clean up orphaned files on disk (not tracked in memory)
        deleted_count += self._cleanup_orphaned_files()

        return deleted_count

    def _cleanup_orphaned_files(self) -> int:
        """Clean up files on disk that aren't tracked in memory."""
        deleted_count = 0
        now = time.time()

        try:
            for item in self.storage_dir.iterdir():
                if item.is_file():
                    # Check if file is tracked
                    file_id = item.stem  # filename without extension
                    with self._lock:
                        if file_id not in self._files:
                            # Check file age by modification time
                            mtime = item.stat().st_mtime
                            age_seconds = now - mtime
                            if age_seconds > self.ttl_seconds:
                                item.unlink()
                                deleted_count += 1
                                logger.info(f"Cleaned up orphaned file: {item.name}")
        except Exception as e:
            logger.warning(f"Error cleaning orphaned files: {e}")

        return deleted_count

    def save_file(self, content: bytes, original_filename: str) -> StoredFile:
        """Save a file to storage.

        Args:
            content: Binary file content
            original_filename: Original filename (used for extension)

        Returns:
            StoredFile with metadata including file_id
        """
        file_id = str(uuid.uuid4())
        extension = Path(original_filename).suffix.lower()
        storage_filename = f"{file_id}{extension}"
        file_path = self.storage_dir / storage_filename

        # Write file
        file_path.write_bytes(content)

        stored_file = StoredFile(
            file_id=file_id,
            original_filename=original_filename,
            size=len(content),
            created_at=datetime.now(timezone.utc),
            path=file_path,
        )

        with self._lock:
            self._files[file_id] = stored_file

        logger.info(f"Saved file: {file_id} ({original_filename}, {len(content)} bytes)")
        return stored_file

    def get_file(self, file_id: str) -> Optional[StoredFile]:
        """Get file metadata by ID.

        Args:
            file_id: UUID of the file

        Returns:
            StoredFile if found, None otherwise
        """
        # Validate UUID format to prevent path traversal
        try:
            uuid.UUID(file_id)
        except ValueError:
            logger.warning(f"Invalid file_id format: {file_id}")
            return None

        with self._lock:
            stored_file = self._files.get(file_id)

        if stored_file and stored_file.path.exists():
            return stored_file

        # Try to find file on disk if not in memory
        return self._find_file_on_disk(file_id)

    def _find_file_on_disk(self, file_id: str) -> Optional[StoredFile]:
        """Find a file on disk that may not be tracked in memory."""
        try:
            for item in self.storage_dir.iterdir():
                if item.is_file() and item.stem == file_id:
                    stored_file = StoredFile(
                        file_id=file_id,
                        original_filename=item.name,
                        size=item.stat().st_size,
                        created_at=datetime.fromtimestamp(
                            item.stat().st_mtime, tz=timezone.utc
                        ),
                        path=item,
                    )
                    with self._lock:
                        self._files[file_id] = stored_file
                    return stored_file
        except Exception as e:
            logger.warning(f"Error finding file {file_id}: {e}")

        return None

    def read_file(self, file_id: str) -> Optional[bytes]:
        """Read file content by ID.

        Args:
            file_id: UUID of the file

        Returns:
            File content bytes, or None if not found
        """
        stored_file = self.get_file(file_id)
        if stored_file and stored_file.path.exists():
            return stored_file.path.read_bytes()
        return None

    def delete_file(self, file_id: str) -> bool:
        """Delete a file by ID.

        Args:
            file_id: UUID of the file

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            return self._delete_file_unsafe(file_id)

    def _delete_file_unsafe(self, file_id: str) -> bool:
        """Delete file without acquiring lock (caller must hold lock)."""
        stored_file = self._files.pop(file_id, None)

        if stored_file and stored_file.path.exists():
            stored_file.path.unlink()
            return True

        # Try to find and delete from disk
        try:
            for item in self.storage_dir.iterdir():
                if item.is_file() and item.stem == file_id:
                    item.unlink()
                    return True
        except Exception:
            pass

        return False

    def list_files(self) -> list[StoredFile]:
        """List all stored files.

        Returns:
            List of StoredFile objects
        """
        with self._lock:
            return list(self._files.values())

    def get_download_url(self, file_id: str, base_url: str = "http://localhost:8080") -> str:
        """Get the download URL for a file.

        Args:
            file_id: UUID of the file
            base_url: Base URL of the HTTP server

        Returns:
            Full download URL
        """
        return f"{base_url}/download/{file_id}"


# Global file store instance
_file_store: Optional[FileStore] = None


def get_file_store() -> FileStore:
    """Get the global FileStore instance."""
    global _file_store
    if _file_store is None:
        _file_store = FileStore()
        _file_store.start_cleanup_thread()
    return _file_store


def init_file_store(
    storage_dir: Optional[str] = None,
    ttl_seconds: int = DEFAULT_FILE_TTL_SECONDS,
) -> FileStore:
    """Initialize the global FileStore with custom settings."""
    global _file_store
    _file_store = FileStore(storage_dir=storage_dir, ttl_seconds=ttl_seconds)
    _file_store.start_cleanup_thread()
    return _file_store
