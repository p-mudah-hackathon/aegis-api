"""Pydantic schemas for the AI chat feature."""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class StartChatRequest(BaseModel):
    """Start a new chat session about a transaction."""
    txn_id: str = Field(..., description="Transaction ID to investigate", example="TXN-000042")
    message: Optional[str] = Field(
        None,
        description="Optional first user message. If empty, AI gives an initial analysis.",
        example="Why was this transaction flagged?",
    )


class SendMessageRequest(BaseModel):
    """Send a follow-up message in an existing chat."""
    message: str = Field(..., description="User message", example="What about the merchant history?")


class ChatMessageOut(BaseModel):
    """A single chat message."""
    seq: int
    role: str = Field(..., description="system | user | assistant")
    content: str
    reasoning: Optional[str] = Field(None, description="AI's chain-of-thought (thinking mode)")
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ChatSessionOut(BaseModel):
    """A chat session summary (for listing)."""
    chat_id: str
    txn_id: str
    title: Optional[str] = None
    message_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatDetailOut(BaseModel):
    """Full chat session with all messages."""
    chat_id: str
    txn_id: str
    title: Optional[str] = None
    messages: List[ChatMessageOut] = []
    created_at: Optional[datetime] = None


class ChatReplyOut(BaseModel):
    """Response from sending a message."""
    chat_id: str
    message: ChatMessageOut = Field(..., description="The AI's reply")
    total_messages: int
