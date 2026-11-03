"""MongoDB access via PyMongo's native async client.

The client is created lazily and reused across invocations of a warm
serverless instance. Indexes are ensured once per process.
"""
import asyncio

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from core.config import get_settings

_client: AsyncMongoClient | None = None
_indexes_ready = False
_index_lock = asyncio.Lock()


def _get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        _client = AsyncMongoClient(
            get_settings().mongo_uri,
            serverSelectionTimeoutMS=8000,
            maxPoolSize=10,
            tz_aware=True,
        )
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
        async with _index_lock:
            if not _indexes_ready:
                await _ensure_indexes(db)
                _indexes_ready = True
    return db
