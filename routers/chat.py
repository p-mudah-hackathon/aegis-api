"""
Chat router — multi-turn AI conversation about fraud transactions.

Endpoints:
  POST /api/v1/chat/start         — Start a new chat about a transaction
  POST /api/v1/chat/{chat_id}     — Send a follow-up message
  GET  /api/v1/chat/{chat_id}     — Get full chat history
  GET  /api/v1/chat               — List all chat sessions
  DELETE /api/v1/chat/{chat_id}   — Delete a chat session
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from database import get_db
from models import ChatSession, ChatMessage
from schemas.chat import (
    StartChatRequest, SendMessageRequest,
    ChatMessageOut, ChatSessionOut, ChatDetailOut, ChatReplyOut,
)
from services import chat_service
from errors import NotFoundError

router = APIRouter(prefix="/api/v1/chat", tags=["AI Chat"])


@router.post(
    "/start",
    response_model=ChatReplyOut,
    summary="Start a new AI chat about a transaction",
    description=(
        "Creates a new chat session linked to a transaction. "
        "The AI receives the full transaction context (risk score, XAI features, fraud type, etc.) "
        "and responds with an initial analysis. You can optionally include a first message."
    ),
)
async def start_chat(req: StartChatRequest, db: AsyncSession = Depends(get_db)):
    """Start a new chat about a flagged transaction."""
    try:
        session, ai_msg = await chat_service.start_chat(
            txn_id=req.txn_id,
            user_message=req.message,
            db=db,
        )
    except ValueError as e:
        raise NotFoundError("Transaction", req.txn_id)

    # Count messages
    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == session.chat_id)
        .where(ChatMessage.role != "system")
    )
    total = len(msg_result.scalars().all())

    return ChatReplyOut(
        chat_id=session.chat_id,
        message=ChatMessageOut.model_validate(ai_msg),
        total_messages=total,
    )


@router.post(
    "/{chat_id}",
    response_model=ChatReplyOut,
    summary="Send a message in an existing chat",
    description=(
        "Send a follow-up message. The AI receives the FULL conversation history "
        "(all previous messages) for context, just like ChatGPT."
    ),
)
async def send_message(
    chat_id: str,
    req: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a follow-up message and get AI response."""
    try:
        session, ai_msg = await chat_service.send_message(
            chat_id=chat_id,
            user_message=req.message,
            db=db,
        )
    except ValueError:
        raise NotFoundError("Chat session", chat_id)

    # Count messages
    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == chat_id)
        .where(ChatMessage.role != "system")
    )
    total = len(msg_result.scalars().all())

    return ChatReplyOut(
        chat_id=chat_id,
        message=ChatMessageOut.model_validate(ai_msg),
        total_messages=total,
    )


@router.get(
    "",
    response_model=List[ChatSessionOut],
    summary="List all chat sessions",
)
async def list_chats(
    txn_id: Optional[str] = Query(None, description="Filter by transaction ID"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List chat sessions, newest first. Optionally filter by transaction."""
    chats = await chat_service.list_chats(txn_id=txn_id, limit=limit, db=db)
    return [ChatSessionOut(**c) for c in chats]


@router.get(
    "/{chat_id}",
    response_model=ChatDetailOut,
    summary="Get full chat history",
    description="Returns all messages in a chat session (excluding system prompt).",
)
async def get_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    """Get full chat session with all messages."""
    try:
        session, messages = await chat_service.get_chat_history(
            chat_id=chat_id, db=db,
        )
    except ValueError:
        raise NotFoundError("Chat session", chat_id)

    return ChatDetailOut(
        chat_id=session.chat_id,
        txn_id=session.txn_id,
        title=session.title,
        messages=[ChatMessageOut.model_validate(m) for m in messages],
        created_at=session.created_at,
    )


@router.delete(
    "/{chat_id}",
    summary="Delete a chat session",
)
async def delete_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a chat session and all its messages."""
    # Check exists
    result = await db.execute(
        select(ChatSession).where(ChatSession.chat_id == chat_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError("Chat session", chat_id)

    # Delete messages first, then session
    await db.execute(
        delete(ChatMessage).where(ChatMessage.chat_id == chat_id)
    )
    await db.delete(session)
    await db.commit()

    return {"status": "deleted", "chat_id": chat_id}
