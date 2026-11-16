"""Tests for Administrator Management, Sources Health, Job Inspection, and Audit Logging."""

from datetime import datetime, timezone

import mongomock
import pytest
from fastapi.testclient import TestClient

from insightbot.api.deps import get_db
from insightbot.api.main import app
from insightbot.models.job import Job, JobStatus
from insightbot.models.source import Source, SourcePolicy
from insightbot.models.user import Role, UserStatus
from insightbot.repositories.source_repository import SourceRepository
from insightbot.repositories.user_repository import UserRepository
from insightbot.services.auth_service import AuthService


@pytest.fixture
def admin_api_env():
    mock_client = mongomock.MongoClient()
    mock_db = mock_client["test_admin_api"]

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # Pre-seed Admin and Viewer
    user_repo = UserRepository(mock_db)
    auth_service = AuthService(user_repo)
    admin = auth_service.register(
        "chief_admin", "AdminSecret123", role=Role.ADMIN, status=UserStatus.ACTIVE
    )
    viewer = auth_service.register(
        "regular_viewer", "ViewerSecret123", role=Role.VIEWER, status=UserStatus.ACTIVE
    )
    pending_user = auth_service.register(
        "new_cadet", "CadetSecret123", role=Role.VIEWER, status=UserStatus.PENDING
    )

    _, admin_session = auth_service.login("chief_admin", "AdminSecret123")
    _, viewer_session = auth_service.login("regular_viewer", "ViewerSecret123")

    admin_token = admin_session.session_token
    viewer_token = viewer_session.session_token

    # Pre-seed Source
    source_repo = SourceRepository(mock_db)
    src = Source(
        source_id="aljazeera_ar",
        name="الجزيرة",
        url="https://aljazeera.net",
        language="ar",
        enabled=False,
        policy=SourcePolicy(rate_limit_per_minute=25, retention_days=90),
    )
    source_repo.upsert_source(src)

    # Pre-seed Job
    failed_job = Job(
        job_id="job-fail-1",
        kind="ingest_source",
        target_id="aljazeera_ar",
        status=JobStatus.FAILED,
        attempts=3,
        error="Network timeout connecting to RSS feed.",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_db["jobs"].insert_one(failed_job.model_dump())

    yield client, admin_token, viewer_token, admin, viewer, pending_user, mock_db
    app.dependency_overrides.clear()


def test_admin_endpoints_require_admin_role(admin_api_env):
    client, _, viewer_token, _, _, _, _ = admin_api_env
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # Viewer accessing admin users
    resp1 = client.get("/api/admin/users", headers=viewer_headers)
    assert resp1.status_code == 403
    assert resp1.json()["error"]["code"] == "FORBIDDEN"

    # Viewer accessing source health
    resp2 = client.get("/api/admin/sources/health", headers=viewer_headers)
    assert resp2.status_code == 403

    # Viewer accessing jobs
    resp3 = client.get("/api/admin/jobs", headers=viewer_headers)
    assert resp3.status_code == 403

    # Viewer accessing audit logs
    resp4 = client.get("/api/admin/audit-logs", headers=viewer_headers)
    assert resp4.status_code == 403


def test_user_approval_and_role_management(admin_api_env):
    client, admin_token, _, _, _, pending_user, _ = admin_api_env
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Approve pending user
    resp_approve = client.patch(
        f"/api/admin/users/{pending_user.user_id}/status",
        headers=headers,
        json={"status": UserStatus.ACTIVE.value},
    )
    assert resp_approve.status_code == 200
    assert resp_approve.json()["status"] == UserStatus.ACTIVE.value

    # 2. Promote to Analyst
    resp_role = client.patch(
        f"/api/admin/users/{pending_user.user_id}/role",
        headers=headers,
        json={"role": Role.ANALYST.value},
    )
    assert resp_role.status_code == 200
    assert resp_role.json()["role"] == Role.ANALYST.value


def test_last_admin_guard_blocks_demoting_only_active_admin(admin_api_env):
    client, admin_token, _, admin, _, _, _ = admin_api_env
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Try to demote the only admin
    resp = client.patch(
        f"/api/admin/users/{admin.user_id}/role",
        headers=headers,
        json={"role": Role.VIEWER.value},
    )
    assert resp.status_code == 400
    assert "last remaining active administrator" in resp.json()["detail"]

    # Try to disable the only admin
    resp_disable = client.patch(
        f"/api/admin/users/{admin.user_id}/status",
        headers=headers,
        json={"status": UserStatus.DISABLED.value},
    )
    assert resp_disable.status_code == 400
    assert "last remaining active administrator" in resp_disable.json()["detail"]


def test_sources_health_and_toggle(admin_api_env):
    client, admin_token, _, _, _, _, _ = admin_api_env
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Health summary
    resp_health = client.get("/api/admin/sources/health", headers=headers)
    assert resp_health.status_code == 200
    health_list = resp_health.json()
    assert len(health_list) >= 1
    src_item = next(item for item in health_list if item["source_id"] == "aljazeera_ar")
    assert src_item["failed_jobs_count"] == 1
    assert "Network timeout" in src_item["recent_error"]
    assert src_item["enabled"] is False

    # Toggle source to enabled
    resp_toggle = client.patch(
        "/api/admin/sources/aljazeera_ar/toggle",
        headers=headers,
        json={"enabled": True},
    )
    assert resp_toggle.status_code == 200
    assert resp_toggle.json()["enabled"] is True


def test_jobs_inspection_retry_and_cancellation(admin_api_env):
    client, admin_token, _, _, _, _, _ = admin_api_env
    headers = {"Authorization": f"Bearer {admin_token}"}

    # List jobs & verify failure inspection
    resp_jobs = client.get("/api/admin/jobs", headers=headers)
    assert resp_jobs.status_code == 200
    data = resp_jobs.json()
    assert len(data["jobs"]) == 1
    assert data["stats"]["failed"] == 1
    assert data["jobs"][0]["job_id"] == "job-fail-1"

    # Scoped retry of failed job
    resp_retry = client.post("/api/admin/jobs/job-fail-1/retry", headers=headers)
    assert resp_retry.status_code == 200
    retried_job = resp_retry.json()
    assert retried_job["status"] == "pending"
    assert retried_job["error"] is None
    assert retried_job["attempts"] == 0

    # Cancel job
    resp_cancel = client.post("/api/admin/jobs/job-fail-1/cancel", headers=headers)
    assert resp_cancel.status_code == 200
    assert "cancelled" in resp_cancel.json()["message"]

    # Trigger new ingestion job
    resp_trigger = client.post(
        "/api/admin/jobs/trigger",
        headers=headers,
        json={"source_id": "aljazeera_ar", "limit": 15},
    )
    assert resp_trigger.status_code == 201
    assert resp_trigger.json()["kind"] == "ingest_source"


def test_audit_logs_trail(admin_api_env):
    client, admin_token, _, _, _, _, _ = admin_api_env
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Toggle source to trigger an audit entry
    client.patch(
        "/api/admin/sources/aljazeera_ar/toggle",
        headers=headers,
        json={"enabled": True},
    )

    # Read audit trail
    resp_audit = client.get("/api/admin/audit-logs", headers=headers)
    assert resp_audit.status_code == 200
    logs = resp_audit.json()
    assert len(logs) >= 1
    latest = logs[0]
    assert latest["action"] == "toggle_source"
    assert latest["entity_id"] == "aljazeera_ar"
    assert latest["details"]["enabled"] is True
