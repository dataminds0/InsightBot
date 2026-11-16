"""MongoDB client connection helpers."""

import logging
from typing import Any

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from insightbot.config import Settings

logger = logging.getLogger(__name__)


def get_mongo_client(settings: Settings) -> MongoClient[dict[str, Any]]:
    """Create and return a configured MongoClient instance."""
    return MongoClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=settings.mongo_timeout_ms,
        connectTimeoutMS=settings.mongo_timeout_ms,
        socketTimeoutMS=settings.mongo_timeout_ms,
    )


def check_mongo_connection(settings: Settings) -> tuple[bool, str]:
    """Test connectivity to MongoDB server by issuing a ping command."""
    client = get_mongo_client(settings)
    try:
        client.admin.command("ping")
        return True, "MongoDB connection established successfully."
    except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
        return False, f"Could not connect to MongoDB at '{settings.mongo_uri}': {exc}"
    except Exception as exc:
        return False, f"Unexpected error checking MongoDB connection: {exc}"
    finally:
        client.close()
