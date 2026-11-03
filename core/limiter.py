from fastapi import Request
from slowapi import Limiter


def client_ip(request: Request) -> str:
    # Vercel sets x-forwarded-for; the first entry is the original client.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# In-memory storage is per serverless instance. For strict global limits,
# point storage_uri at Redis (e.g. Upstash): Limiter(..., storage_uri="redis://...").
limiter = Limiter(key_func=client_ip, default_limits=[])
