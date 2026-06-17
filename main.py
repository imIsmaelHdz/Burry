"""CLI entry point: run one orchestration cycle with a human-in-the-loop pause.

    python main.py AAPL MSFT NVDA

The graph runs ingestion → research → critic, then pauses at the approval gate.
You're shown the memo + proposed orders + risk result, and you type y/n to
resume into (or skip) execution.
"""

from __future__ import annotations

import json
import sys
import uuid

from langgraph.types import Command

from src.burry.graph import graph


def main(tickers: list[str]) -> None:
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    # 1) Run until the interrupt at the human approval gate.
    result = graph.invoke({"tickers": tickers}, config=config)

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
    print(json.dumps(payload.get("proposed_orders"), indent=2, default=str))
    print(f"\nRISK PASSED: {payload.get('risk_passed')}")
    if payload.get("risk_violations"):
        print("VIOLATIONS:", payload["risk_violations"])
    print("=" * 70)

    # 2) Human decision → resume.
    answer = input("\nApprove and execute? [y/N] ").strip().lower()
    note = "" if answer == "y" else "rejected at CLI gate"

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
    args = sys.argv[1:] or ["AAPL"]
    main(args)
