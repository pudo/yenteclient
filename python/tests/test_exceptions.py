"""Tests for the YenteError hierarchy."""

from yente_client.exceptions import (
    APIError,
    AuthenticationError,
    BadRequestError,
    ConfigurationError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TransportError,
    YenteError,
)


def test_hierarchy() -> None:
    # Every error inherits from YenteError so callers can catch broadly.
    for cls in (
        ConfigurationError,
        TransportError,
        APIError,
        BadRequestError,
        AuthenticationError,
        NotFoundError,
        RateLimitError,
        ServerError,
    ):
        assert issubclass(cls, YenteError)
    for cls in (BadRequestError, AuthenticationError, NotFoundError, RateLimitError, ServerError):
        assert issubclass(cls, APIError)


def test_api_error_carries_status_and_detail() -> None:
    e = APIError(404, "Entity not found")
    assert e.status_code == 404
    assert e.detail == "Entity not found"
    assert "404" in str(e)
    assert "Entity not found" in str(e)


def test_rate_limit_error_carries_retry_after() -> None:
    e = RateLimitError(429, "Too many requests", retry_after=30.0)
    assert e.status_code == 429
    assert e.retry_after == 30.0


def test_rate_limit_error_without_retry_after() -> None:
    e = RateLimitError(429, "Too many requests")
    assert e.retry_after is None
