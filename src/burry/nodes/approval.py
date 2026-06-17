"""Human Approval Gate.

Uses LangGraph's dynamic `interrupt`: execution pauses here and surfaces the memo
+ proposed orders + risk result to the operator. The graph resumes when you send
a `Command(resume=...)` with your decision (see main.py).
"""

from __future__ import annotations

from langgraph.types import interrupt

from ..state import TradingState


def human_approval(state: TradingState) -> TradingState:
    decision = interrupt(
        {
            "investment_memo": state.get("investment_memo"),
            "proposed_orders": state.get("proposed_orders"),
            "risk_passed": state.get("risk_passed"),
            "risk_violations": state.get("risk_violations"),
            "prompt": "Approve these orders? Resume with "
            "{'approved': bool, 'note': str}.",
        }
    )

    # `decision` is whatever the caller passed to Command(resume=...).
    approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
    note = decision.get("note", "") if isinstance(decision, dict) else ""

    return {
        "approved": approved,
        "approval_note": note,
        "log": [f"human gate: {'APPROVED' if approved else 'REJECTED'}"],
    }


def route_after_approval(state: TradingState) -> str:
    """Only execute when a human approved AND the risk gate passed."""
    if state.get("approved") and state.get("risk_passed"):
        return "execute"
    return "end"
