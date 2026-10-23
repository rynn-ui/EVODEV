"""Unit tests for secret redaction, safety validator, and cryptographic functions."""

import io
import zipfile
import pytest

from evodev.security.crypto import (
    compute_sha256,
    compute_hmac,
    encrypt_payload,
    decrypt_payload,
)
from evodev.security.redactor import SecretRedactor, redact_text, redact_data
from evodev.security.validator import (
    ArchiveSizeExceededError,
    ProfileValidator,
    UnsafeArchivePathError,
)


def test_secret_redactor_patterns():
    redactor = SecretRedactor()

    # OpenAI key
    text_openai = "Connecting with key sk-proj-1234567890abcdef1234567890abcdef"
    redacted = redactor.redact_text(text_openai)
    assert "[REDACTED_OPENAI_KEY]" in redacted
    assert "sk-proj" not in redacted

    # Anthropic key
    text_ant = "Auth header sk-ant-api03-1234567890abcdef1234567890abcdef"
    redacted = redactor.redact_text(text_ant)
    assert "[REDACTED_ANTHROPIC_KEY]" in redacted

    # GitHub token
    text_gh = "git push with ghp_1234567890abcdef1234567890abcdef1234"
    redacted = redactor.redact_text(text_gh)
    assert "[REDACTED_GITHUB_TOKEN]" in redacted

    # Google API Key
    text_google = "API endpoint key AIzaSyD1234567890abcdef1234567890abcde"
    redacted = redactor.redact_text(text_google)
    assert "[REDACTED_GOOGLE_API_KEY]" in redacted

    # AWS Key
    text_aws = "Deploying to AWS using AKIAIOSFODNN7EXAMPLE"
    redacted = redactor.redact_text(text_aws)
    assert "[REDACTED_AWS_KEY]" in redacted

    # Private Key
    text_key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0\n-----END RSA PRIVATE KEY-----"
    redacted = redactor.redact_text(text_key)
    assert "[REDACTED_PRIVATE_KEY]" in redacted

    # Basic Auth URL
    text_url = "https://admin:superSecretP@ssword123@api.internal.com/v1"
    redacted = redactor.redact_text(text_url)
    assert "[REDACTED_USER]:[REDACTED_PASS]" in redacted
    assert "superSecretP@ssword123" not in redacted


def test_recursive_data_redaction():
    data = {
        "user": "developer",
        "api_key": "raw_secret_value_123",
        "nested": {
            "token": "ghp_1234567890abcdef1234567890abcdef1234",
            "logs": ["All systems ok", "Auth: Bearer sk-ant-1234567890abcdef1234567890abcdef"],
        },
    }
    redacted = redact_data(data)
    assert redacted["api_key"] == "[REDACTED_SENSITIVE_KEY]"
    assert "[REDACTED_GITHUB_TOKEN]" in redacted["nested"]["token"] or "[REDACTED_SENSITIVE_KEY]" in redacted["nested"]["token"]
    assert "[REDACTED_ANTHROPIC_KEY]" in redacted["nested"]["logs"][1]


def test_validator_rejects_zip_slip():
    validator = ProfileValidator()

    # Create in-memory zip with malicious traversal path
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0::/root:/bin/bash")
    buf.seek(0)

    with zipfile.ZipFile(buf, "r") as zf:
        with pytest.raises(UnsafeArchivePathError):
            validator.validate_archive_safety(zf)


def test_validator_rejects_zip_bomb():
    validator = ProfileValidator()
    # Configure tiny entry size limit to trigger error
    validator.config.max_profile_single_entry_bytes = 1000

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("huge_file.json", "0" * 5000)
    buf.seek(0)

    with zipfile.ZipFile(buf, "r") as zf:
        with pytest.raises(ArchiveSizeExceededError):
            validator.validate_archive_safety(zf)


def test_crypto_aes_gcm_roundtrip():
    secret_text = b"Secret developer lesson payload: Do not commit .env"
    password = "MyStrongEncryptionPassword!123"

    # Encrypt
    encrypted_blob = encrypt_payload(secret_text, password)
    assert encrypted_blob != secret_text
    assert len(encrypted_blob) > len(secret_text)

    # Decrypt with correct password
    decrypted = decrypt_payload(encrypted_blob, password)
    assert decrypted == secret_text

    # Decrypt with wrong password fails
    with pytest.raises(Exception):
        decrypt_payload(encrypted_blob, "WrongPassword")


def test_sha256_and_hmac():
    data = "EvoDev Profile Integrity Check"
    h1 = compute_sha256(data)
    h2 = compute_sha256(data)
    assert h1 == h2
    assert len(h1) == 64

    sig = compute_hmac(b"secret_key", data.encode("utf-8"))
    assert len(sig) == 64
