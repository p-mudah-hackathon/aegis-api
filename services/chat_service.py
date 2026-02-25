"""
Chat service — multi-turn AI conversation about fraud transactions.

Each chat session:
  1. Is linked to a specific transaction (txn_id)
  2. Has a system prompt with full transaction context baked in
  3. Sends the FULL message history to Qwen on each turn (conversational memory)
  4. Persists all messages to DB for chat history
"""
import logging
import asyncio
from typing import List, Dict, Optional
from openai import OpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from config import settings
from models import Transaction, ChatSession, ChatMessage

logger = logging.getLogger("aegis.chat")

# ── System prompt for chat mode (richer than one-shot reasoning) ─────────────
CHAT_SYSTEM_PROMPT = """You are AegisNode Fraud Analyst — an AI assistant specialized in investigating flagged transactions.

## Your Capabilities
- Explain WHY a transaction was flagged by the HTGNN (Heterogeneous Temporal Graph Neural Network) model
- Analyze fraud patterns: velocity attacks, card testing, collusion rings, geo-anomalies, amount anomalies
- Interpret XAI (explainable AI) feature importance weights
- Suggest investigation steps for the analyst
- Answer follow-up questions about the transaction, merchant, payer patterns, etc.

## Model Context
- HTGNN operates on a bipartite payer↔merchant graph; each transaction is an edge
- Risk score ∈ [0, 1] — higher = more suspicious
- Feature importances from integrated gradients on edge features

## Your Style
- Be conversational but precise — cite actual values from the transaction
- When the analyst asks follow-up questions, build on your previous analysis
- If the user asks you anything out of scope (e.g., programming questions, general knowledge, asking you to write scripts or poems), politely refuse. You are strictly a fraud investigator handling this specific transaction ONLY. Do not act as a general-purpose AI.
- Keep responses focused and actionable — analysts are busy

## Transaction Under Investigation
{transaction_context}"""


def _build_transaction_context(txn: Transaction) -> str:
    """Build a compact context block from a DB Transaction object."""
    lines = [
        f"txn_id: {txn.txn_id}",
        f"time: {txn.timestamp}",
        f"payer: {txn.payer}",
        f"issuer: {txn.issuer} ({txn.country})",
        f"merchant: {txn.merchant} @ {txn.city}",
        f"amount: IDR {txn.amount_idr:,} ({txn.amount_foreign} {txn.currency})",
        f"risk_score: {txn.risk_score:.4f}",
        f"is_flagged: {txn.is_flagged}",
        f"is_fraud (ground truth): {txn.is_fraud}",
    ]
    if txn.fraud_type:
        lines.append(f"fraud_type: {txn.fraud_type}")
    if txn.attack_detail:
        lines.append(f"detail: {txn.attack_detail}")
    if txn.xai_reasons:
        if isinstance(txn.xai_reasons, list):
            feats = " | ".join(
                f"{f.get('display_name', f.get('feature', '?'))}={f.get('importance', 0):.3f}"
                for f in txn.xai_reasons
            )
            lines.append(f"xai_features: {feats}")
    if txn.review_status:
        lines.append(f"analyst_review: {txn.review_status}")
        if txn.review_note:
            lines.append(f"review_note: {txn.review_note}")

    return "\n".join(lines)


def _call_qwen(messages: List[Dict[str, str]]) -> Dict[str, str]:
    """Call Qwen 3.5 Plus with chat history. Returns {content, reasoning}."""
    client = OpenAI(
        api_key=settings.dashscope_api_key,
        base_url="https://dashscope-intl.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1",
    )

    response = client.responses.create(
        model="qwen3.5-plus",
        input=messages,
        extra_body={"enable_thinking": True},
    )

    reasoning_text = ""
    content_text = ""

    for item in response.output:
        if item.type == "reasoning":
            for summary in item.summary:
                reasoning_text += summary.text
        elif item.type == "message":
            content_text = item.content[0].text

    return {
        "content": content_text.strip(),
        "reasoning": reasoning_text.strip() if reasoning_text.strip() else None,
    }


async def start_chat(
    txn_id: str,
    user_message: Optional[str],
    db: AsyncSession,
) -> tuple:
    """
    Start a new chat session about a transaction.

    Returns:
        (ChatSession, ChatMessage) — the session and the AI's first response
    """
    # 1. Load the transaction
    result = await db.execute(
        select(Transaction).where(Transaction.txn_id == txn_id)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise ValueError(f"Transaction '{txn_id}' not found")

    # 2. Create the session
    session = ChatSession(
        txn_id=txn_id,
        title=f"Investigation: {txn_id} ({txn.fraud_type or 'Unknown'})",
    )
    db.add(session)
    await db.flush()  # Get chat_id generated

    # 3. Build system message with transaction context
    tx_context = _build_transaction_context(txn)
    system_content = CHAT_SYSTEM_PROMPT.format(transaction_context=tx_context)

    # Save system message (seq=0, not shown to user but kept for history)
    sys_msg = ChatMessage(
        chat_id=session.chat_id,
        seq=0,
        role="system",
        content=system_content,
    )
    db.add(sys_msg)

    # 4. Build the messages for Qwen
    qwen_messages = [{"role": "system", "content": system_content}]

    if user_message:
        # Save user message
        user_msg = ChatMessage(
            chat_id=session.chat_id,
            seq=1,
            role="user",
            content=user_message,
        )
        db.add(user_msg)
        qwen_messages.append({"role": "user", "content": user_message})
        next_seq = 2
    else:
        # No user message — ask AI for initial analysis
        default_prompt = "Analyze this transaction and explain why it was flagged. What should I investigate?"
        user_msg = ChatMessage(
            chat_id=session.chat_id,
            seq=1,
            role="user",
            content=default_prompt,
        )
        db.add(user_msg)
        qwen_messages.append({"role": "user", "content": default_prompt})
        next_seq = 2

    # 5. Call Qwen
    logger.info(f"Chat {session.chat_id}: starting with {len(qwen_messages)} messages")
    ai_response = await asyncio.to_thread(_call_qwen, qwen_messages)

    # 6. Save AI response
    ai_msg = ChatMessage(
        chat_id=session.chat_id,
        seq=next_seq,
        role="assistant",
        content=ai_response["content"],
        reasoning=ai_response["reasoning"],
    )
    db.add(ai_msg)
    await db.commit()
    await db.refresh(session)
    await db.refresh(ai_msg)

    return session, ai_msg


async def send_message(
    chat_id: str,
    user_message: str,
    db: AsyncSession,
) -> tuple:
    """
    Send a follow-up message in an existing chat session.
    Loads full history and sends to Qwen for contextual response.

    Returns:
        (ChatSession, ChatMessage) — session and the AI's reply
    """
    # 1. Load the session
    result = await db.execute(
        select(ChatSession).where(ChatSession.chat_id == chat_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise ValueError(f"Chat session '{chat_id}' not found")

    # 2. Load all previous messages (ordered by seq)
    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == chat_id)
        .order_by(ChatMessage.seq)
    )
    history = msg_result.scalars().all()

    # 3. Build qwen messages from history
    qwen_messages = []
    for msg in history:
        qwen_messages.append({"role": msg.role, "content": msg.content})

    # 4. Determine next seq number
    next_seq = max(m.seq for m in history) + 1 if history else 1

    # 5. Add user message
    user_msg = ChatMessage(
        chat_id=chat_id,
        seq=next_seq,
        role="user",
        content=user_message,
    )
    db.add(user_msg)
    qwen_messages.append({"role": "user", "content": user_message})

    # 6. Call Qwen with full context
    logger.info(f"Chat {chat_id}: sending {len(qwen_messages)} messages to Qwen")
    ai_response = await asyncio.to_thread(_call_qwen, qwen_messages)

    # 7. Save AI response
    ai_msg = ChatMessage(
        chat_id=chat_id,
        seq=next_seq + 1,
        role="assistant",
        content=ai_response["content"],
        reasoning=ai_response["reasoning"],
    )
    db.add(ai_msg)

    # Update session timestamp
    import datetime
    session.updated_at = datetime.datetime.utcnow()

    await db.commit()
    await db.refresh(ai_msg)

    return session, ai_msg


async def get_chat_history(chat_id: str, db: AsyncSession) -> tuple:
    """Load a full chat session with all messages (excluding system message)."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.chat_id == chat_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise ValueError(f"Chat session '{chat_id}' not found")

    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == chat_id)
        .where(ChatMessage.role != "system")  # Don't expose system prompt
        .order_by(ChatMessage.seq)
    )
    messages = msg_result.scalars().all()

    return session, messages


async def list_chats(
    txn_id: Optional[str],
    limit: int,
    db: AsyncSession,
) -> list:
    """List chat sessions, optionally filtered by transaction."""
    query = (
        select(
            ChatSession,
            func.count(ChatMessage.id).label("msg_count"),
        )
        .outerjoin(ChatMessage, ChatMessage.chat_id == ChatSession.chat_id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(limit)
    )
    if txn_id:
        query = query.where(ChatSession.txn_id == txn_id)

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "chat_id": session.chat_id,
            "txn_id": session.txn_id,
            "title": session.title,
            "message_count": msg_count,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
        for session, msg_count in rows
    ]
