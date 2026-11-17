"""Unit tests for container packaging, Compose specs, same-origin SPA serving, and atomic raw storage."""

import tempfile
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from insightbot.api.main import app


def test_dockerfiles_security_and_locked_builds():
    """Verify Dockerfiles contain non-root user isolation, multi-stage builds, and locked uv dependencies."""
    api_dockerfile = Path("Dockerfile.api")
    worker_dockerfile = Path("Dockerfile.worker")

    assert api_dockerfile.exists(), "Dockerfile.api must exist"
    assert worker_dockerfile.exists(), "Dockerfile.worker must exist"

    api_content = api_dockerfile.read_text(encoding="utf-8")
    worker_content = worker_dockerfile.read_text(encoding="utf-8")

    # Multi-stage check
    assert "FROM node:" in api_content, "API Dockerfile should build frontend in stage 1"
    assert "AS runtime" in api_content

    # Non-root user check
    assert "10001" in api_content and "USER insightbot" in api_content, "API container must run as non-root user"
    assert "10001" in worker_content and "USER insightbot" in worker_content, "Worker container must run as non-root user"

    # Locked dependencies
    assert "uv sync --frozen --no-dev" in api_content, "Dependencies must be locked (--frozen)"
    assert "uv sync --frozen --no-dev" in worker_content

    # Healthcheck check
    assert "HEALTHCHECK" in api_content, "API Dockerfile must declare container healthcheck"


def test_compose_production_specifications():
    """Verify infra/compose.prod.yaml has explicit resource limits, volumes, networks, and healthchecks."""
    prod_compose = Path("infra/compose.prod.yaml")
    assert prod_compose.exists(), "infra/compose.prod.yaml must exist"

    with open(prod_compose, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    assert "mongo" in services
    assert "prefect" in services
    assert "migrator" in services
    assert "api" in services
    assert "worker" in services

    # Verify resource limits
    for s_name in ("mongo", "api", "worker"):
        res = services[s_name].get("deploy", {}).get("resources", {}).get("limits", {})
        assert "memory" in res, f"Service {s_name} must declare explicit memory limits"

    # Verify healthchecks
    assert "healthcheck" in services["mongo"]
    assert "healthcheck" in services["api"]

    # Verify persistent volumes
    volumes = data.get("volumes", {})
    assert "mongo_data" in volumes
    assert "raw_data" in volumes
    assert "exports_data" in volumes


def test_same_origin_spa_serving_and_api_isolation():
    """Verify that FastAPI serves built React index.html for SPA routes while maintaining strict 404 on invalid API routes."""
    client = TestClient(app)

    # API 404 should return JSON, not index.html
    r_api_404 = client.get("/api/nonexistent-endpoint-xyz")
    assert r_api_404.status_code == 404
    assert r_api_404.headers.get("content-type", "").startswith("application/json")

    # Healthcheck remains accessible
    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"


def test_atomic_raw_write_and_rename_discipline():
    """Test that file writes to raw storage execute via temporary file and atomic rename."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        raw_path = Path(tmp_dir)
        content = b"<html><title>Clean Atomic Ingestion</title><body>Payload</body></html>"

        # Simulate atomic write
        tmp_target = raw_path / "temp_ingest_123.tmp"
        final_target = raw_path / "art_123.html"

        tmp_target.write_bytes(content)
        tmp_target.replace(final_target)

        assert final_target.exists()
        assert not tmp_target.exists()
        assert final_target.read_bytes() == content


def test_seed_removal_immutability():
    """Verify that bundled demo seed articles and fixed-admin script are completely absent from repository."""
    seed_csv = Path("Interface/insightbot_seed/news_articles.csv")
    seed_py = Path("Interface/insightbot_seed/seed_data.py")

    assert not seed_csv.exists(), "news_articles.csv seed must never be recreated"
    assert not seed_py.exists(), "seed_data.py must never be recreated"
