"""
Attack simulation router — WebSocket streaming + REST endpoints.
Updated: passes DB session to attack_simulation for persistence.
"""
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from schemas.attack import AttackConfig
from services import attack_simulation
from database import get_db, async_session
from models import AttackRun

router = APIRouter(tags=["Attack Simulation"])


# ── Response schemas ─────────────────────────────────────────────────────────
class AttackRunOut(BaseModel):
    id: int
    total_txns: int
    fraud_pct: float
    speed: str
    mode: Optional[str] = None
    total: int = 0
    approved: int = 0
    flagged: int = 0
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    recall: float = 0
    precision: float = 0
    f1: float = 0
    fpr: float = 0
    roi_saved: int = 0
    per_type: Optional[dict] = None
    per_type_total: Optional[dict] = None
    status: str = "running"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── WebSocket ────────────────────────────────────────────────────────────────
@router.websocket("/ws/attack")
async def ws_attack(ws: WebSocket):
    """
    WebSocket for attack simulation.

    Send a JSON config to start:
        {"total": 500, "fraud_pct": 0.05, "speed": "normal"}

    Receives streamed events:
        {"type": "transaction", "data": {...}}
        {"type": "stats_update", "data": {...}}
        {"type": "attack_start", "data": {"total": N, "fraud": M}}
        {"type": "attack_end", "data": {...}}
        {"type": "log", "level": "info", "text": "..."}
    """
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            config = AttackConfig(**json.loads(raw))

            # Create a DB session for this run
            async with async_session() as db:
                async for event in attack_simulation.run_attack(config, db=db):
                    await ws.send_text(json.dumps(event))

    except WebSocketDisconnect:
        pass


# ── REST ─────────────────────────────────────────────────────────────────────
@router.post(
    "/api/v1/attack/start",
    summary="Start attack simulation (non-streaming)",
    description=(
        "Starts an attack simulation synchronously and returns the final stats. "
        "For real-time streaming, use the WebSocket endpoint at /ws/attack instead."
    ),
)
async def start_attack_rest(config: AttackConfig, db: AsyncSession = Depends(get_db)):
    """Start an attack and return the final results (no streaming)."""
    transactions = []
    final_stats = {}

    async for event in attack_simulation.run_attack(config, db=db):
        if event.get("type") == "transaction":
            transactions.append(event["data"])
        elif event.get("type") == "attack_end":
            final_stats = event["data"]

    return {
        "stats": final_stats,
        "transactions": transactions,
        "total_transactions": len(transactions),
    }


@router.get(
    "/api/v1/attack/history",
    response_model=List[AttackRunOut],
    summary="Get past attack simulation runs",
)
async def get_attack_history(
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Paginated list of past attack simulation runs."""
    query = select(AttackRun).order_by(desc(AttackRun.started_at)).limit(limit)
    if status:
        query = query.where(AttackRun.status == status)

    result = await db.execute(query)
    runs = result.scalars().all()
    return [AttackRunOut.model_validate(r) for r in runs]
