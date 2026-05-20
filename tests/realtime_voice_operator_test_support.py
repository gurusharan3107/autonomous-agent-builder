"""Shared test doubles for Realtime voice operator route tests."""

from __future__ import annotations

from typing import Any


class FakeRealtimeResponse:
    status_code = 201
    text = "answer-sdp"
    headers = {"Location": "/v1/realtime/calls/rtc_test_call"}


class FakeAsyncClient:
    calls: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> FakeRealtimeResponse:
        self.calls.append({"url": url, **kwargs})
        return FakeRealtimeResponse()
