"""Massive Research Agent — optional extra step in the research fan-out.

Only added to the graph when ENABLE_MASSIVE is true (see graph.py). Pulls a
richer Massive.com dataset and produces a "second opinion" analysis that the
critic folds in alongside the Technical and Macro views. Writes to its own
state key so the fan-in stays conflict-free.
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from ..models import get_llm
from ..prompts import load_prompt
from ..state import TradingState
from ..tools import massive


def _truncate(obj, limit: int = 6000) -> str:
    return json.dumps(obj, default=str)[:limit]


def massive_research(state: TradingState) -> TradingState:
    tickers = state["tickers"]

    # Best-effort fetch — this is an optional enrichment, so a failure here must
    # not sink the whole cycle.
    try:
        data = {
            "ohlcv": massive.fetch_ohlcv(tickers),
            "news": massive.fetch_news(tickers),
            "fundamentals": massive.fetch_fundamentals(tickers),
            "macro": massive.fetch_macro(),
        }
    except Exception as exc:
        return {
            "massive_analysis": f"(Massive step skipped: {exc})",
            "log": [f"WARN: massive research skipped: {exc}"],
        }

    prompt = load_prompt("massive_research")
    llm = get_llm(prompt.role, temperature=prompt.temperature or 0.2)
    resp = llm.invoke(
        [
            SystemMessage(content=prompt.text),
            HumanMessage(content=_truncate({"tickers": tickers, **data})),
        ]
    )
    return {
        "massive_data": data,
        "massive_analysis": resp.content,
        "log": ["massive research complete"],
    }
