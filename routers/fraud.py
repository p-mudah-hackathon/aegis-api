"""Fraud reasoning router — single endpoint for HTGNN-flagged transaction explanations."""
from fastapi import APIRouter, HTTPException
from schemas.fraud import TransactionData, FraudReasonResponse
from services.qwen_reasoning import get_fraud_reasoning

router = APIRouter(prefix="/api/v1/fraud", tags=["Fraud Reasoning"])


@router.post(
    "/reason",
    response_model=FraudReasonResponse,
    summary="Explain why a transaction was flagged as fraud",
    description=(
        "Accepts a transaction flagged by the HTGNN model and returns an AI-generated "
        "explanation of why the transaction was marked as fraudulent, powered by Qwen 3.5 Plus."
    ),
)
async def explain_fraud(txn: TransactionData):
    """
    Send a flagged transaction to Qwen 3.5 Plus for fraud reasoning.

    The AI analyzes the transaction features, XAI importance weights,
    and fraud type to produce a detailed yet concise explanation.
    """
    try:
        result = get_fraud_reasoning(txn)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Qwen AI service error: {str(e)}",
        )

    return FraudReasonResponse(
        txn_id=txn.txn_id,
        risk_score=txn.risk_score,
        fraud_type=txn.fraud_type,
        reasoning=result["reasoning"],
        explanation=result["explanation"],
        confidence=result["confidence"],
    )
