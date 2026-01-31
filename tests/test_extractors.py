"""Tests for document extractors."""

import base64
import tempfile
from pathlib import Path

import pytest

from src.extractors import (
    DocumentExtractor,
    ExtractionError,
    PlainTextExtractor,
    CSVExtractor,
)


@pytest.fixture
def extractor():
    """Create a DocumentExtractor instance."""
    return DocumentExtractor()


class TestPlainTextExtractor:
    """Tests for plain text extraction."""

    def test_extract_utf8(self):
        """Should extract UTF-8 text."""
        content = b"Hello, World!\nThis is a test."
        extractor = PlainTextExtractor()
        result = extractor.extract(content, "test.txt")

        assert result.content == "Hello, World!\nThis is a test."
        assert result.source_type == "text"

    def test_extract_latin1(self):
        """Should fall back to latin-1 for non-UTF-8."""
        content = b"Hello \xe9\xe8\xe0"  # Latin-1 encoded
        extractor = PlainTextExtractor()
        result = extractor.extract(content, "test.txt")

        assert result.source_type == "text"


class TestCSVExtractor:
    """Tests for CSV extraction."""

    def test_extract_simple_csv(self):
        """Should convert CSV to markdown table."""
        content = b"Name,Email,Phone\nJohn,john@test.com,555-1234\nJane,jane@test.com,555-5678"
        extractor = CSVExtractor()
        result = extractor.extract(content, "test.csv")

        assert "| Name | Email | Phone |" in result.content
        assert "| John | john@test.com | 555-1234 |" in result.content
        assert result.source_type == "csv"
        assert result.metadata["row_count"] == 2


class TestDocumentExtractor:
    """Tests for the main DocumentExtractor."""

    def test_supported_extensions(self, extractor):
        """Should list all supported extensions."""
        extensions = extractor.get_supported_extensions()
        assert ".txt" in extensions
        assert ".docx" in extensions
        assert ".pdf" in extensions
        assert ".xlsx" in extensions
        assert ".csv" in extensions
        assert ".eml" in extensions

    def test_extract_text_file(self, extractor):
        """Should extract plain text files."""
        content = b"Test content"
        result = extractor.extract(content, "test.txt")
        assert result.content == "Test content"

    def test_extract_from_base64(self, extractor):
        """Should decode base64 and extract."""
        content = b"Test content"
        b64 = base64.b64encode(content).decode()
        result = extractor.extract_from_base64(b64, "test.txt")
        assert result.content == "Test content"

    def test_unsupported_file_type(self, extractor):
        """Should raise error for unsupported types."""
        with pytest.raises(ExtractionError) as exc:
            extractor.extract(b"content", "test.xyz")

        assert "Unsupported file type" in str(exc.value)

    def test_file_size_limit(self, extractor):
        """Should reject files over size limit."""
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB

        with pytest.raises(ExtractionError) as exc:
            extractor.extract(large_content, "large.txt")

        assert "exceeds maximum size" in str(exc.value)

    def test_extract_from_file(self, extractor):
        """Should extract from a file on disk."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"File content")
            f.flush()

            result = extractor.extract_from_file(f.name)
            assert result.content == "File content"

        Path(f.name).unlink()

    def test_extract_nonexistent_file(self, extractor):
        """Should raise error for nonexistent file."""
        with pytest.raises(ExtractionError):
            extractor.extract_from_file("/nonexistent/file.txt")
