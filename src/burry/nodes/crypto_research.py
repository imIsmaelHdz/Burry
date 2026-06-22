"""Crypto Research Agent — Binance Futures F1-F5 protocol.

Runs as a parallel branch in the research fan-out alongside Technical and Macro.
Uses only Binance public endpoints (no API key required).

Pipeline:
  F1 — Macro context    (BTC price, Fear & Greed, dominance, funding)
  F2 — Pair scan        (top longs + shorts by RSI/EMA/funding criteria)
  F3 — Technical valid. (EMA20/50/200 + RSI(14) on 4H candles per candidate)
  F4 — Entry criteria   (>60% success threshold, 10% capital per position)
  F5 — Management rules (SL trailing, TP1 50% close, RSI-based exit)

Writes to disjoint state keys (crypto_*) so the fan-in stays conflict-free.
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from ..models import get_llm
from ..prompts import load_prompt
from ..state import TradingState


def _truncate(obj: object, limit: int = 8000) -> str:
    return json.dumps(obj, default=str)[:limit]


def crypto_research(state: TradingState) -> TradingState:
    from ..tools import binance as bn

    # ── F1: macro context ────────────────────────────────────────────────────
    try:
        macro = bn.get_macro_context()
    except Exception as exc:
        return {
            "crypto_analysis": f"(Crypto step skipped — macro fetch failed: {exc})",
            "crypto_orders":   [],
            "log": [f"WARN: crypto research skipped: {exc}"],
        }

    # ── F2: scan candidates ──────────────────────────────────────────────────
    try:
        candidates = bn.scan_candidates(top_n=50)
    except Exception as exc:
        candidates = {"longs": [], "shorts": [], "error": str(exc)}

    # ── F3: detailed 4H indicators for each candidate ───────────────────────
    detailed: dict[str, list] = {"longs": [], "shorts": []}
    for side in ("longs", "shorts"):
        for c in candidates.get(side, []):
            try:
                ind = bn.get_4h_indicators(c["symbol"], candles=220)
                detailed[side].append(ind)
            except Exception as exc:
                detailed[side].append({"symbol": c["symbol"], "error": str(exc)})

    # ── LLM: F1 → F5 analysis + order proposals ─────────────────────────────
    prompt = load_prompt("crypto_research")
    llm = get_llm(prompt.role, temperature=prompt.temperature or 0.1)

    payload = {
        "capital":    state.get("crypto_capital", 1000),  # default $1 000 if not set
        "macro":      macro,
        "candidates": candidates,
        "indicators": detailed,
    }

    resp = llm.invoke([
        SystemMessage(content=prompt.text),
        HumanMessage(content=_truncate(payload)),
    ])

    # Try to extract structured orders from the response
    crypto_orders = _parse_orders(resp.content)

    return {
        "crypto_macro":    macro,
        "crypto_data":     {"candidates": candidates, "indicators": detailed},
        "crypto_analysis": resp.content,
        "crypto_orders":   crypto_orders,
        "log": [
            f"crypto F1 bias: {macro.get('session_bias', '?')}",
            f"crypto candidates: {len(candidates.get('longs',[]))} longs, "
            f"{len(candidates.get('shorts',[]))} shorts",
            "crypto research complete",
        ],
    }


def _parse_orders(text: str) -> list[dict]:
    """Best-effort extraction of JSON order blocks from LLM output."""
    import re
    orders = []
    # Look for JSON array or individual objects in the response
    json_blocks = re.findall(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
    for block in json_blocks:
        try:
            parsed = json.loads(block)
            if isinstance(parsed, list):
                orders.extend(parsed)
        except json.JSONDecodeError:
            pass
    # Fallback: single objects
    if not orders:
        json_objs = re.findall(r"\{[^{}]*\"symbol\"[^{}]*\}", text, re.DOTALL)
        for obj in json_objs:
            try:
                orders.append(json.loads(obj))
            except json.JSONDecodeError:
                pass
    return orders
