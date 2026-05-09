"""
Query cache with TTL for DataPulse.

Reduces redundant MCP/ES calls by caching frequent queries.
Uses layered caching: in-memory (fast) → optional Redis (shared).
"""

import asyncio
import functools
import json
import logging
import time
from typing import Any, Callable, Optional, TypeVar, Union, overload

from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheEntry:
    """A single cached value with TTL."""

    def __init__(self, value: Any, ttl_seconds: int):
        self.value = value
        self.created_at = time.monotonic()
        self.ttl_seconds = ttl_seconds

    @property
    def is_expired(self) -> bool:
        return time.monotonic() - self.created_at > self.ttl_seconds

    def get(self) -> Optional[Any]:
        return None if self.is_expired else self.value


class TTLCache:
    """Thread-safe in-memory TTL cache."""

    def __init__(self, default_ttl: int = 300):
        self._cache: dict = {}
        self._lock = asyncio.Lock()
        self.default_ttl = default_ttl

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            value = entry.get()
            if value is None:
                del self._cache[key]
            return value

    async def set(self, key: str, value: Any, ttl: int = None) -> None:
        async with self._lock:
            self._cache[key] = CacheEntry(value, ttl or self.default_ttl)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def keys(self) -> list:
        async with self._lock:
            return list(self._cache.keys())

    async def size(self) -> int:
        async with self._lock:
            return len(self._cache)


class RedisCache:
    """Redis-backed cache for shared/deployed environments."""

    def __init__(self, redis_url: str, default_ttl: int = 300):
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self._client = None
        self._lock = asyncio.Lock()

    async def _get_client(self):
        if self._client is None:
            try:
                import redis.asyncio as redis
                self._client = redis.from_url(self.redis_url, decode_responses=True)
            except ImportError:
                logger.warning("redis[asyncio] not installed — falling back to in-memory cache")
                self._client = False
            except Exception as e:
                logger.warning(f"Redis connection failed: {e} — using in-memory cache")
                self._client = False
        if self._client is False:
            return None
        return self._client

    async def get(self, key: str) -> Optional[Any]:
        client = await self._get_client()
        if not client:
            return None
        async with self._lock:
            try:
                data = await client.get(f"dp:cache:{key}")
                return json.loads(data) if data else None
            except Exception as e:
                logger.debug(f"Redis get failed: {e}")
                return None

    async def set(self, key: str, value: Any, ttl: int = None) -> None:
        client = await self._get_client()
        if not client:
            return
        async with self._lock:
            try:
                await client.set(
                    f"dp:cache:{key}", json.dumps(value), ex=ttl or self.default_ttl
                )
            except Exception as e:
                logger.debug(f"Redis set failed: {e}")

    async def delete(self, key: str) -> None:
        client = await self._get_client()
        if not client:
            return
        async with self._lock:
            try:
                await client.delete(f"dp:cache:{key}")
            except Exception:
                pass

    async def clear(self) -> None:
        client = await self._get_client()
        if not client:
            return
        async with self._lock:
            try:
                keys = await client.keys("dp:cache:*")
                if keys:
                    await client.delete(*keys)
            except Exception:
                pass


# Global cache instances
_in_memory_cache = TTLCache(default_ttl=settings.CACHE_TTL_SECONDS)
_redis_cache = None


async def get_cache() -> TTLCache:
    """Get the primary in-memory cache (always available)."""
    return _in_memory_cache


async def get_redis_cache() -> Optional[RedisCache]:
    """Get Redis cache if enabled and available."""
    global _redis_cache
    if not settings.CACHE_ENABLED:
        return None
    if _redis_cache is None and settings.REDIS_URL and settings.REDIS_URL != "redis://localhost:6379":
        _redis_cache = RedisCache(settings.REDIS_URL, settings.CACHE_TTL_SECONDS)
    return _redis_cache


# Type variable for decorator return
F = TypeVar("F", bound=Callable)


def cached(key_prefix: str, ttl: int = None, skip_cache: bool = False):
    """
    Decorator to cache async function results.

    Works with both sync and async functions by detecting the function type.

    Usage:
        @cached("health_overview", ttl=60)
        async def get_health_overview():
            ...
    """
    def decorator(func: F) -> F:
        import inspect

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                cache_key = f"{key_prefix}:{hash(str(args) + str(kwargs)) % 10000}"

                if not skip_cache and settings.CACHE_ENABLED:
                    # Try in-memory cache first
                    cached_val = await _in_memory_cache.get(cache_key)
                    if cached_val is not None:
                        logger.debug(f"Cache hit: {cache_key}")
                        return cached_val

                    # Try Redis cache
                    redis_cache = await get_redis_cache()
                    if redis_cache:
                        cached_val = await redis_cache.get(cache_key)
                        if cached_val is not None:
                            await _in_memory_cache.set(cache_key, cached_val, ttl)
                            logger.debug(f"Redis cache hit: {cache_key}")
                            return cached_val

                # Execute function
                result = await func(*args, **kwargs)

                # Cache the result
                if settings.CACHE_ENABLED:
                    effective_ttl = ttl if ttl is not None else settings.CACHE_TTL_SECONDS
                    await _in_memory_cache.set(cache_key, result, effective_ttl)
                    redis_cache = await get_redis_cache()
                    if redis_cache:
                        await redis_cache.set(cache_key, result, effective_ttl)

                return result
            return async_wrapper  # type: ignore
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                cache_key = f"{key_prefix}:{hash(str(args) + str(kwargs)) % 10000}"

                if not skip_cache and settings.CACHE_ENABLED:
                    cached_val = asyncio.get_event_loop().run_until_complete(
                        _in_memory_cache.get(cache_key)
                    ) if asyncio.get_event_loop().is_running() else None

                    if cached_val is not None:
                        logger.debug(f"Cache hit: {cache_key}")
                        return cached_val

                # Execute function
                result = func(*args, **kwargs)

                # Cache the result (skip for sync in async context)
                return result
            return sync_wrapper  # type: ignore

    return decorator


async def invalidate_cache(key_prefix: str) -> int:
    """Invalidate all cache entries matching a key prefix. Returns count invalidated."""
    count = 0
    keys = await _in_memory_cache.keys()
    for key in keys:
        if key.startswith(key_prefix):
            await _in_memory_cache.delete(key)
            count += 1
    return count


async def warm_cache(func, *args, key_prefix: str = "", ttl: int = None, **kwargs):
    """Pre-warm cache by executing a function and caching the result."""
    result = await func(*args, **kwargs)
    cache_key = f"{key_prefix}:{hash(str(args) + str(kwargs)) % 10000}"
    await _in_memory_cache.set(cache_key, result, ttl or settings.CACHE_TTL_SECONDS)
    return result