"""Agent chat API routes for embedded server."""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.agents.runner import AgentRunner, RunResult
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import ChatMessage, ChatSession
from autonomous_agent_builder.db.session import get_db

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class MessageItem(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str


class ChatResponse(BaseModel):
    response: str
    session_id: str
    status: dict | None = None


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[MessageItem]


@router.get("/agent/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get chat history for a session.
    If no session_id provided, returns empty history.
    """
    if not session_id:
        return ChatHistoryResponse(session_id="", messages=[])
    
    # Load session with messages
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.messages))
    )
    session = result.scalar_one_or_none()
    
    if not session:
        return ChatHistoryResponse(session_id="", messages=[])
    
    messages = [
        MessageItem(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            timestamp=msg.created_at.isoformat(),
        )
        for msg in session.messages
    ]
    
    return ChatHistoryResponse(session_id=session.id, messages=messages)


@router.post("/agent/chat", response_model=ChatResponse)
async def agent_chat(
    request: ChatRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Chat with the Claude SDK agent.
    
    This endpoint accepts a user message and returns the agent's response.
    Uses a general-purpose chat agent with access to project context.
    Persists conversation history to database.
    """
    try:
        settings = get_settings()
        runner = AgentRunner(settings)
        
        # Get or create chat session
        if request.session_id:
            result = await db.execute(
                select(ChatSession).where(ChatSession.id == request.session_id)
            )
            session = result.scalar_one_or_none()
            if not session:
                session = ChatSession()
                db.add(session)
                await db.flush()  # Flush to get the session ID
        else:
            session = ChatSession()
            db.add(session)
            await db.flush()  # Flush to get the session ID
        
        # Save user message
        user_message = ChatMessage(
            session_id=session.id,
            role="user",
            content=request.message,
        )
        db.add(user_message)
        await db.commit()
        
        # Get project root from app state
        project_root = str(req.app.state.project_root)
        
        # Build prompt using the chat agent template
        prompt = f"""You are a helpful AI assistant for the autonomous-agent-builder project.

You have access to the project files and can help users:
- Understand the codebase structure and architecture
- Answer questions about specific files or components
- Provide guidance on development tasks
- Search through project knowledge and memory

Use Read/Glob/Grep to explore the codebase when needed.
Use builder_kb_search to find relevant documentation.
Use builder_memory_search to recall past decisions.

Project root: {project_root}

User: {request.message}"""
        
        # Run the chat agent
        result: RunResult = await runner.run_phase(
            agent_name="chat",
            prompt=prompt,
            workspace_path=project_root,
            resume_session=session.sdk_session_id,
        )
        
        if result.error:
            # Save error message
            error_message = ChatMessage(
                session_id=session.id,
                role="assistant",
                content=f"Error: {result.error}",
            )
            db.add(error_message)
            await db.commit()
            raise HTTPException(status_code=500, detail=result.error)
        
        # Update session with SDK session ID
        if result.session_id:
            session.sdk_session_id = result.session_id
        
        # Save assistant response
        assistant_message = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=result.output_text or "No response from agent",
            tokens_used=result.tokens_input + result.tokens_output,
            cost_usd=result.cost_usd,
        )
        db.add(assistant_message)
        await db.commit()
        
        status = {
            "running": False,
            "current_turn": result.num_turns,
            "max_turns": settings.agent.max_turns,
            "tokens_used": result.tokens_input + result.tokens_output,
            "cost_usd": result.cost_usd,
        }
        
        return ChatResponse(
            response=result.output_text or "No response from agent",
            session_id=session.id,
            status=status,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


