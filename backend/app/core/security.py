"""Cryptographic utilities, Argon2id hashing, token digests, and password policy."""

import hashlib
import re
import secrets

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# Initialize password hasher with robust parameters
password_hash_engine = PasswordHash((Argon2Hasher(),))


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return password_hash_engine.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    return password_hash_engine.verify(plain_password, hashed_password)


def hash_token(raw_token: str) -> str:
    """Compute SHA-256 hex digest of an opaque token for database storage and matching."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def generate_secure_token(length_bytes: int = 32) -> str:
    """Generate an opaque cryptographically secure URL-safe random string."""
    return secrets.token_urlsafe(length_bytes)


def validate_password_policy(password: str) -> None:
    """Enforce baseline administrative password complexity requirements."""
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters long.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one digit.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must contain at least one special character.")
