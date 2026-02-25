"""Pydantic schemas for the fraud reasoning endpoint."""
from typing import List, Optional
from pydantic import BaseModel, Field


class XAIFeature(BaseModel):
    """Single XAI feature importance from HTGNN."""
    feature: str = Field(..., description="Feature key, e.g. 'amount_idr'")
    display_name: str = Field(..., description="Human-readable name")
    importance: float = Field(..., ge=0, le=1, description="SHAP-like importance weight 0-1")


class TransactionData(BaseModel):
    """Transaction flagged by HTGNN model — sent to Qwen for reasoning."""
    txn_id: str = Field(..., example="TXN-000042")
    timestamp: str = Field(..., example="2026-02-25 14:23:01")
    payer: str = Field(..., example="a1b2c3d4e5")
    issuer: str = Field(..., example="Alipay_CN")
    country: str = Field(..., example="CN")
    merchant: str = Field(..., example="Bali Beach Resort")
    city: str = Field(..., example="Bali")
    amount_idr: int = Field(..., example=5200000)
    amount_foreign: float = Field(..., example=2122.45)
    currency: str = Field(..., example="CNY")
    risk_score: float = Field(..., ge=0, le=1, example=0.8731)
    is_flagged: bool = Field(True, description="Always True — only flagged txns are sent")
    fraud_type: Optional[str] = Field(
        None,
        description="HTGNN-predicted fraud type",
        example="velocity_attack",
    )
    attack_detail: Optional[str] = Field(None, example="10 txns from same payer in <3min")
    xai_reasons: List[XAIFeature] = Field(
        default_factory=list,
        description="Top contributing features from HTGNN explainability",
    )

    model_config = {"json_schema_extra": {"examples": [
        {
            "txn_id": "TXN-000042",
            "timestamp": "2026-02-25 14:23:01",
            "payer": "a1b2c3d4e5",
            "issuer": "Alipay_CN",
            "country": "CN",
            "merchant": "Bali Beach Resort",
            "city": "Bali",
            "amount_idr": 5200000,
            "amount_foreign": 2122.45,
            "currency": "CNY",
            "risk_score": 0.8731,
            "is_flagged": True,
            "fraud_type": "velocity_attack",
            "attack_detail": "10 txns from same payer in <3min",
            "xai_reasons": [
                {"feature": "payer_txn_count_1h", "display_name": "Payer Activity (1h)", "importance": 0.412},
                {"feature": "time_since_last_txn_sec", "display_name": "Time Since Last Txn", "importance": 0.287},
                {"feature": "amount_idr", "display_name": "Transaction Amount", "importance": 0.183},
            ],
        }
    ]}}


class FraudReasonResponse(BaseModel):
    """Structured AI reasoning response."""
    txn_id: str
    risk_score: float
    fraud_type: Optional[str]
    reasoning: str = Field(..., description="AI's chain-of-thought reasoning (thinking mode)")
    explanation: str = Field(..., description="Concise human-readable fraud explanation")
    confidence: str = Field(
        ...,
        description="AI's confidence level: HIGH / MEDIUM / LOW",
        example="HIGH",
    )
