"""Critic / Risk Node.

Compiles the two research streams into a single Investment Memo with concrete
proposed orders, then runs the deterministic, hardcoded portfolio limits over
those orders. The LLM proposes; risk/limits.py disposes.
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..models import get_llm
from ..prompts import load_prompt
from ..risk import limits
from ..state import TradingState
from ..tools import alpaca


class _Order(BaseModel):
    symbol: str
    side: str = Field(description='"buy" or "sell"')
    qty: float | None = Field(default=None, description="share quantity, or null")
    notional: float | None = Field(default=None, description="dollar amount, or null")
    rationale: str


class _Memo(BaseModel):
    memo: str = Field(description="the full investment memo, markdown")
    orders: list[_Order] = Field(description="concrete proposed orders")


def critic_review(state: TradingState) -> TradingState:
    prompt = load_prompt("critic")
    llm = get_llm(prompt.role, temperature=prompt.temperature or 0.1).with_structured_output(
        _Memo
    )

    payload = {
        "tickers": state["tickers"],
        "technical_analysis": state.get("technical_analysis"),
        "macro_analysis": state.get("macro_analysis"),
    }
    # Optional Massive second-opinion, included only when that step ran.
    if state.get("massive_analysis"):
        payload["massive_analysis"] = state["massive_analysis"]
    result: _Memo = llm.invoke(
        [
            SystemMessage(content=prompt.text),
            HumanMessage(content=json.dumps(payload, default=str)),
        ]
    )

    proposed = [o.model_dump() for o in result.orders]

    # Deterministic risk gate.
    try:
        account = alpaca.get_account()
        positions = alpaca.get_positions()
    except Exception as exc:  # keep the graph running offline / without keys
        account, positions = {"equity": 0.0}, []
        log_extra = [f"WARN: could not load account/positions: {exc}"]
    else:
        log_extra = []

    passed, violations = limits.check_orders(proposed, account, positions)

    return {
        "investment_memo": result.memo,
        "proposed_orders": proposed,
        "risk_passed": passed,
        "risk_violations": violations,
        "log": ["critic memo compiled", f"risk check: {'PASS' if passed else 'FAIL'}"]
        + log_extra,
    }
