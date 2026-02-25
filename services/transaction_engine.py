"""
Transaction generators for attack simulation.
Moved from aegis-ai/server.py — pure data generation, no model interaction.
"""
import hashlib
import numpy as np
import secrets
from datetime import datetime, timedelta

# ── Constants ────────────────────────────────────────────────────────────────
ISSUERS = {
    "Alipay_CN":    {"country": "CN", "currency": "CNY", "rate": 2450.0},
    "WeChat_CN":    {"country": "CN", "currency": "CNY", "rate": 2450.0},
    "UnionPay_CN":  {"country": "CN", "currency": "CNY", "rate": 2450.0},
    "JPQR_JP":      {"country": "JP", "currency": "JPY", "rate": 107.0},
    "PayPay_JP":    {"country": "JP", "currency": "JPY", "rate": 107.0},
    "KakaoPay_KR":  {"country": "KR", "currency": "KRW", "rate": 11.6},
    "GrabPay_SG":   {"country": "SG", "currency": "SGD", "rate": 12200.0},
    "TouchNGo_MY":  {"country": "MY", "currency": "MYR", "rate": 3550.0},
    "PromptPay_TH": {"country": "TH", "currency": "THB", "rate": 455.0},
}

MERCHANT_NAMES = [
    "Bali Beach Resort", "Jakarta Mall", "Surabaya Electronics",
    "Yogya Batik Center", "Denpasar Jewelry", "Bandung Cafe",
    "Medan Food Court", "Semarang Market", "Makassar Seafood",
    "Lombok Surf Shop", "Ubud Art Gallery", "Kuta Night Market",
]

CITIES = [
    "Bali", "Jakarta", "Surabaya", "Yogyakarta", "Denpasar",
    "Bandung", "Medan", "Semarang", "Makassar", "Lombok",
]


# ── Helpers ──────────────────────────────────────────────────────────────────
def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


# ── Normal Transactions ─────────────────────────────────────────────────────
def gen_normal(rng: np.random.Generator, txn_id: int, base_time: datetime, run_id_prefix: str) -> dict:
    iss_name = rng.choice(list(ISSUERS.keys()))
    iss = ISSUERS[iss_name]
    amount = max(50000, min(int(rng.lognormal(12.5, 0.8)), 2000000))
    ts = base_time + timedelta(seconds=int(rng.integers(0, 3600)))
    return {
        "txn_id": f"TXN-{run_id_prefix}-{txn_id:06d}",
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "payer": _hash(f"tourist_{rng.integers(0, 5000)}")[:10],
        "issuer": iss_name,
        "country": iss["country"],
        "merchant": rng.choice(MERCHANT_NAMES),
        "city": rng.choice(CITIES),
        "amount_idr": amount,
        "amount_foreign": round(amount / iss["rate"], 2),
        "currency": iss["currency"],
        "is_fraud": False,
        "fraud_type": None,
        "attack_detail": None,
    }


# ── Velocity Attack ─────────────────────────────────────────────────────────
def gen_velocity(rng: np.random.Generator, txn_id_start: int, base_time: datetime, run_id_prefix: str) -> list:
    iss_name = rng.choice(list(ISSUERS.keys()))
    iss = ISSUERS[iss_name]
    payer = _hash(f"attacker_vel_{rng.integers(0, 1000)}")[:10]
    n = int(rng.integers(8, 13))
    txns = []
    for i in range(n):
        amount = int(rng.integers(100000, 500000))
        ts = base_time + timedelta(seconds=int(rng.integers(0, 180)))
        txns.append({
            "txn_id": f"TXN-{run_id_prefix}-{txn_id_start + i:06d}",
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "payer": payer,
            "issuer": iss_name,
            "country": iss["country"],
            "merchant": rng.choice(MERCHANT_NAMES),
            "city": rng.choice(CITIES),
            "amount_idr": amount,
            "amount_foreign": round(amount / iss["rate"], 2),
            "currency": iss["currency"],
            "is_fraud": True,
            "fraud_type": "velocity_attack",
            "attack_detail": f"{n} txns from same payer in <3min",
        })
    return txns


# ── Card Testing ─────────────────────────────────────────────────────────────
def gen_card_testing(rng: np.random.Generator, txn_id_start: int, base_time: datetime, run_id_prefix: str) -> list:
    iss_name = rng.choice(list(ISSUERS.keys()))
    iss = ISSUERS[iss_name]
    payer = _hash(f"attacker_ct_{rng.integers(0, 1000)}")[:10]
    n_probes = int(rng.integers(4, 8))
    txns = []
    for i in range(n_probes):
        amount = int(rng.integers(10000, 35000))
        ts = base_time + timedelta(seconds=int(rng.integers(0, 600)))
        txns.append({
            "txn_id": f"TXN-{run_id_prefix}-{txn_id_start + i:06d}",
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "payer": payer,
            "issuer": iss_name,
            "country": iss["country"],
            "merchant": rng.choice(MERCHANT_NAMES),
            "city": rng.choice(CITIES),
            "amount_idr": amount,
            "amount_foreign": round(amount / iss["rate"], 2),
            "currency": iss["currency"],
            "is_fraud": True,
            "fraud_type": "card_testing",
            "attack_detail": f"Probing txn #{i + 1}/{n_probes}",
        })
    big = int(rng.integers(3000000, 10000000))
    ts = base_time + timedelta(seconds=int(rng.integers(600, 900)))
    txns.append({
        "txn_id": f"TXN-{run_id_prefix}-{txn_id_start + n_probes:06d}",
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "payer": payer,
        "issuer": iss_name,
        "country": iss["country"],
        "merchant": rng.choice(MERCHANT_NAMES),
        "city": rng.choice(CITIES),
        "amount_idr": big,
        "amount_foreign": round(big / iss["rate"], 2),
        "currency": iss["currency"],
        "is_fraud": True,
        "fraud_type": "card_testing",
        "attack_detail": f"Large purchase after {n_probes} probes! {big:,} IDR",
    })
    return txns


# ── Collusion Ring ───────────────────────────────────────────────────────────
def gen_collusion(rng: np.random.Generator, txn_id_start: int, base_time: datetime, run_id_prefix: str) -> list:
    iss_name = rng.choice(list(ISSUERS.keys()))
    iss = ISSUERS[iss_name]
    target = rng.choice(MERCHANT_NAMES)
    n_members = int(rng.integers(3, 6))
    txns = []
    for m in range(n_members):
        payer = _hash(f"ring_{rng.integers(0, 1000)}_{m}")[:10]
        for i in range(int(rng.integers(2, 4))):
            amount = int(rng.integers(500000, 5000000))
            ts = base_time + timedelta(
                minutes=int(rng.integers(0, 60)),
                seconds=int(rng.integers(0, 60)),
            )
            txns.append({
                "txn_id": f"TXN-{run_id_prefix}-{txn_id_start + len(txns):06d}",
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "payer": payer,
                "issuer": iss_name,
                "country": iss["country"],
                "merchant": target,
                "city": rng.choice(CITIES),
                "amount_idr": amount,
                "amount_foreign": round(amount / iss["rate"], 2),
                "currency": iss["currency"],
                "is_fraud": True,
                "fraud_type": "collusion_ring",
                "attack_detail": f"Ring member {m + 1}/{n_members} -> {target}",
            })
    return txns


# ── Geographic Anomaly ───────────────────────────────────────────────────────
def gen_geo(rng: np.random.Generator, txn_id_start: int, base_time: datetime, run_id_prefix: str) -> list:
    iss_name = rng.choice(list(ISSUERS.keys()))
    iss = ISSUERS[iss_name]
    payer = _hash(f"attacker_geo_{rng.integers(0, 1000)}")[:10]
    cities = list(rng.choice(CITIES, size=2, replace=False))
    a1 = int(rng.integers(200000, 1500000))
    a2 = int(rng.integers(200000, 1500000))
    ts1 = base_time
    ts2 = base_time + timedelta(minutes=int(rng.integers(5, 15)))
    gap = (ts2 - ts1).seconds // 60
    return [
        {
            "txn_id": f"TXN-{run_id_prefix}-{txn_id_start:06d}",
            "timestamp": ts1.strftime("%Y-%m-%d %H:%M:%S"),
            "payer": payer,
            "issuer": iss_name,
            "country": iss["country"],
            "merchant": rng.choice(MERCHANT_NAMES),
            "city": cities[0],
            "amount_idr": a1,
            "amount_foreign": round(a1 / iss["rate"], 2),
            "currency": iss["currency"],
            "is_fraud": True,
            "fraud_type": "geo_anomaly",
            "attack_detail": f"{cities[0]} -> {cities[1]} in {gap}min",
        },
        {
            "txn_id": f"TXN-{run_id_prefix}-{txn_id_start + 1:06d}",
            "timestamp": ts2.strftime("%Y-%m-%d %H:%M:%S"),
            "payer": payer,
            "issuer": iss_name,
            "country": iss["country"],
            "merchant": rng.choice(MERCHANT_NAMES),
            "city": cities[1],
            "amount_idr": a2,
            "amount_foreign": round(a2 / iss["rate"], 2),
            "currency": iss["currency"],
            "is_fraud": True,
            "fraud_type": "geo_anomaly",
            "attack_detail": f"{cities[0]} -> {cities[1]} in {gap}min",
        },
    ]


# ── Amount Anomaly ───────────────────────────────────────────────────────────
def gen_amount(rng: np.random.Generator, txn_id_start: int, base_time: datetime, run_id_prefix: str) -> list:
    iss_name = rng.choice(list(ISSUERS.keys()))
    iss = ISSUERS[iss_name]
    payer = _hash(f"attacker_amt_{rng.integers(0, 1000)}")[:10]
    amount = int(rng.integers(5000000, 10000000))
    hour = int(rng.choice([22, 23, 0, 1, 2, 3, 4]))
    ts = base_time.replace(hour=hour, minute=int(rng.integers(0, 60)))
    return [{
        "txn_id": f"TXN-{run_id_prefix}-{txn_id_start:06d}",
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "payer": payer,
        "issuer": iss_name,
        "country": iss["country"],
        "merchant": rng.choice(MERCHANT_NAMES),
        "city": rng.choice(CITIES),
        "amount_idr": amount,
        "amount_foreign": round(amount / iss["rate"], 2),
        "currency": iss["currency"],
        "is_fraud": True,
        "fraud_type": "amount_anomaly",
        "attack_detail": f"{amount:,} IDR at {hour}:00 (off-hours)",
    }]


# ── Batch Generator ─────────────────────────────────────────────────────────
def generate_attack_batch(
    total: int = 500,
    fraud_pct: float = 0.05,
    seed: int = 42,
) -> list:
    """
    Generate a shuffled batch of normal + fraud transactions.

    Returns:
        List of transaction dicts ready for scoring.
    """
    rng = np.random.default_rng(seed)
    base_time = datetime(2026, 2, 25, 14, 0, 0)
    # Generate a truly random 4-char hex prefix to prevent duplicate IDs across runs
    run_id_prefix = secrets.token_hex(2)
    
    n_fraud_target = max(int(total * fraud_pct), 10)
    n_normal = total - n_fraud_target

    all_txns = []
    txn_id = 1

    # Normal transactions
    for _ in range(n_normal):
        all_txns.append(gen_normal(rng, txn_id, base_time, run_id_prefix))
        txn_id += 1

    # Fraud transactions — spread across all 5 types
    fpt = max(n_fraud_target // 5, 2)
    for _ in range(max(fpt // 10, 1)):
        t = gen_velocity(rng, txn_id, base_time, run_id_prefix)
        all_txns.extend(t)
        txn_id += len(t)
    for _ in range(max(fpt // 7, 1)):
        t = gen_card_testing(rng, txn_id, base_time, run_id_prefix)
        all_txns.extend(t)
        txn_id += len(t)
    for _ in range(max(fpt // 8, 1)):
        t = gen_collusion(rng, txn_id, base_time, run_id_prefix)
        all_txns.extend(t)
        txn_id += len(t)
    for _ in range(max(fpt // 2, 1)):
        t = gen_geo(rng, txn_id, base_time, run_id_prefix)
        all_txns.extend(t)
        txn_id += len(t)
    for _ in range(max(fpt, 1)):
        t = gen_amount(rng, txn_id, base_time, run_id_prefix)
        all_txns.extend(t)
        txn_id += len(t)

    rng.shuffle(all_txns)
    return all_txns
