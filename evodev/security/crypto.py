"""Cryptographic utilities: SHA-256 digests and optional AES-256-GCM authenticated encryption."""

import hashlib
import hmac
import os
from typing import Union
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def compute_sha256(data: Union[bytes, str]) -> str:
    """Calculate SHA-256 hex digest."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def compute_hmac(key: bytes, data: bytes) -> str:
    """Calculate HMAC-SHA256 hex digest."""
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from password using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_payload(payload: bytes, password: str) -> bytes:
    """Encrypt payload using AES-256-GCM authenticated encryption.
    
    Structure: [16 bytes salt] + [12 bytes nonce] + [ciphertext + tag]
    """
    salt = os.urandom(16)
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, payload, None)
    return salt + nonce + ciphertext


def decrypt_payload(encrypted_data: bytes, password: str) -> bytes:
    """Decrypt payload encrypted with AES-256-GCM.
    
    Raises cryptography.exceptions.InvalidTag on incorrect password or tampering.
    """
    if len(encrypted_data) < 28:
        raise ValueError("Encrypted data blob is too short to be valid.")
    salt = encrypted_data[:16]
    nonce = encrypted_data[16:28]
    ciphertext = encrypted_data[28:]
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)
