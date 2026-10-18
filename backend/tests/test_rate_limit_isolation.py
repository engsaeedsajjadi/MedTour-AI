"""Regression tests: Docker's REDIS_URL must not make unit tests share login counters."""
import pytest
from fastapi import HTTPException
from redis import Redis
from app.rate_limit import throttle, _hits


def test_rate_limit_isolated_from_docker_redis_during_tests(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/99")

    def redis_must_not_be_used(*args, **kwargs):
        raise AssertionError("Tests must never contact shared Redis for login throttling")

    monkeypatch.setattr(Redis, "from_url", redis_must_not_be_used)
    _hits.clear()
    try:
        throttle("synthetic-user-login", limit=2)
        throttle("synthetic-user-login", limit=2)
        with pytest.raises(HTTPException) as caught:
            throttle("synthetic-user-login", limit=2)
        assert caught.value.status_code == 429
    finally:
        _hits.clear()


def test_production_rate_limit_stays_fail_closed_without_redis(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(HTTPException) as caught:
        throttle("synthetic-production-user")
    assert caught.value.status_code == 503
