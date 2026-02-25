"""
HTTP client for aegis-ai ML model service.
Wraps /model/score, /model/explain, /model/info as async calls.
"""
from typing import List, Dict, Any, Optional
import httpx
from config import settings

AEGIS_AI_URL = settings.aegis_ai_url
_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=AEGIS_AI_URL, timeout=30.0)
    return _client


async def get_model_info() -> Dict[str, Any]:
    """GET /model/info — model metadata."""
    client = _get_client()
    resp = await client.get("/model/info")
    resp.raise_for_status()
    return resp.json()


async def score_transactions(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    POST /model/score — score a batch of transactions.

    Args:
        transactions: list of dicts with keys: txn_id, is_fraud, fraud_type
    Returns:
        dict with keys: results (list of {txn_id, risk_score, is_flagged}),
                        threshold, mode
    """
    client = _get_client()
    resp = await client.post("/model/score", json={"transactions": transactions})
    resp.raise_for_status()
    return resp.json()


async def explain_transaction(
    txn_id: str,
    risk_score: float,
    is_fraud: bool = False,
    fraud_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    POST /model/explain — XAI feature importances for one transaction.

    Returns:
        list of {feature, display_name, importance}
    """
    client = _get_client()
    resp = await client.post(
        "/model/explain",
        json={
            "txn_id": txn_id,
            "risk_score": risk_score,
            "is_fraud": is_fraud,
            "fraud_type": fraud_type,
        },
    )
    resp.raise_for_status()
    return resp.json().get("features", [])


async def health_check() -> bool:
    """Check if aegis-ai is reachable."""
    try:
        client = _get_client()
        resp = await client.get("/health")
        return resp.status_code == 200
    except Exception:
        return False
