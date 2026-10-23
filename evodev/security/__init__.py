"""Security module for EvoDev: secret redaction, safe validation, and crypto integrity."""

from evodev.security.redactor import SecretRedactor, redact_text, redact_data
from evodev.security.validator import (
    ProfileValidator,
    ValidationError,
    UnsafeArchivePathError,
    ArchiveSizeExceededError,
)
from evodev.security.crypto import (
    compute_sha256,
    compute_hmac,
    encrypt_payload,
    decrypt_payload,
)

__all__ = [
    "SecretRedactor",
    "redact_text",
    "redact_data",
    "ProfileValidator",
    "ValidationError",
    "UnsafeArchivePathError",
    "ArchiveSizeExceededError",
    "compute_sha256",
    "compute_hmac",
    "encrypt_payload",
    "decrypt_payload",
]
