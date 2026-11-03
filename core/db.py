"""MongoDB access via PyMongo's native async client.

The client is created lazily and reused across invocations of a warm
serverless instance. Async clients are bound to the event loop they were
created on, and some serverless runtimes start a fresh loop per
invocation, so the client is rebuilt whenever the running loop changes.
Indexes are ensured once per process.
"""
import asyncio

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from core.config import get_settings

_client: AsyncMongoClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None
_indexes_ready = False


def _get_client() -> AsyncMongoClient:
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        # The old client's loop is gone; its sockets are released with it.
        _client = AsyncMongoClient(
            get_settings().mongo_uri,
            serverSelectionTimeoutMS=8000,
            maxPoolSize=10,
            tz_aware=True,
            appname="portfolio",
        )
        _client_loop = loop
    return _client


async def _ensure_indexes(db: AsyncDatabase) -> None:
    await db.users.create_index("email", unique=True)
    await db.projects.create_index("slug", unique=True)
    await db.projects.create_index([("status", ASCENDING), ("order", ASCENDING), ("created_at", DESCENDING)])
    await db.projects.create_index("tags")
    await db.posts.create_index("slug", unique=True)
    await db.posts.create_index([("status", ASCENDING), ("published_at", DESCENDING)])
    await db.posts.create_index("tags")
    await db.messages.create_index([("created_at", DESCENDING)])
    # Mongo removes expired OTP docs automatically.
    await db.otps.create_index("expires_at", expireAfterSeconds=0)
    await db.otps.create_index("email")


async def get_db() -> AsyncDatabase:
    global _indexes_ready
    db = _get_client()[get_settings().mongo_db_name]
    if not _indexes_ready:
        # create_index is idempotent, so a concurrent duplicate run is harmless.
        await _ensure_indexes(db)
        _indexes_ready = True
    return db


async def ping() -> bool:
    try:
        await _get_client().admin.command("ping")
        return True
    except Exception:
        return False
