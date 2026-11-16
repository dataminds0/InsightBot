import bcrypt

from insightbot.infra.security import (
    generate_csrf_token,
    generate_session_token,
    hash_password,
    verify_and_upgrade_password,
)


def test_argon2_hashing_and_verification():
    password = "SuperSecurePassword123!"
    pw_hash = hash_password(password)
    assert pw_hash.startswith("$argon2id$")

    valid, upgraded = verify_and_upgrade_password(password, pw_hash)
    assert valid is True
    # Already latest Argon2id configuration, so no upgrade needed
    assert upgraded is None

    invalid, _ = verify_and_upgrade_password("WrongPassword!", pw_hash)
    assert invalid is False


def test_legacy_bcrypt_verification_and_transparent_upgrade():
    password = "LegacyBcryptPassword2024"
    # Create an authentic bcrypt hash
    salt = bcrypt.gensalt()
    bcrypt_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    assert bcrypt_hash.startswith("$2b$")

    # Verify and transparently upgrade
    valid, upgraded = verify_and_upgrade_password(password, bcrypt_hash)
    assert valid is True
    assert upgraded is not None
    assert upgraded.startswith("$argon2id$")

    # Verify the upgraded hash works with password
    valid2, _ = verify_and_upgrade_password(password, upgraded)
    assert valid2 is True


def test_token_generation():
    session_token = generate_session_token()
    assert len(session_token) >= 32
    csrf_token = generate_csrf_token()
    assert len(csrf_token) == 32
