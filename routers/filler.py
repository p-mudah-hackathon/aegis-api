"""
Data Filler router — start/stop continuous transaction generation for demos.
"""
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter
from services.data_filler import start_filler, stop_filler, get_filler_status

router = APIRouter(prefix="/api/v1/filler", tags=["Data Filler"])


class FillerConfig(BaseModel):
    """Configuration for the data filler."""
    min_interval: float = Field(
        2.0, ge=0.5, le=30.0,
        description="Minimum seconds between transactions",
    )
    max_interval: float = Field(
        5.0, ge=1.0, le=60.0,
        description="Maximum seconds between transactions",
    )
    fraud_ratio: float = Field(
        0.08, ge=0.0, le=0.5,
        description="Fraction of transactions that are fraudulent (0.08 = 8%)",
    )

    model_config = {"json_schema_extra": {"examples": [
        {"min_interval": 2.0, "max_interval": 5.0, "fraud_ratio": 0.08}
    ]}}


class FillerStatus(BaseModel):
    is_running: bool
    total_inserted: int
    started_at: Optional[str] = None
    last_txn_at: Optional[str] = None
    interval_range: list
    fraud_ratio: float


@router.post(
    "/start",
    response_model=FillerStatus,
    summary="Start continuous data filling",
    description=(
        "Starts a background task that generates, scores, and inserts "
        "transactions at random intervals (default 2-5s). "
        "~8% will be fraud. Use /stop to halt."
    ),
)
async def start_filling(config: FillerConfig = FillerConfig()):
    """Start the data filler background task."""
    started = start_filler(
        min_interval=config.min_interval,
        max_interval=config.max_interval,
        fraud_ratio=config.fraud_ratio,
    )
    status = get_filler_status()
    if not started:
        status["message"] = "Filler is already running. Stop it first."
    return status


@router.post(
    "/stop",
    response_model=FillerStatus,
    summary="Stop continuous data filling",
)
async def stop_filling():
    """Stop the data filler background task."""
    stopped = stop_filler()
    status = get_filler_status()
    if not stopped:
        status["message"] = "Filler is not running."
    return status


@router.get(
    "/status",
    response_model=FillerStatus,
    summary="Get data filler status",
)
async def filler_status():
    """Check if the data filler is running and how many transactions it has inserted."""
    return get_filler_status()
