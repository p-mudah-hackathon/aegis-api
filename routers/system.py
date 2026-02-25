"""
System router — health, model status proxy, WebSocket event schema docs.
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from fastapi import APIRouter
from services import aegis_ai_client

router = APIRouter(tags=["System"])


class ModelStatus(BaseModel):
    """Proxied model info from aegis-ai."""
    status: str
    threshold: float
    mode: str
    architecture: str = "HTGNN"
    n_layers: Optional[int] = None
    d_model: Optional[int] = None
    gate_value: Optional[float] = None
    n_edges: Optional[int] = None
    aegis_ai_reachable: bool


class WSEventField(BaseModel):
    name: str
    type: str
    description: str


class WSEventType(BaseModel):
    type: str
    description: str
    fields: List[WSEventField] = []


class WSSchemaResponse(BaseModel):
    description: str
    endpoints: Dict[str, Any]
    event_types: List[WSEventType]


@router.get(
    "/api/v1/model/status",
    response_model=ModelStatus,
    summary="Get ML model status (proxied from aegis-ai)",
)
async def get_model_status():
    """
    Proxy to aegis-ai /model/info so the React frontend
    only needs to talk to aegis-api.
    """
    reachable = await aegis_ai_client.health_check()
    if not reachable:
        return ModelStatus(
            status="unavailable",
            threshold=0.5,
            mode="SIMULATION",
            aegis_ai_reachable=False,
        )
    try:
        info = await aegis_ai_client.get_model_info()
        return ModelStatus(
            status=info.get("status", "unknown"),
            threshold=info.get("threshold", 0.5),
            mode=info.get("mode", "SIMULATION"),
            architecture=info.get("architecture", "HTGNN"),
            n_layers=info.get("n_layers"),
            d_model=info.get("d_model"),
            gate_value=info.get("gate_value"),
            n_edges=info.get("n_edges"),
            aegis_ai_reachable=True,
        )
    except Exception:
        return ModelStatus(
            status="error",
            threshold=0.5,
            mode="SIMULATION",
            aegis_ai_reachable=False,
        )


@router.get(
    "/api/v1/ws/schema",
    response_model=WSSchemaResponse,
    summary="WebSocket event type documentation",
    description="Returns the schema of all WebSocket event types for frontend integration.",
)
async def get_ws_schema():
    """
    Since WebSocket events aren't in OpenAPI, this endpoint
    documents all event types your React app will receive.
    """
    return WSSchemaResponse(
        description="WebSocket event types for /ws/attack and /ws/dashboard",
        endpoints={
            "/ws/attack": {
                "direction": "bidirectional",
                "send": "JSON AttackConfig: {total: int, fraud_pct: float, speed: string}",
                "receive": "Streamed events (see event_types below)",
            },
            "/ws/dashboard": {
                "direction": "receive-only",
                "receive": "Same events as /ws/attack, plus 'snapshot' on connect",
            },
        },
        event_types=[
            WSEventType(
                type="snapshot",
                description="Sent on /ws/dashboard connect — current stats state",
                fields=[WSEventField(name="data", type="StatsSnapshot", description="Current simulation stats")],
            ),
            WSEventType(
                type="log",
                description="Log message from the simulation engine",
                fields=[
                    WSEventField(name="level", type="string", description="info | warning | success | error"),
                    WSEventField(name="text", type="string", description="Log message text"),
                ],
            ),
            WSEventType(
                type="attack_start",
                description="Emitted when simulation begins",
                fields=[
                    WSEventField(name="data.total", type="int", description="Total transactions to simulate"),
                    WSEventField(name="data.fraud", type="int", description="Number of fraud transactions"),
                ],
            ),
            WSEventType(
                type="transaction",
                description="A single scored transaction",
                fields=[
                    WSEventField(name="data.txn_id", type="string", description="Transaction ID"),
                    WSEventField(name="data.risk_score", type="float", description="Model risk score 0-1"),
                    WSEventField(name="data.is_flagged", type="bool", description="Whether score >= threshold"),
                    WSEventField(name="data.is_fraud", type="bool", description="Ground truth label"),
                    WSEventField(name="data.fraud_type", type="string|null", description="velocity_attack | card_testing | collusion_ring | geo_anomaly | amount_anomaly"),
                    WSEventField(name="data.xai_reasons", type="array", description="Feature importance list [{feature, display_name, importance}]"),
                ],
            ),
            WSEventType(
                type="stats_update",
                description="Updated stats (emitted every 10 transactions)",
                fields=[
                    WSEventField(name="data", type="StatsSnapshot", description="tp, fp, tn, fn, recall, precision, f1, fpr, roi_saved, per_type, per_type_total"),
                ],
            ),
            WSEventType(
                type="attack_end",
                description="Emitted when simulation completes",
                fields=[WSEventField(name="data", type="StatsSnapshot", description="Final stats")],
            ),
            WSEventType(
                type="error",
                description="Error message",
                fields=[WSEventField(name="text", type="string", description="Error description")],
            ),
        ],
    )
