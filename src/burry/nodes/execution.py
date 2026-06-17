"""Alpaca Execution Node — places the approved orders and tracks results."""

from __future__ import annotations

from ..state import TradingState
from ..tools import alpaca


def execute(state: TradingState) -> TradingState:
    results = []
    for order in state.get("proposed_orders", []):
        try:
            res = alpaca.submit_order(
                symbol=order["symbol"],
                side=order["side"],
                qty=order.get("qty"),
                notional=order.get("notional"),
            )
            results.append(res)
        except Exception as exc:
            results.append({"symbol": order.get("symbol"), "error": str(exc)})

    placed = sum(1 for r in results if "error" not in r)
    return {
        "execution_results": results,
        "log": [f"execution: {placed}/{len(results)} orders placed"],
    }
