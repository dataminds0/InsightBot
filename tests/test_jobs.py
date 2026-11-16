from datetime import datetime, timedelta, timezone

import mongomock
import pytest

from insightbot.models.job import JobStatus
from insightbot.repositories.job_repository import JobRepository, StaleWorkerCommitError


@pytest.fixture
def job_repo():
    client = mongomock.MongoClient()
    db = client["test_jobs_db"]
    return JobRepository(db)


def test_create_job_is_idempotent(job_repo):
    job1 = job_repo.create_job(kind="ingest_source", target_id="aljazeera_ar")
    assert job1.status == JobStatus.PENDING
    assert job1.fencing_token == 1

    # Attempting to queue the same job again returns existing job without duplicates
    job2 = job_repo.create_job(kind="ingest_source", target_id="aljazeera_ar")
    assert job2.job_id == job1.job_id

    # Exactly 1 job exists in database
    assert job_repo.jobs.count_documents({}) == 1


def test_atomic_job_claim(job_repo):
    job = job_repo.create_job(kind="ingest_source", target_id="bbc_en")

    claimed = job_repo.claim_next_job(worker_id="worker_A", lease_duration=timedelta(minutes=5))
    assert claimed is not None
    assert claimed.job_id == job.job_id
    assert claimed.status == JobStatus.RUNNING
    assert claimed.lease_owner == "worker_A"
    assert claimed.fencing_token == 2  # incremented upon claim
    assert claimed.attempts == 1

    # Second worker cannot claim the same active job
    claimed_again = job_repo.claim_next_job(worker_id="worker_B")
    assert claimed_again is None


def test_reclaimed_worker_rejects_late_commit(job_repo):
    """
    CRITICAL ACCEPTANCE GATE:
    If Worker A's lease expires and Worker B reclaims the job, Worker A's subsequent
    commit attempt MUST be rejected by fencing token validation.
    """
    job = job_repo.create_job(kind="extract_article", target_id="art_123")

    # Worker A claims job with a very short lease (simulating expiration)
    claimed_a = job_repo.claim_next_job(worker_id="worker_A", lease_duration=timedelta(seconds=1))
    assert claimed_a is not None
    assert claimed_a.fencing_token == 2
    token_a = claimed_a.fencing_token

    # Simulate lease expiration in database
    past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
    job_repo.jobs.update_one({"job_id": job.job_id}, {"$set": {"lease_expires_at": past_time}})

    # Worker B comes in and reclaims the expired job!
    claimed_b = job_repo.claim_next_job(worker_id="worker_B", lease_duration=timedelta(minutes=5))
    assert claimed_b is not None
    assert claimed_b.job_id == job.job_id
    assert claimed_b.lease_owner == "worker_B"
    assert claimed_b.fencing_token == 3  # Fencing token advanced!

    # Worker A finally wakes up and attempts to commit with stale token 2
    with pytest.raises(StaleWorkerCommitError) as exc_info:
        job_repo.commit_job(
            job_id=job.job_id,
            worker_id="worker_A",
            fencing_token=token_a,
            result_data={"text": "Late result from worker A"},
        )
    assert "lease was reclaimed" in str(exc_info.value)

    # Worker B successfully commits with token 3
    completed = job_repo.commit_job(
        job_id=job.job_id,
        worker_id="worker_B",
        fencing_token=claimed_b.fencing_token,
        result_data={"text": "Valid result from worker B"},
    )
    assert completed.status == JobStatus.COMPLETED
    assert completed.result_data["text"] == "Valid result from worker B"


def test_job_failure_and_retry(job_repo):
    job = job_repo.create_job(kind="ingest_source", target_id="source_fail", max_attempts=2)
    claimed1 = job_repo.claim_next_job("worker_1")
    assert claimed1 is not None

    # First failure should reset status to PENDING for retry
    job_repo.fail_job(claimed1.job_id, "worker_1", claimed1.fencing_token, "Network timeout 1")
    job_after_fail1 = job_repo.get_by_id(job.job_id)
    assert job_after_fail1.status == JobStatus.PENDING
    assert job_after_fail1.attempts == 1

    # Second claim and failure should mark as FAILED (attempts >= max_attempts)
    claimed2 = job_repo.claim_next_job("worker_2")
    assert claimed2 is not None
    job_repo.fail_job(claimed2.job_id, "worker_2", claimed2.fencing_token, "Network timeout 2")
    job_after_fail2 = job_repo.get_by_id(job.job_id)
    assert job_after_fail2.status == JobStatus.FAILED
    assert job_after_fail2.attempts == 2


def test_cancel_job(job_repo):
    job = job_repo.create_job(kind="ingest_source", target_id="cancel_target")
    assert job_repo.cancel_job(job.job_id) is True
    cancelled = job_repo.get_by_id(job.job_id)
    assert cancelled.status == JobStatus.CANCELLED
