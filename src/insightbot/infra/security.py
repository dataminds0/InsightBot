"""Cryptographic utilities: Argon2id password hashing, legacy bcrypt verification, and token generation."""

import secrets
from typing import Optional

import argon2
import bcrypt
from argon2.exceptions import VerifyMismatchError

# Standard Argon2id configuration suitable for modern secure authentication
ph = argon2.PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MB
    parallelism=1,
    hash_len=32,
    type=argon2.Type.ID,
)


def hash_password(password: str) -> str:
    """Hash password using Argon2id."""
    return ph.hash(password)


def verify_and_upgrade_password(password: str, stored_hash: str) -> tuple[bool, Optional[str]]:
    """
    Verify password against stored hash.
    Supports native Argon2id and legacy bcrypt hashes.
    If a legacy bcrypt hash matches, generates and returns a new Argon2id hash for transparent upgrade.

    Returns:
        tuple[bool, Optional[str]]: (is_valid, new_argon2_hash_if_upgrade_needed)
    """
    if not stored_hash:
        return False, None

    # Case 1: Native Argon2id
    if stored_hash.startswith("$argon2"):
        try:
            ph.verify(stored_hash, password)
            if ph.check_needs_rehash(stored_hash):
                return True, ph.hash(password)
            return True, None
        except (VerifyMismatchError, Exception):
            return False, None

    # Case 2: Legacy bcrypt hashes ($2a$, $2b$, $2y$)
    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            is_valid = bcrypt.checkpw(
                password.encode("utf-8"),
                stored_hash.encode("utf-8"),
            )
            if is_valid:
                # Upgrade immediately to Argon2id
                new_hash = hash_password(password)
                return True, new_hash
            return False, None
        except Exception:
            return False, None

    return False, None


def generate_session_token() -> str:
    """Generate high-entropy cryptographically secure session token."""
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Generate cryptographically secure CSRF token."""
    return secrets.token_hex(16)
