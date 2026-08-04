import os
import json
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.Redis.from_url(REDIS_URL, decode_responses=True, protocol=2)

ALERTS_CACHE_TTL = int(os.getenv("ALERTS_CACHE_TTL_SECONDS", 3))
HISTORY_CACHE_TTL = int(os.getenv("HISTORY_CACHE_TTL_SECONDS", 15))


def get_cached(key: str):
    val = r.get(key)
    return json.loads(val) if val else None


def set_cached(key: str, value, ttl: int = ALERTS_CACHE_TTL):
    r.setex(key, ttl, json.dumps(value))


def invalidate_prefix(prefix: str):
    for k in r.scan_iter(f"{prefix}*"):
        r.delete(k)

def get_multi(keys: list[str]) -> dict:
    if not keys:
        return {}
    values = r.mget(keys)
    return {k: json.loads(v) for k, v in zip(keys, values) if v is not None}


def set_multi(items: dict, ttl: int = ALERTS_CACHE_TTL):
    pipe = r.pipeline()
    for key, value in items.items():
        pipe.setex(key, ttl, json.dumps(value))
    pipe.execute()