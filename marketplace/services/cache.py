"""
Redis cache for query embeddings and LLM explanations.

Values are stored in a language-neutral format on purpose (raw little-endian
float32 for vectors, UTF-8 for text), so a non-Python service can read the
same keys later. pgvector stores float32 anyway, so nothing is lost.

Every Redis error is swallowed and logged: a cache problem must never fail
a search. With REDIS_URL unset the cache is simply disabled.
"""

import hashlib
import logging
import re
import struct
import unicodedata

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

EMBEDDING_PREFIX = "emb:v1:"
EXPLANATION_PREFIX = "expl:v1:"

# Bump when the query text format sent to the embedding model changes.
QUERY_PROMPT_VERSION = "q1"

_clients = {}
_WHITESPACE = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    """NFKC-normalize, lowercase, trim and collapse whitespace."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", query).lower()).strip()


def _client():
    url = getattr(settings, "REDIS_URL", "")
    if not url:
        return None
    if url not in _clients:
        # Short timeouts: if Redis is down a search loses ~200 ms, not seconds.
        _clients[url] = redis.Redis.from_url(
            url, socket_connect_timeout=0.2, socket_timeout=0.2
        )
    return _clients[url]


def _hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def embedding_key(query: str, model: str, dims: int) -> str:
    return EMBEDDING_PREFIX + _hash(model, str(dims), QUERY_PROMPT_VERSION, normalize_query(query))


def explanation_key(query: str, model: str, app_ids) -> str:
    ids = ",".join(str(i) for i in sorted(app_ids))
    return EXPLANATION_PREFIX + _hash(model, normalize_query(query), ids)


def _get(key):
    client = _client()
    if client is None:
        return None
    try:
        return client.get(key)
    except redis.RedisError:
        logger.warning("Redis unavailable on get; continuing without cache")
        return None


def _set(key, value, ttl):
    client = _client()
    if client is None:
        return
    try:
        client.set(key, value, ex=ttl)
    except redis.RedisError:
        logger.warning("Redis unavailable on set; skipping cache write")


def get_embedding(key):
    raw = _get(key)
    if raw is None:
        return None
    return list(struct.unpack(f"<{len(raw) // 4}f", raw))


def set_embedding(key, vector, ttl):
    _set(key, struct.pack(f"<{len(vector)}f", *vector), ttl)


def get_text(key):
    raw = _get(key)
    return raw.decode("utf-8") if raw is not None else None


def set_text(key, text, ttl):
    _set(key, text.encode("utf-8"), ttl)


def ping() -> str:
    """Return "ok", "degraded" (configured but unreachable) or "disabled"."""
    client = _client()
    if client is None:
        return "disabled"
    try:
        client.ping()
        return "ok"
    except redis.RedisError:
        return "degraded"
