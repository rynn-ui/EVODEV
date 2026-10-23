"""Safety and integrity validation for profiles, file paths, and archive contents."""

import os
from pathlib import Path
import re
from typing import List
import zipfile

from evodev.config import EvoDevConfig, load_config


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


class UnsafeArchivePathError(ValidationError):
    """Raised when an archive contains paths attempting directory traversal (Zip Slip)."""
    pass


class ArchiveSizeExceededError(ValidationError):
    """Raised when archive contents exceed safety thresholds (Zip Bomb defense)."""
    pass


class MalformedProfileError(ValidationError):
    """Raised when profile contents fail schema or structural requirements."""
    pass


class ProfileValidator:
    """Enforces safety, path sanitization, and size caps on archive files and schemas."""

    DANGEROUS_PATTERNS: List[re.Pattern] = [
        re.compile(r"(?i)\bignore\s+(all\s+)?previous\s+instructions\b"),
        re.compile(r"(?i)<\s*system\s*>"),
        re.compile(r"(?i)<\s*/\s*system\s*>"),
        re.compile(r"(?i)\boverride\s+all\s+(security\s+)?rules\b"),
    ]

    def __init__(self, config: EvoDevConfig = None):
        self.config = config or load_config()

    def validate_archive_safety(self, zip_file: zipfile.ZipFile) -> None:
        """Inspect archive members for Zip-Slip traversal, zip bomb, or unauthorized file types."""
        total_uncompressed_bytes = 0
        total_files = 0

        for member in zip_file.infolist():
            total_files += 1
            if total_files > 50:
                raise ArchiveSizeExceededError("Archive contains too many file entries (max 50).")

            # Check for path traversal (Zip Slip)
            filename = member.filename
            if (
                ".." in filename
                or filename.startswith("/")
                or filename.startswith("\\")
                or (len(filename) > 1 and filename[1] == ":")
            ):
                raise UnsafeArchivePathError(
                    f"Suspicious path traversal attempt detected in archive entry: {filename}"
                )

            # Check uncompressed size
            if member.file_size > self.config.max_profile_single_entry_bytes:
                raise ArchiveSizeExceededError(
                    f"Archive entry {filename} size ({member.file_size} bytes) exceeds maximum single entry limit ({self.config.max_profile_single_entry_bytes} bytes)."
                )

            total_uncompressed_bytes += member.file_size
            if total_uncompressed_bytes > self.config.max_profile_uncompressed_bytes:
                raise ArchiveSizeExceededError(
                    f"Archive uncompressed size ({total_uncompressed_bytes} bytes) exceeds maximum limit ({self.config.max_profile_uncompressed_bytes} bytes)."
                )

    def validate_safe_extraction_path(self, target_dir: Path, relative_name: str) -> Path:
        """Resolve extraction path and ensure it strictly resides within target_dir."""
        target_dir = target_dir.resolve()
        destination = (target_dir / relative_name).resolve()
        try:
            destination.relative_to(target_dir)
        except ValueError:
            raise UnsafeArchivePathError(
                f"Path resolution escaped destination sandbox: {relative_name}"
            )
        return destination

    def sanitize_lesson_text(self, text: str) -> str:
        """Scan text for prompt injection keywords and neutralize them."""
        if not text:
            return ""
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.search(text):
                text = pattern.sub("[FILTERED_POTENTIAL_PROMPT_INJECTION]", text)
        return text
