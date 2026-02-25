"""
Dashboard router — global stats from DB, WebSocket for live stream.
"""
import json
from typing import List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from schemas.attack import StatsSnapshot
from services.attack_simulation import get_stats
from database import get_db
from models import Transaction

router = APIRouter(tags=["Dashboard"])

# ── Connected dashboard clients ──────────────────────────────────────────────
dashboard_clients: List[WebSocket] = []


async def broadcast(event: dict):
    """Broadcast an event to all connected dashboard clients."""
    dead = []
    msg = json.dumps(event)
    for ws in dashboard_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in dashboard_clients:
            dashboard_clients.remove(ws)


@router.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket):
    """
    WebSocket for dashboard — receive-only.

    On connect, sends current stats snapshot.
    Then streams all transaction events as they happen during attack simulations.
    """
    await ws.accept()
    dashboard_clients.append(ws)
    stats = get_stats()
    await ws.send_text(json.dumps({"type": "snapshot", "data": stats.model_dump()}))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in dashboard_clients:
            dashboard_clients.remove(ws)


# ── Dashboard counts (global, from DB) ───────────────────────────────────────
class DashboardCounts(BaseModel):
    """Global counts from database — NOT page-local."""
    total: int = 0
    flagged: int = 0
    fraud: int = 0
    pending_review: int = 0
    reviewed: int = 0


@router.get(
    "/api/v1/dashboard/counts",
    response_model=DashboardCounts,
    summary="Global dashboard counts from the entire database",
)
async def get_dashboard_counts(db: AsyncSession = Depends(get_db)):
    """
    Returns global counts from the entire transactions table:
    - total: all transactions
    - flagged: where is_flagged = true
    - fraud: where is_fraud = true (ground truth)
    - pending_review: where is_flagged = true AND review_status is null
    - reviewed: where review_status is not null
    """
    total = await db.execute(select(func.count()).select_from(Transaction))
    flagged = await db.execute(
        select(func.count()).select_from(Transaction).where(
            Transaction.is_flagged == True,
        )
    )
    fraud = await db.execute(
        select(func.count()).select_from(Transaction).where(
            Transaction.review_status == "confirmed_fraud",
        )
    )
    pending = await db.execute(
        select(func.count()).select_from(Transaction).where(
            Transaction.is_flagged == True,
            Transaction.review_status == None,
        )
    )
    reviewed = await db.execute(
        select(func.count()).select_from(Transaction).where(
            Transaction.review_status != None,
        )
    )

    return DashboardCounts(
        total=total.scalar() or 0,
        flagged=flagged.scalar() or 0,
        fraud=fraud.scalar() or 0,
        pending_review=pending.scalar() or 0,
        reviewed=reviewed.scalar() or 0,
    )


@router.get(
    "/api/v1/stats",
    response_model=StatsSnapshot,
    summary="Get current simulation stats",
    description="Returns the current attack simulation statistics snapshot.",
)
async def get_current_stats():
    """Return current simulation stats."""
    return get_stats()
