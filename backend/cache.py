import os
import json
import logging
import redis
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("cache")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

ALERTS_CACHE_TTL = int(os.getenv("ALERTS_CACHE_TTL_SECONDS", 3))
HISTORY_CACHE_TTL = int(os.getenv("HISTORY_CACHE_TTL_SECONDS", 15))


def get_cached(key: str):
    try:
        val = r.get(key)
        return json.loads(val) if val else None
    except redis.RedisError as exc:
        logger.warning(f"[cache] Redis indisponible (get_cached, key={key}): {exc}")
        return None


def set_cached(key: str, value, ttl: int = ALERTS_CACHE_TTL):
    try:
        r.setex(key, ttl, json.dumps(value))
    except redis.RedisError as exc:
        logger.warning(f"[cache] Redis indisponible (set_cached, key={key}): {exc}")


def invalidate_prefix(prefix: str):
    try:
        for k in r.scan_iter(f"{prefix}*"):
            r.delete(k)
    except redis.RedisError as exc:
        logger.warning(f"[cache] Redis indisponible (invalidate_prefix, prefix={prefix}): {exc}")


def get_multi(keys: list[str]) -> dict:
    if not keys:
        return {}
    try:
        values = r.mget(keys)
        return {k: json.loads(v) for k, v in zip(keys, values) if v is not None}
    except redis.RedisError as exc:
        logger.warning(f"[cache] Redis indisponible (get_multi): {exc}")
        return {}


def set_multi(items: dict, ttl: int = ALERTS_CACHE_TTL):
    try:
        pipe = r.pipeline()
        for key, value in items.items():
            pipe.setex(key, ttl, json.dumps(value))
        pipe.execute()
    except redis.RedisError as exc:
        logger.warning(f"[cache] Redis indisponible (set_multi): {exc}")