from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker
from sse_starlette.sse import EventSourceResponse

from autonomous_agent_builder.embedded.server.routes.dashboard import (
    approval_stream,
    board_stream,
)


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_embedded_board_stream_returns_sse_response(test_db):
    _, factory = test_db
    assert isinstance(factory, async_sessionmaker)

    async with factory() as db:
        response = await board_stream(_ConnectedRequest(), db)

    assert isinstance(response, EventSourceResponse)
    assert response.media_type == "text/event-stream"


@pytest.mark.asyncio
async def test_embedded_approval_stream_raises_404_for_unknown_gate(test_db):
    _, factory = test_db

    async with factory() as db:
        with pytest.raises(HTTPException) as exc:
            await approval_stream("missing-gate", _ConnectedRequest(), db)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Approval gate not found"
