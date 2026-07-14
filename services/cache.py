"""Valkey cache read/write logic with IAM authentication."""

import hashlib
import json
from typing import Any

import boto3
import botocore.auth
import botocore.awsrequest
import redis
from redis.credentials import CredentialProvider

from config import settings
from utils.exceptions import CacheConnectionError
from utils.logging import get_logger

LOGGER = get_logger("services.cache")
_redis_client: redis.Redis | None = None


class RedisIamCredentialProvider(CredentialProvider):
    """Generate Redis IAM credentials for each new connection."""

    def __init__(self, host: str, port: int, cache_name: str, user_id: str, region: str) -> None:
        self.host = host
        self.port = port
        self.cache_name = cache_name
        self.user_id = user_id
        self.region = region

    def get_credentials(self) -> tuple[str, str]:
        """Return username and a fresh short-lived IAM auth token."""
        return (
            self.user_id,
            generate_iam_auth_token(
                self.host,
                self.port,
                self.cache_name,
                self.user_id,
                self.region,
            ),
        )


def generate_iam_auth_token(host: str, port: int, cache_name: str, user_id: str, region: str) -> str:
    """Generate a short-lived IAM token for ElastiCache Valkey."""
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise CacheConnectionError("AWS credentials are required for Redis IAM authentication.")
    request = botocore.awsrequest.AWSRequest(
        method="GET",
        url=f"https://{cache_name}/?Action=connect&User={user_id}",
    )
    signer = botocore.auth.SigV4QueryAuth(
        credentials.get_frozen_credentials(),
        "elasticache",
        region,
        expires=900,
    )
    signer.add_auth(request)
    return request.url.replace("https://", "", 1)


def init_cache(correlation_id: str = "startup") -> redis.Redis | None:
    """Initialise Valkey when its endpoint is configured."""
    global _redis_client
    if settings.REDIS_HOST.startswith("REPLACE_WITH"):
        LOGGER.warning("cache_not_configured", correlation_id=correlation_id)
        return None
    credential_provider = RedisIamCredentialProvider(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        cache_name=settings.REDIS_CACHE_NAME,
        user_id=settings.REDIS_USER,
        region=settings.AWS_REGION,
    )
    client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        credential_provider=credential_provider,
        ssl=True,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=2,
        retry_on_timeout=True,
    )
    try:
        client.ping()
    except redis.RedisError:
        client.close()
        raise
    _redis_client = client
    LOGGER.info("cache_initialized", correlation_id=correlation_id, host=settings.REDIS_HOST, user=settings.REDIS_USER)
    return _redis_client


def close_cache(correlation_id: str = "shutdown") -> None:
    """Close Redis connections during graceful shutdown."""
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None
        LOGGER.info("cache_closed", correlation_id=correlation_id)


def build_cache_key(message: str, country: str, language: str, role: str) -> str:
    """Build a versioned locale-aware SHA256 cache key."""
    versions = "|".join(
        [
            settings.CACHE_SCHEMA_VERSION,
            settings.KB_VERSION,
            settings.PROMPT_VERSION,
            settings.BEDROCK_GUARDRAIL_VERSION,
            settings.BEDROCK_MODEL_ARN,
        ]
    )
    digest = hashlib.sha256(f"{message}|{country}|{language}|{role}|{versions}".encode("utf-8")).hexdigest()
    return f"ask-vera:{country}:{language}:{role}:{digest}"


def get_cache_value(key: str, correlation_id: str) -> dict[str, Any] | None:
    """Read and decode a cached response."""
    if _redis_client is None:
        return None
    try:
        raw = _redis_client.get(key)
        LOGGER.info("cache_read", correlation_id=correlation_id, hit=bool(raw), key=key)
        return json.loads(raw) if raw else None
    except redis.RedisError as exc:
        LOGGER.exception("cache_read_failed", correlation_id=correlation_id)
        raise CacheConnectionError("Redis cache read failed.") from exc


def set_cache_value(key: str, value: dict[str, Any], correlation_id: str) -> None:
    """Write a response to Redis with the configured TTL."""
    if _redis_client is None:
        return
    try:
        _redis_client.setex(key, settings.CACHE_TTL_SECONDS, json.dumps(value))
        LOGGER.info("cache_write", correlation_id=correlation_id, key=key, ttl=settings.CACHE_TTL_SECONDS)
    except redis.RedisError as exc:
        LOGGER.exception("cache_write_failed", correlation_id=correlation_id)
        raise CacheConnectionError("Redis cache write failed.") from exc
