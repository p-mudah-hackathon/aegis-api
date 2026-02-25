"""
Attack simulation orchestrator.
Generates transactions, scores them via aegis-ai, tracks stats, persists to DB.
"""
import asyncio
import datetime
from typing import AsyncGenerator, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from services import aegis_ai_client
from services.transaction_engine import generate_attack_batch
from schemas.attack import AttackConfig, StatsSnapshot
from models import SimulatedTransaction, AttackRun


# ── Global state ─────────────────────────────────────────────────────────────
attack_running = False
current_stats = StatsSnapshot()


def get_stats() -> StatsSnapshot:
    return current_stats


def is_running() -> bool:
    return attack_running


async def run_attack(
    config: AttackConfig,
    db: Optional[AsyncSession] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Run an attack simulation. Yields JSON-serializable events.
    If db session is provided, persists transactions and attack run.

    Event types:
        - {"type": "log", "level": "info|success|error", "text": "..."}
        - {"type": "attack_start", "data": {total, fraud}}
        - {"type": "transaction", "data": TransactionEvent}
        - {"type": "stats_update", "data": StatsSnapshot}
        - {"type": "attack_end", "data": StatsSnapshot}
    """
    global attack_running, current_stats

    if attack_running:
        yield {"type": "error", "text": "Attack already running!"}
        return

    attack_running = True
    current_stats = StatsSnapshot()

    delay_map = {"slow": 0.15, "normal": 0.04, "fast": 0.005}
    delay = delay_map.get(config.speed, 0.04)

    # Create attack run record in DB
    attack_run = None
    if db:
        attack_run = AttackRun(
            total_txns=config.total,
            fraud_pct=config.fraud_pct,
            speed=config.speed,
            status="running",
        )
        db.add(attack_run)
        await db.commit()
        await db.refresh(attack_run)

    try:
        # 1. Check aegis-ai health
        yield {"type": "log", "level": "info", "text": "[AegisNode] Connecting to ML model service..."}
        ai_healthy = await aegis_ai_client.health_check()
        if not ai_healthy:
            yield {"type": "log", "level": "warning", "text": "[AegisNode] aegis-ai unreachable, using simulation mode"}

        # 2. Get model info
        mode = "SIMULATION"
        threshold = 0.5
        try:
            model_info = await aegis_ai_client.get_model_info()
            mode = model_info.get("mode", "SIMULATION")
            threshold = model_info.get("threshold", 0.5)
            yield {"type": "log", "level": "info", "text": f"[AegisNode] Mode: {mode} | Threshold: {threshold:.3f}"}
        except Exception:
            yield {"type": "log", "level": "info", "text": f"[AegisNode] Mode: SIMULATION | Threshold: {threshold:.3f}"}

        if attack_run and db:
            attack_run.mode = mode
            await db.commit()

        # 3. Generate transactions
        yield {"type": "log", "level": "info", "text": f"[AegisNode] Generating {config.total} transactions ({config.fraud_pct:.0%} fraud)..."}
        all_txns = generate_attack_batch(
            total=config.total,
            fraud_pct=config.fraud_pct,
        )
        n_actual_fraud = sum(1 for t in all_txns if t["is_fraud"])

        yield {"type": "log", "level": "info", "text": f"[AegisNode] Ready: {len(all_txns)} txns ({n_actual_fraud} fraud). Streaming..."}
        yield {"type": "attack_start", "data": {"total": len(all_txns), "fraud": n_actual_fraud}}

        # 4. Score & stream each transaction
        s = current_stats
        for i, txn in enumerate(all_txns):
            # Score via aegis-ai
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
                import numpy as np
                rng = np.random.default_rng()
                score = round(float(rng.beta(5, 2) if txn["is_fraud"] else rng.beta(1, 8)), 4)
                is_flagged = score >= threshold

            # Get XAI if flagged
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

            # Persist to DB
            if db:
                db_txn = SimulatedTransaction(
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
                    attack_run_id=attack_run.id if attack_run else None,
                )
                db.add(db_txn)
                # Batch commit every 50 txns
                if i % 50 == 0:
                    await db.commit()

            # Update stats
            s.total += 1
            if txn["is_fraud"]:
                ft = txn["fraud_type"]
                s.per_type_total[ft] = s.per_type_total.get(ft, 0) + 1
                if is_flagged:
                    s.tp += 1
                    s.flagged += 1
                    s.per_type[ft] = s.per_type.get(ft, 0) + 1
                else:
                    s.fn += 1
                    s.approved += 1
            else:
                if is_flagged:
                    s.fp += 1
                    s.flagged += 1
                else:
                    s.tn += 1
                    s.approved += 1

            tp, fp, fn, tn = s.tp, s.fp, s.fn, s.tn
            s.recall = round(tp / max(tp + fn, 1), 4)
            s.precision = round(tp / max(tp + fp, 1), 4)
            s.f1 = round(
                2 * s.precision * s.recall / max(s.precision + s.recall, 1e-8), 4
            )
            s.fpr = round(fp / max(fp + tn, 1), 4)
            s.roi_saved = tp * 1_500_000

            # Yield transaction event
            txn_event = {
                "txn_id": txn["txn_id"],
                "timestamp": txn["timestamp"],
                "payer": txn["payer"],
                "issuer": txn["issuer"],
                "country": txn["country"],
                "merchant": txn["merchant"],
                "city": txn["city"],
                "amount_idr": txn["amount_idr"],
                "amount_foreign": txn["amount_foreign"],
                "currency": txn["currency"],
                "risk_score": score,
                "is_flagged": is_flagged,
                "is_fraud": txn["is_fraud"],
                "fraud_type": txn.get("fraud_type"),
                "attack_detail": txn.get("attack_detail"),
                "xai_reasons": xai_reasons,
            }
            yield {"type": "transaction", "data": txn_event}

            # Stats update every 10 txns
            if i % 10 == 0 or i == len(all_txns) - 1:
                yield {"type": "stats_update", "data": s.model_dump()}

            await asyncio.sleep(delay)

        # Final DB commit
        if db:
            await db.commit()

        # Update attack run record
        if attack_run and db:
            attack_run.total = s.total
            attack_run.approved = s.approved
            attack_run.flagged = s.flagged
            attack_run.tp = s.tp
            attack_run.fp = s.fp
            attack_run.tn = s.tn
            attack_run.fn = s.fn
            attack_run.recall = s.recall
            attack_run.precision_ = s.precision
            attack_run.f1 = s.f1
            attack_run.fpr = s.fpr
            attack_run.roi_saved = s.roi_saved
            attack_run.per_type = s.per_type
            attack_run.per_type_total = s.per_type_total
            attack_run.status = "completed"
            attack_run.completed_at = datetime.datetime.utcnow()
            await db.commit()

        # 5. Done
        yield {
            "type": "log",
            "level": "success",
            "text": (
                f"[AegisNode] Attack complete! {s.total} txns processed. "
                f"Recall: {s.recall:.1%}, Precision: {s.precision:.1%}, F1: {s.f1:.4f}"
            ),
        }
        yield {"type": "attack_end", "data": s.model_dump()}

    except Exception as e:
        if attack_run and db:
            attack_run.status = "failed"
            await db.commit()
        raise
    finally:
        attack_running = False
