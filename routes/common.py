from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

from models.schemas import Profile


def oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404)


async def get_profile(db) -> Profile:
    doc = await db.settings.find_one({"_id": "profile"}) or {}
    doc.pop("_id", None)
    return Profile(**doc)


async def unique_slug(collection, base: str, exclude_id: ObjectId | None = None) -> str:
    slug, n = base, 2
    while True:
        query: dict = {"slug": slug}
        if exclude_id:
            query["_id"] = {"$ne": exclude_id}
        if not await collection.find_one(query, {"_id": 1}):
            return slug
        slug = f"{base}-{n}"
        n += 1
