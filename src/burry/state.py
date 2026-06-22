"""Graph state — the shared object every node reads from and writes to.

Mirrors the pipeline:
  ingestion → (technical ∥ macro) → critic/risk → [human gate] → execution
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class Position(TypedDict):
    """A manually declared existing holding passed into the graph at runtime."""
    symbol:      str
    side:        str        # "long" | "short"
    qty:         float
    entry_price: float
    entry_date:  str        # ISO date string, e.g. "2025-01-15"
    notional:    float      # qty * entry_price


class ProposedOrder(TypedDict):
    symbol:    str
    side:      str          # "buy" | "sell"
    action:    str          # "open" | "add" | "trim" | "exit" | "hold"
    qty:       float | None
    notional:  float | None
    rationale: str


class CryptoOrder(TypedDict):
    symbol:      str
    side:        str            # "long" | "short"
    leverage:    int
    notional:    float          # 10% of declared capital
    entry_price: float
    sl:          float
    tp1:         float
    tp2:         float
    rationale:   str
    success_pct: float


class TradingState(TypedDict, total=False):
    # Inputs
    tickers: list[str]
    crypto_capital: float       # declared capital for the crypto session
    current_positions: list[Position]  # manually declared existing holdings

    # Ingestion output (raw, per source)
    ohlcv:             dict[str, Any]
    sentiment:         dict[str, Any]
    finnhub:           dict[str, Any]
    earnings_calendar: dict[str, Any]   # upcoming earnings per ticker (14-day window)

    # Research (the agents run in parallel, distinct keys so
    # there is no write conflict at the fan-in)
    technical_analysis: str
    macro_analysis: str

    # Optional Massive research step (only populated when ENABLE_MASSIVE)
    massive_data: dict[str, Any]
    massive_analysis: str

    # Crypto research (Binance Futures F1-F5, only when ENABLE_CRYPTO)
    crypto_macro:    dict[str, Any]   # F1 macro snapshot
    crypto_data:     dict[str, Any]   # F2-F3 candidates + indicators
    crypto_analysis: str              # full F1-F5 LLM analysis
    crypto_orders:   list[CryptoOrder]

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
