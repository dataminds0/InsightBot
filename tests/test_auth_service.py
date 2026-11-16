import bcrypt
import mongomock
import pytest

from insightbot.models.user import Role, UserStatus
from insightbot.repositories.user_repository import UserRepository
from insightbot.services.auth_service import AuthenticationError, AuthorizationError, AuthService


@pytest.fixture
def auth_service():
    client = mongomock.MongoClient()
    db = client["test_auth"]
    user_repo = UserRepository(db)
    return AuthService(user_repo)


def test_register_creates_pending_viewer(auth_service):
    user = auth_service.register(
        username="new_analyst",
        password="ValidPassword123",
        email="analyst@example.com",
    )
    assert user.username == "new_analyst"
    assert user.role == Role.VIEWER
    assert user.status == UserStatus.PENDING


def test_login_rejects_pending_user(auth_service):
    auth_service.register("pending_user", "ValidPassword123")
    with pytest.raises(AuthenticationError) as exc:
        auth_service.login("pending_user", "ValidPassword123")
    assert "pending administrator approval" in str(exc.value)


def test_login_rejects_disabled_user(auth_service):
    auth_service.register(
        "disabled_user",
        "ValidPassword123",
        status=UserStatus.DISABLED,
    )
    with pytest.raises(AuthenticationError) as exc:
        auth_service.login("disabled_user", "ValidPassword123")
    assert "disabled" in str(exc.value)


def test_login_transparently_upgrades_legacy_bcrypt(auth_service):
    # Seed legacy bcrypt user directly into repository
    password = "MyLegacyPassword123"
    bcrypt_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    legacy_user = auth_service.register(
        "legacy_user",
        "temp_password",
        status=UserStatus.ACTIVE,
    )
    # Overwrite password hash with real legacy bcrypt
    auth_service.user_repo.update_password_hash(legacy_user.user_id, bcrypt_hash)

    # Login should succeed and transparently upgrade hash in database
    user, session = auth_service.login("legacy_user", password)
    assert session.session_token is not None

    refreshed_user = auth_service.user_repo.get_by_id(user.user_id)
    assert refreshed_user.password_hash.startswith("$argon2id$")


def test_session_validation_and_idle_extension(auth_service):
    auth_service.register("active_user", "ValidPassword123", status=UserStatus.ACTIVE)
    _, session = auth_service.login("active_user", "ValidPassword123")

    # Regular validation extends idle timeout
    initial_expiry = session.expires_at
    _, validated_session = auth_service.validate_session(session.session_token, extend_idle=True)
    assert validated_session.expires_at >= initial_expiry

    # Background polling DOES NOT extend idle timeout
    initial_poll_expiry = validated_session.expires_at
    _, poll_session = auth_service.validate_session(session.session_token, extend_idle=False)
    assert poll_session.expires_at == initial_poll_expiry


def test_immediate_session_revocation_on_role_or_status_change(auth_service):
    admin = auth_service.register(
        "admin_user", "AdminPassword123", role=Role.ADMIN, status=UserStatus.ACTIVE
    )
    viewer = auth_service.register(
        "viewer_user", "ViewerPassword123", role=Role.VIEWER, status=UserStatus.ACTIVE
    )

    # Viewer logs in and establishes active session
    _, viewer_session = auth_service.login("viewer_user", "ViewerPassword123")
    assert auth_service.user_repo.get_session(viewer_session.session_token) is not None

    # Admin changes viewer role to ANALYST -> active session must be revoked immediately
    auth_service.change_user_role(admin, viewer.user_id, Role.ANALYST)
    assert auth_service.user_repo.get_session(viewer_session.session_token) is None

    # Viewer logs in again
    _, viewer_session2 = auth_service.login("viewer_user", "ViewerPassword123")
    assert auth_service.user_repo.get_session(viewer_session2.session_token) is not None

    # Admin disables viewer -> active session must be revoked immediately
    auth_service.change_user_status(admin, viewer.user_id, UserStatus.DISABLED)
    assert auth_service.user_repo.get_session(viewer_session2.session_token) is None


def test_last_admin_guard(auth_service):
    admin = auth_service.register(
        "sole_admin", "AdminPassword123", role=Role.ADMIN, status=UserStatus.ACTIVE
    )

    # Attempting to demote sole admin must fail
    with pytest.raises(AuthorizationError) as exc_demote:
        auth_service.change_user_role(admin, admin.user_id, Role.VIEWER)
    assert "last remaining active administrator" in str(exc_demote.value)

    # Attempting to disable sole admin must fail
    with pytest.raises(AuthorizationError) as exc_disable:
        auth_service.change_user_status(admin, admin.user_id, UserStatus.DISABLED)
    assert "last remaining active administrator" in str(exc_disable.value)

    # Adding a second active admin permits modifying the first
    admin2 = auth_service.register(
        "second_admin", "AdminPassword123", role=Role.ADMIN, status=UserStatus.ACTIVE
    )
    updated = auth_service.change_user_role(admin2, admin.user_id, Role.ANALYST)
    assert updated.role == Role.ANALYST
