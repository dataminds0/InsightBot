"""Main server and process entrypoint for background flows and workers."""

import logging
import signal
import sys
import time
from typing import Any

from insightbot.config import get_settings
from insightbot.flows.worker import WorkerService
from insightbot.infra.mongo import check_mongo_connection, get_mongo_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("insightbot.flows.serve")

_keep_running = True


def _handle_signal(sig: int, frame: Any) -> None:
    global _keep_running
    logger.info("Received termination signal %d. Shutting down worker gracefully...", sig)
    _keep_running = False


def serve_worker() -> None:
    """Run worker process loop processing pending jobs."""
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    settings = get_settings()
    logger.info("Starting InsightBot Background Worker...")

    ok, msg = check_mongo_connection(settings)
    if not ok:
        logger.error("Cannot connect to MongoDB: %s", msg)
        sys.exit(1)

    client = get_mongo_client(settings)
    db = client[settings.mongo_db]
    worker = WorkerService(db=db, settings=settings)

    logger.info("Worker '%s' online. Waiting for jobs...", worker.worker_id)

    try:
        while _keep_running:
            job = worker.process_one_job()
            if not job:
                time.sleep(2.0)
    finally:
        client.close()
        logger.info("Worker '%s' stopped cleanly.", worker.worker_id)


if __name__ == "__main__":
    serve_worker()
