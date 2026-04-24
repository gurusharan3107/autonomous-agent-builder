"""Tests for the synthetic app."""

from src.app import HealthResponse, greet, health_check


def test_health_response() -> None:
    resp = HealthResponse(status="ok", version="0.1.0")
    assert resp.status == "ok"
    assert resp.version == "0.1.0"


def test_greet() -> None:
    assert greet("World") == "Hello, World!"


def test_health_check() -> None:
    resp = health_check()
    assert resp.status == "ok"
