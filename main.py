"""CLI entry point: run one orchestration cycle with a human-in-the-loop pause.

Basic usage (no existing positions):
    python main.py AAPL MSFT NVDA

With existing positions (symbol:qty:entry_price:entry_date):
    python main.py NDAQ --position NDAQ:10:91.04:2025-01-15
    python main.py AAPL MSFT --position AAPL:5:195.00:2025-03-01 --position MSFT:3:415.00:2025-02-10

The graph runs ingestion → parallel research → critic (position-aware) →
human approval gate. Type y to execute, n to reject.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

from langgraph.types import Command

from src.burry.graph import graph
from src.burry.state import Position


def _parse_position(raw: str) -> Position:
    """Parse  symbol:qty:entry_price:entry_date  into a Position dict."""
    parts = raw.split(":")
    if len(parts) != 4:
        raise ValueError(
            f"Invalid position format '{raw}'. "
            "Use symbol:qty:entry_price:entry_date  e.g.  NDAQ:10:91.04:2025-01-15"
        )
    symbol, qty, price, date = parts
    qty_f   = float(qty)
    price_f = float(price)
    return Position(
        symbol=symbol.upper(),
        side="long",
        qty=qty_f,
        entry_price=price_f,
        entry_date=date,
        notional=round(qty_f * price_f, 2),
    )


def _show_positions(positions: list[Position], current_prices: dict[str, float]) -> None:
    if not positions:
        return
    print("\nCURRENT POSITIONS")
    print(f"  {'Symbol':<8} {'Qty':>6} {'Entry':>10} {'Current':>10} {'P&L':>10} {'P&L %':>8}  Since")
    print(f"  {'─'*8} {'─'*6} {'─'*10} {'─'*10} {'─'*10} {'─'*8}  {'─'*12}")
    for p in positions:
        cur = current_prices.get(p["symbol"])
        if cur:
            pnl     = (cur - p["entry_price"]) * p["qty"]
            pnl_pct = (cur / p["entry_price"] - 1) * 100
            color   = "\033[32m" if pnl >= 0 else "\033[31m"
            reset   = "\033[0m"
            print(f"  {p['symbol']:<8} {p['qty']:>6.1f} "
                  f"${p['entry_price']:>9.2f} ${cur:>9.2f} "
                  f"{color}${pnl:>+9.2f} {pnl_pct:>+7.2f}%{reset}  {p['entry_date']}")
        else:
            print(f"  {p['symbol']:<8} {p['qty']:>6.1f} ${p['entry_price']:>9.2f}  (no price)  {p['entry_date']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Burry trading orchestrator")
    parser.add_argument("tickers", nargs="+", help="Ticker symbols to research")
    parser.add_argument(
        "--position", "-p",
        action="append",
        dest="positions",
        metavar="SYMBOL:QTY:ENTRY:DATE",
        help="Existing position (repeatable). e.g. NDAQ:10:91.04:2025-01-15",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1000.0,
        help="Crypto session capital in USD (default: 1000)",
    )
    args = parser.parse_args()

    tickers   = [t.upper() for t in args.tickers]
    positions: list[Position] = []
    for raw in (args.positions or []):
        try:
            positions.append(_parse_position(raw))
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    # Fetch current prices for P&L display (best-effort via Finnhub)
    current_prices: dict[str, float] = {}
    if positions:
        try:
            import os, sys as _sys
            _sys.path.insert(0, "src")
            from dotenv import load_dotenv
            load_dotenv(".env")
            from src.burry.tools.finnhub import fetch_quote
            for p in positions:
                q = fetch_quote(p["symbol"])
                if q.get("price"):
                    current_prices[p["symbol"]] = q["price"]
        except Exception:
            pass

    _show_positions(positions, current_prices)

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    initial_state = {
        "tickers":           tickers,
        "crypto_capital":    args.capital,
        "current_positions": positions,
    }

    # 1) Run until the interrupt at the human approval gate
    result = graph.invoke(initial_state, config=config)

    interrupts = result.get("__interrupt__")
    if not interrupts:
        print("Graph finished without pausing. Final state:")
        print(json.dumps(result.get("log", []), indent=2))
        return

    payload = interrupts[0].value
    print("\n" + "=" * 70)
    print("INVESTMENT MEMO\n")
    print(payload.get("investment_memo"))
    print("\nPROPOSED ORDERS")
    orders = payload.get("proposed_orders", [])
    print(json.dumps(orders, indent=2, default=str))
    print(f"\nRISK PASSED: {payload.get('risk_passed')}")
    if payload.get("risk_violations"):
        print("VIOLATIONS:", payload["risk_violations"])

    # Show crypto analysis if available
    if result.get("crypto_analysis"):
        print("\n" + "=" * 70)
        print("CRYPTO ANALYSIS\n")
        print(result["crypto_analysis"])
        if result.get("crypto_orders"):
            print("\nCRYPTO ORDERS")
            print(json.dumps(result["crypto_orders"], indent=2, default=str))

    print("=" * 70)

    # 2) Human decision → resume
    answer = input("\nApprove and execute? [y/N] ").strip().lower()
    note   = "" if answer == "y" else "rejected at CLI gate"

    final = graph.invoke(
        Command(resume={"approved": answer == "y", "note": note}),
        config=config,
    )

    print("\nFINAL LOG")
    print(json.dumps(final.get("log", []), indent=2))
    if final.get("execution_results"):
        print("\nEXECUTION RESULTS")
        print(json.dumps(final["execution_results"], indent=2, default=str))


if __name__ == "__main__":
    main()
