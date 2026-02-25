"""
Transactions router — CRUD, pagination, filtering, analyst review, cached reasoning.
"""
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_
from sqlalchemy.orm import selectinload

from database import get_db
from models import Transaction, FraudReason
from errors import NotFoundError
from schemas.fraud import TransactionData, FraudReasonResponse
from services.qwen_reasoning import get_fraud_reasoning

router = APIRouter(prefix="/api/v1/transactions", tags=["Transactions"])


# ── Response schemas ─────────────────────────────────────────────────────────
from pydantic import BaseModel, Field


class TransactionOut(BaseModel):
    """Transaction as returned to the frontend."""
    txn_id: str
    timestamp: str
    payer: str
    issuer: str
    country: str
    merchant: str
    city: str
    amount_idr: int
    amount_foreign: float
    currency: str
    risk_score: float
    is_flagged: bool
    is_fraud: bool
    fraud_type: Optional[str] = None
    attack_detail: Optional[str] = None
    xai_reasons: Optional[list] = None
    review_status: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaginatedTransactions(BaseModel):
    items: List[TransactionOut]
    total: int
    page: int
    page_size: int
    pages: int


class ReviewRequest(BaseModel):
    status: str = Field(
        ...,
        description="confirmed_fraud | false_positive",
        example="confirmed_fraud",
    )
    note: Optional[str] = Field(None, example="Verified with cardholder")


class CachedReasonOut(BaseModel):
    txn_id: str
    risk_score: float
    fraud_type: Optional[str]
    reasoning: str
    explanation: str
    confidence: str
    cached: bool = Field(True, description="Whether this was served from cache")


# ── Endpoints ────────────────────────────────────────────────────────────────
@router.get(
    "",
    response_model=PaginatedTransactions,
    summary="List transactions with pagination and filters",
)
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_flagged: Optional[bool] = None,
    is_fraud: Optional[bool] = None,
    fraud_type: Optional[str] = None,
    review_status: Optional[str] = None,
    min_risk: Optional[float] = Query(None, ge=0, le=1),
    max_risk: Optional[float] = Query(None, ge=0, le=1),
    payer: Optional[str] = None,
    merchant: Optional[str] = None,
    search: Optional[str] = Query(None, description="Global search string"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="asc or desc"),
    db: AsyncSession = Depends(get_db),
):
    """Paginated transaction list with filters for the dashboard table."""
    query = select(Transaction)

    # Apply filters
    if is_flagged is not None:
        query = query.where(Transaction.is_flagged == is_flagged)
    if is_fraud is not None:
        query = query.where(Transaction.is_fraud == is_fraud)
    if fraud_type:
        query = query.where(Transaction.fraud_type == fraud_type)
    if review_status:
        query = query.where(Transaction.review_status == review_status)
    if min_risk is not None:
        query = query.where(Transaction.risk_score >= min_risk)
    if max_risk is not None:
        query = query.where(Transaction.risk_score <= max_risk)
    if payer:
        query = query.where(Transaction.payer == payer)
    if merchant:
        query = query.where(Transaction.merchant.contains(merchant))
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Transaction.txn_id.ilike(search_pattern),
                Transaction.payer.ilike(search_pattern),
                Transaction.merchant.ilike(search_pattern),
                Transaction.city.ilike(search_pattern),
                Transaction.fraud_type.ilike(search_pattern),
            )
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sort
    sort_col = getattr(Transaction, sort_by, Transaction.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    pages = max(1, (total + page_size - 1) // page_size)

    return PaginatedTransactions(
        items=[TransactionOut.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/{txn_id}",
    response_model=TransactionOut,
    summary="Get single transaction by ID",
)
async def get_transaction(txn_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single transaction with all details."""
    result = await db.execute(
        select(Transaction).where(Transaction.txn_id == txn_id)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise NotFoundError("Transaction", txn_id)
    return TransactionOut.model_validate(txn)


@router.get(
    "/{txn_id}/reason",
    response_model=CachedReasonOut,
    summary="Get or generate fraud reasoning for a transaction",
)
async def get_transaction_reason(txn_id: str, db: AsyncSession = Depends(get_db)):
    """
    Returns cached Qwen AI reasoning if available.
    If not cached, generates a new one, caches it, and returns it.
    """
    # Check DB cache
    result = await db.execute(
        select(FraudReason).where(FraudReason.txn_id == txn_id)
    )
    cached = result.scalar_one_or_none()

    if cached:
        return CachedReasonOut(
            txn_id=cached.txn_id,
            risk_score=cached.risk_score,
            fraud_type=cached.fraud_type,
            reasoning=cached.reasoning,
            explanation=cached.explanation,
            confidence=cached.confidence,
            cached=True,
        )

    # Not cached — get the transaction
    txn_result = await db.execute(
        select(Transaction).where(Transaction.txn_id == txn_id)
    )
    txn = txn_result.scalar_one_or_none()
    if not txn:
        raise NotFoundError("Transaction", txn_id)

    # Build request for Qwen
    txn_data = TransactionData(
        txn_id=txn.txn_id,
        timestamp=txn.timestamp,
        payer=txn.payer,
        issuer=txn.issuer,
        country=txn.country,
        merchant=txn.merchant,
        city=txn.city,
        amount_idr=txn.amount_idr,
        amount_foreign=txn.amount_foreign,
        currency=txn.currency,
        risk_score=txn.risk_score,
        is_flagged=txn.is_flagged,
        fraud_type=txn.fraud_type,
        attack_detail=txn.attack_detail,
        xai_reasons=txn.xai_reasons or [],
    )

    ai_result = get_fraud_reasoning(txn_data)

    # Cache in DB
    reason = FraudReason(
        txn_id=txn.txn_id,
        risk_score=txn.risk_score,
        fraud_type=txn.fraud_type,
        reasoning=ai_result["reasoning"],
        explanation=ai_result["explanation"],
        confidence=ai_result["confidence"],
    )
    db.add(reason)
    await db.commit()

    return CachedReasonOut(
        txn_id=txn.txn_id,
        risk_score=txn.risk_score,
        fraud_type=txn.fraud_type,
        reasoning=ai_result["reasoning"],
        explanation=ai_result["explanation"],
        confidence=ai_result["confidence"],
        cached=False,
    )


@router.post(
    "/{txn_id}/review",
    response_model=TransactionOut,
    summary="Submit analyst review for a transaction",
)
async def review_transaction(
    txn_id: str,
    review: ReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark a flagged transaction as confirmed_fraud or false_positive.
    Used by analysts in the dashboard.
    """
    result = await db.execute(
        select(Transaction).where(Transaction.txn_id == txn_id)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise NotFoundError("Transaction", txn_id)

    txn.review_status = review.status
    txn.reviewed_at = datetime.utcnow()
    txn.review_note = review.note
    await db.commit()
    await db.refresh(txn)

    return TransactionOut.model_validate(txn)
