import mongomock
import pytest
from fastapi.testclient import TestClient

from insightbot.api.deps import get_db
from insightbot.api.main import app
from insightbot.models.user import Role, UserStatus
from insightbot.repositories.user_repository import UserRepository
from insightbot.services.auth_service import AuthService


@pytest.fixture
def api_client():
    mock_client = mongomock.MongoClient()
    mock_db = mock_client["test_auth_api"]

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    # Pre-seed an admin and an active viewer
    repo = UserRepository(mock_db)
    service = AuthService(repo)
    admin = service.register(
        "system_admin", "AdminPass123", role=Role.ADMIN, status=UserStatus.ACTIVE
    )
    viewer = service.register(
        "viewer_one", "ViewerPass123", role=Role.VIEWER, status=UserStatus.ACTIVE
    )

    yield client, service, admin, viewer
    app.dependency_overrides.clear()


def test_api_register_creates_pending_user(api_client):
    client, _, _, _ = api_client
    resp = client.post(
        "/api/auth/register",
        json={"username": "registered_user", "password": "Password123", "email": "test@domain.com"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert "approval" in data["message"]


def test_api_login_and_me_lifecycle(api_client):
    client, _, _, viewer = api_client
    # Login as viewer
    resp = client.post(
        "/api/auth/login",
        json={"username": "viewer_one", "password": "ViewerPass123"},
    )
    assert resp.status_code == 200
    token = resp.json()["token"]
    assert token is not None

    # Fetch /api/auth/me with Bearer token
    resp_me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_me.status_code == 200
    assert resp_me.json()["username"] == "viewer_one"
    assert resp_me.json()["role"] == "viewer"


def test_api_viewer_cannot_administer(api_client):
    client, _, _, _ = api_client
    # Login as viewer
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "viewer_one", "password": "ViewerPass123"},
    )
    viewer_token = login_resp.json()["token"]

    # Viewer attempts to access admin endpoint -> 403 Forbidden
    admin_resp = client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert admin_resp.status_code == 403
    assert "Forbidden" in admin_resp.json()["detail"]


def test_api_admin_can_access_and_immediate_revocation(api_client):
    client, _, admin, viewer = api_client
    # Login as admin
    admin_login = client.post(
        "/api/auth/login",
        json={"username": "system_admin", "password": "AdminPass123"},
    )
    admin_token = admin_login.json()["token"]

    # Admin lists users
    list_resp = client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 2

    # Viewer logs in
    viewer_login = client.post(
        "/api/auth/login",
        json={"username": "viewer_one", "password": "ViewerPass123"},
    )
    viewer_token = viewer_login.json()["token"]

    # Admin disables viewer account
    disable_resp = client.patch(
        f"/api/admin/users/{viewer.user_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "disabled"},
    )
    assert disable_resp.status_code == 200

    # Viewer makes immediate request with old token -> must be 401 Unauthorized
    revoked_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert revoked_resp.status_code == 401
