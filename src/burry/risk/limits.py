"""Hardcoded Python portfolio limits.

The critic LLM writes the memo and *proposes* orders, but it does not get to
decide whether they pass risk. This module is the deterministic gate: pure
Python, fully auditable, no model judgment involved.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from ..state import ProposedOrder


def check_orders(
    proposed_orders: list[ProposedOrder],
    account: dict[str, Any],
    positions: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Return (passed, violations). `passed` is True only if violations is empty."""
    s = get_settings()
    violations: list[str] = []

    equity = account.get("equity", 0.0) or 0.0
    open_count = len(positions)

    for order in proposed_orders:
        symbol = order.get("symbol", "?")
        notional = order.get("notional")

        # Estimate notional from qty when only qty is given (needs a price feed
        # in production; left as None-aware here).
        if notional is None and order.get("qty") is not None:
            notional = order.get("qty")  # TODO: multiply by latest price

        if notional is not None:
            if notional > s.max_notional_per_order:
                violations.append(
                    f"{symbol}: order notional ${notional:,.0f} exceeds "
                    f"max ${s.max_notional_per_order:,.0f}"
                )
            if equity and notional / equity > s.max_position_pct:
                violations.append(
                    f"{symbol}: position {notional / equity:.1%} of equity exceeds "
                    f"cap {s.max_position_pct:.0%}"
                )

    held = {p["symbol"] for p in positions}
    new_buys = {
        o["symbol"] for o in proposed_orders if o.get("side", "").lower() == "buy"
    }
    if open_count + len(new_buys - held) > s.max_open_positions:
        violations.append(
            f"would exceed max open positions ({s.max_open_positions})"
        )

    return (len(violations) == 0, violations)
