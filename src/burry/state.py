"""Graph state — the shared object every node reads from and writes to.

Mirrors the pipeline:
  ingestion → (technical ∥ macro) → critic/risk → [human gate] → execution
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ProposedOrder(TypedDict):
    symbol: str
    side: str          # "buy" | "sell"
    qty: float | None
    notional: float | None
    rationale: str


class TradingState(TypedDict, total=False):
    # Inputs
    tickers: list[str]

    # Ingestion output (raw, per source)
    ohlcv: dict[str, Any]
    sentiment: dict[str, Any]
    finnhub: dict[str, Any]

    # Research (the agents run in parallel, distinct keys so
    # there is no write conflict at the fan-in)
    technical_analysis: str
    macro_analysis: str

    # Optional Massive research step (only populated when ENABLE_MASSIVE)
    massive_data: dict[str, Any]
    massive_analysis: str

    # Critic / Risk
    investment_memo: str
    proposed_orders: list[ProposedOrder]
    risk_passed: bool
    risk_violations: list[str]

    # Human approval gate
    approved: bool
    approval_note: str

    # Execution
    execution_results: list[dict[str, Any]]

    # Running log, append-only across nodes
    log: Annotated[list[str], operator.add]
