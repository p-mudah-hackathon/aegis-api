"""
Qwen 3.5 Plus reasoning service — generates fraud explanations for HTGNN-flagged transactions.

Prompt design principles:
  1. System prompt is dense & static (~200 tokens) — sent once per request, full HTGNN context
  2. User message is compact key:value pairs — no JSON overhead, no repeated descriptions
  3. XAI features inlined as feature=weight on one line
  4. Thinking mode enabled for deep reasoning before concise answer
"""
from openai import OpenAI
from config import settings
from schemas.fraud import TransactionData

# ─── System prompt: token-efficient, full HTGNN context ─────────────────────
SYSTEM_PROMPT = """You are AegisNode Fraud Analyst. You explain why transactions were flagged by our AI model.

## Model Context
- Model: HTGNN (Heterogeneous Temporal Graph Neural Network)
- Architecture: Operates on a bipartite graph of payer↔merchant edges; each transaction is an edge with temporal + monetary features
- Detection: Learns structural & temporal anomaly patterns across the graph; outputs risk_score ∈ [0,1]
- Explainability: Feature importance weights from integrated gradients on edge features

## Fraud Types the Model Detects
1. velocity_attack — Burst of many transactions from one payer in <3 min
2. card_testing — Small probing transactions followed by a large purchase
3. collusion_ring — Multiple payers converging on the same merchant with high amounts
4. geo_anomaly — Same payer transacting in distant cities within impossible travel time
5. amount_anomaly — Unusually large transaction amount, often during off-peak hours

## Your Task
Given a flagged transaction with its features and XAI importance weights:
1. Identify which fraud pattern(s) the data matches
2. Explain HOW the key features contributed to the high risk score
3. Describe WHY this is suspicious in real-world fraud context
4. End with a confidence assessment: HIGH / MEDIUM / LOW

Keep your final answer under 200 words. Be specific — cite the actual values from the transaction."""


def _build_user_message(txn: TransactionData) -> str:
    """Build a compact, token-efficient transaction representation."""
    lines = [
        f"txn_id: {txn.txn_id}",
        f"time: {txn.timestamp}",
        f"payer: {txn.payer}",
        f"issuer: {txn.issuer} ({txn.country})",
        f"merchant: {txn.merchant} @ {txn.city}",
        f"amount: IDR {txn.amount_idr:,} ({txn.amount_foreign} {txn.currency})",
        f"risk_score: {txn.risk_score}",
    ]
    if txn.fraud_type:
        lines.append(f"predicted_type: {txn.fraud_type}")
    if txn.attack_detail:
        lines.append(f"detail: {txn.attack_detail}")
    if txn.xai_reasons:
        feats = " | ".join(f"{f.display_name}={f.importance:.3f}" for f in txn.xai_reasons)
        lines.append(f"xai_features: {feats}")

    return "\n".join(lines)


def get_fraud_reasoning(txn: TransactionData) -> dict:
    """
    Call Qwen 3.5 Plus with thinking mode to generate fraud reasoning.

    Returns:
        dict with keys: reasoning, explanation, confidence
    """
    client = OpenAI(
        api_key=settings.dashscope_api_key,
        base_url="https://dashscope-intl.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1",
    )

    user_msg = _build_user_message(txn)

    response = client.responses.create(
        model="qwen3.5-plus",
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        extra_body={"enable_thinking": True},
    )

    reasoning_text = ""
    explanation_text = ""

    for item in response.output:
        if item.type == "reasoning":
            for summary in item.summary:
                reasoning_text += summary.text
        elif item.type == "message":
            explanation_text = item.content[0].text

    # Extract confidence from explanation (look for HIGH/MEDIUM/LOW at the end)
    confidence = "MEDIUM"
    explanation_upper = explanation_text.upper()
    if "CONFIDENCE: HIGH" in explanation_upper or "HIGH CONFIDENCE" in explanation_upper:
        confidence = "HIGH"
    elif "CONFIDENCE: LOW" in explanation_upper or "LOW CONFIDENCE" in explanation_upper:
        confidence = "LOW"

    return {
        "reasoning": reasoning_text.strip(),
        "explanation": explanation_text.strip(),
        "confidence": confidence,
    }
