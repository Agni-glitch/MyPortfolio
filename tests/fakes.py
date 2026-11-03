"""Minimal in-memory stand-in for the async PyMongo API used by the app."""
import copy
from types import SimpleNamespace

from bson import ObjectId


def _match(doc: dict, query: dict) -> bool:
    for key, cond in query.items():
        val = doc.get(key)
        if isinstance(cond, dict):
            if "$ne" in cond and val == cond["$ne"]:
                return False
            if "$in" in cond:
                vals = val if isinstance(val, list) else [val]
                if not set(vals) & set(cond["$in"]):
                    return False
        elif isinstance(val, list):
            if cond not in val:
                return False
        elif val != cond:
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        keys = [(key, direction)] if isinstance(key, str) else key
        for k, d in reversed(keys):
            self.docs.sort(key=lambda x: (x.get(k) is None, x.get(k) or 0), reverse=d == -1)
        return self

    def skip(self, n):
        self.docs = self.docs[n:]
        return self

    async def to_list(self, n=None):
        return self.docs[:n] if n else self.docs

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    async def create_index(self, *args, **kwargs):
        pass

    def find(self, query=None, projection=None):
        return FakeCursor([copy.deepcopy(d) for d in self.docs if _match(d, query or {})])

    async def find_one(self, query=None, projection=None):
        found = [d for d in self.docs if _match(d, query or {})]
        return copy.deepcopy(found[0]) if found else None

    async def count_documents(self, query):
        return sum(_match(d, query) for d in self.docs)

    async def distinct(self, field, query):
        out = set()
        for d in self.docs:
            if _match(d, query):
                v = d.get(field)
                out.update(v if isinstance(v, list) else [v])
        return list(out)

    async def insert_one(self, doc):
        doc = copy.deepcopy(doc)
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    async def replace_one(self, query, doc, upsert=False):
        for i, d in enumerate(self.docs):
            if _match(d, query):
                self.docs[i] = {"_id": d["_id"], **copy.deepcopy(doc)}
                return
        if upsert:
            await self.insert_one(doc)

    async def update_one(self, query, update):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                for k, n in update.get("$inc", {}).items():
                    d[k] = d.get(k, 0) + n
                return

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _match(d, query):
                del self.docs[i]
                return

    async def delete_many(self, query):
        self.docs = [d for d in self.docs if not _match(d, query)]

    async def find_one_and_delete(self, query):
        doc = await self.find_one(query)
        if doc:
            await self.delete_one({"_id": doc["_id"]})
        return doc


class FakeDB:
    def __init__(self):
        self._collections: dict[str, FakeCollection] = {}

    def __getattr__(self, name):
        return self._collections.setdefault(name, FakeCollection())
