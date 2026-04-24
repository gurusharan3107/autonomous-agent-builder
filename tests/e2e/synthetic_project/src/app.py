"""Synthetic app for e2e pipeline testing."""

from dataclasses import dataclass


@dataclass
class HealthResponse:
    """Health check response model."""

    status: str
    version: str


def greet(name: str) -> str:
    """Return a greeting message."""
    return f"Hello, {name}!"


def health_check() -> HealthResponse:
    """Return current health status."""
    return HealthResponse(status="ok", version="0.1.0")
