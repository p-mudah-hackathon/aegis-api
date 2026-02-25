"""
Data Filler — background task that continuously generates, scores, and inserts
transactions at random intervals for demo purposes.

Best practice for demos: 2-5 second random intervals between transactions
to simulate realistic traffic without overwhelming the UI.
"""
import asyncio
import logging
import random
import secrets
from datetime import datetime
from typing import Optional

import numpy as np

from database import async_session
from models import Transaction
from services import aegis_ai_client
from services.transaction_engine import gen_normal, gen_velocity, gen_card_testing, gen_collusion, gen_geo, gen_amount, ISSUERS

logger = logging.getLogger("aegis.filler")

# ── Global state ─────────────────────────────────────────────────────────────
_filler_task: Optional[asyncio.Task] = None
_filler_stats = {
    "is_running": False,
    "total_inserted": 0,
    "started_at": None,
    "last_txn_at": None,
    "interval_range": [2.0, 5.0],
    "fraud_ratio": 0.08,
}


def get_filler_status() -> dict:
    return {**_filler_stats}


def is_filler_running() -> bool:
    return _filler_stats["is_running"]


async def _generate_single_txn(rng: np.random.Generator, txn_counter: int) -> dict:
    """Generate a single random transaction (normal or fraud)."""
    base_time = datetime.utcnow()
    fraud_ratio = _filler_stats["fraud_ratio"]
    run_id_prefix = secrets.token_hex(2)

    if rng.random() < fraud_ratio:
        # Pick a random fraud type
        fraud_gen = rng.choice([
            "velocity", "card_testing", "collusion", "geo", "amount"
        ])
        generators = {
            "velocity": gen_velocity,
            "card_testing": gen_card_testing,
            "collusion": gen_collusion,
            "geo": gen_geo,
            "amount": gen_amount,
        }
        txns = generators[fraud_gen](rng, txn_counter, base_time, run_id_prefix)
        return txns[0]  # Take just the first from the batch
    else:
        return gen_normal(rng, txn_counter, base_time, run_id_prefix)


async def _score_single_txn(txn: dict) -> tuple:
    """Score a single transaction via aegis-ai, return (score, is_flagged, xai)."""
    try:
        score_resp = await aegis_ai_client.score_transactions([{
            "txn_id": txn["txn_id"],
            "is_fraud": txn["is_fraud"],
            "fraud_type": txn.get("fraud_type"),
        }])
        result = score_resp["results"][0]
        score = result["risk_score"]
        is_flagged = result["is_flagged"]
    except Exception:
        rng = np.random.default_rng()
        score = round(float(rng.beta(5, 2) if txn["is_fraud"] else rng.beta(1, 8)), 4)
        is_flagged = score >= 0.5

    xai_reasons = []
    if is_flagged:
        try:
            xai_reasons = await aegis_ai_client.explain_transaction(
                txn_id=txn["txn_id"],
                risk_score=score,
                is_fraud=txn["is_fraud"],
                fraud_type=txn.get("fraud_type"),
            )
        except Exception:
            pass

    return score, is_flagged, xai_reasons


async def _filler_loop():
    """Main filler loop — runs until cancelled."""
    global _filler_stats
    rng = np.random.default_rng()
    txn_counter = int(datetime.utcnow().timestamp()) % 1000000

    logger.info("Data filler started")

    while True:
        try:
            txn_counter += 1
            txn = await _generate_single_txn(rng, txn_counter)
            score, is_flagged, xai_reasons = await _score_single_txn(txn)

            # Persist to DB
            async with async_session() as db:
                db_txn = Transaction(
                    txn_id=txn["txn_id"],
                    timestamp=txn["timestamp"],
                    payer=txn["payer"],
                    issuer=txn["issuer"],
                    country=txn["country"],
                    merchant=txn["merchant"],
                    city=txn["city"],
                    amount_idr=txn["amount_idr"],
                    amount_foreign=txn["amount_foreign"],
                    currency=txn["currency"],
                    risk_score=score,
                    is_flagged=is_flagged,
                    is_fraud=txn["is_fraud"],
                    fraud_type=txn.get("fraud_type"),
                    attack_detail=txn.get("attack_detail"),
                    xai_reasons=xai_reasons,
                )
                db.add(db_txn)
                await db.commit()

            _filler_stats["total_inserted"] += 1
            _filler_stats["last_txn_at"] = datetime.utcnow().isoformat()

            logger.debug(
                f"Inserted {txn['txn_id']} | "
                f"score={score:.4f} | flagged={is_flagged} | "
                f"fraud={txn['is_fraud']} ({txn.get('fraud_type', 'normal')})"
            )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Filler error: {e}")

        # Random interval between transactions (2-5 seconds)
        min_interval, max_interval = _filler_stats["interval_range"]
        delay = random.uniform(min_interval, max_interval)
        await asyncio.sleep(delay)


def start_filler(
    min_interval: float = 2.0,
    max_interval: float = 5.0,
    fraud_ratio: float = 0.08,
) -> bool:
    """Start the background filler task. Returns False if already running."""
    global _filler_task, _filler_stats

    if _filler_stats["is_running"]:
        return False

    _filler_stats["is_running"] = True
    _filler_stats["total_inserted"] = 0
    _filler_stats["started_at"] = datetime.utcnow().isoformat()
    _filler_stats["last_txn_at"] = None
    _filler_stats["interval_range"] = [min_interval, max_interval]
    _filler_stats["fraud_ratio"] = fraud_ratio

    _filler_task = asyncio.create_task(_filler_loop())
    return True


def stop_filler() -> bool:
    """Stop the background filler task. Returns False if not running."""
    global _filler_task, _filler_stats

    if not _filler_stats["is_running"] or _filler_task is None:
        return False

    _filler_task.cancel()
    _filler_task = None
    _filler_stats["is_running"] = False
    logger.info(f"Data filler stopped. Total inserted: {_filler_stats['total_inserted']}")
    return True
