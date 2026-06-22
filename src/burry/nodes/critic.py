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


class _Order(BaseModel):
    symbol: str
    side: str = Field(description='"buy" or "sell"')
    action: str = Field(description='"open" | "add" | "trim" | "exit" | "hold"', default="open")
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
        "tickers":            state["tickers"],
        "technical_analysis": state.get("technical_analysis"),
        "macro_analysis":     state.get("macro_analysis"),
    }
    # Existing positions — give the critic full context on open holdings
    if state.get("current_positions"):
        payload["current_positions"] = state["current_positions"]
    # Earnings calendar — flag overnight risk
    if state.get("earnings_calendar"):
        payload["earnings_calendar"] = state["earnings_calendar"]
    # Optional Massive second-opinion
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
    # Account/positions are optional — graph keeps running without Alpaca keys.
    try:
        from ..tools import alpaca as _alpaca
        account = _alpaca.get_account()
        positions = _alpaca.get_positions()
        log_extra = []
    except Exception as exc:
        account, positions = {"equity": 0.0}, []
        log_extra = [f"WARN: Alpaca account unavailable — risk check uses zero equity: {exc}"]

    passed, violations = limits.check_orders(proposed, account, positions)

    return {
        "investment_memo": result.memo,
        "proposed_orders": proposed,
        "risk_passed": passed,
        "risk_violations": violations,
        "log": ["critic memo compiled", f"risk check: {'PASS' if passed else 'FAIL'}"]
        + log_extra,
    }
