"""Pydantic schemas for attack simulation endpoints."""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field


class AttackConfig(BaseModel):
    """Configuration for an attack simulation run."""
    total: int = Field(500, ge=10, le=10000, description="Total transactions to simulate")
    fraud_pct: float = Field(0.05, ge=0.01, le=0.5, description="Fraction of fraud transactions")
    speed: str = Field("normal", description="Simulation speed: slow | normal | fast")

    model_config = {"json_schema_extra": {"examples": [
        {"total": 500, "fraud_pct": 0.05, "speed": "normal"}
    ]}}


class XAIFeature(BaseModel):
    feature: str
    display_name: str
    importance: float


class TransactionEvent(BaseModel):
    """A single scored transaction event streamed during simulation."""
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
    xai_reasons: List[XAIFeature] = []


class StatsSnapshot(BaseModel):
    """Current simulation statistics."""
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
    per_type: Dict[str, int] = {}
    per_type_total: Dict[str, int] = {}
    roi_saved: int = 0
