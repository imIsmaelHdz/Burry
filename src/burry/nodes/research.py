"""Technical & Macro Research Agents.

Two independent LLM agents that run in parallel (the graph fans out from
ingestion to both). They write to disjoint state keys so the fan-in is
conflict-free.
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from ..models import get_llm
from ..prompts import load_prompt
from ..state import TradingState


def _truncate(obj, limit: int = 6000) -> str:
    return json.dumps(obj, default=str)[:limit]


def technical_research(state: TradingState) -> TradingState:
    prompt = load_prompt("technical_research")
    llm = get_llm(prompt.role, temperature=prompt.temperature or 0.2)
    payload = {
        "tickers": state["tickers"],
        "ohlcv": state.get("ohlcv"),
        "sentiment": state.get("sentiment"),
    }
    resp = llm.invoke(
        [
            SystemMessage(content=prompt.text),
            HumanMessage(content=_truncate(payload)),
        ]
    )
    return {
        "technical_analysis": resp.content,
        "log": ["technical research complete"],
    }


def macro_research(state: TradingState) -> TradingState:
    prompt = load_prompt("macro_research")
    llm = get_llm(prompt.role, temperature=prompt.temperature or 0.2)
    payload = {
        "tickers": state["tickers"],
        "finnhub": state.get("finnhub"),
        "sentiment": state.get("sentiment"),
    }
    resp = llm.invoke(
        [
            SystemMessage(content=prompt.text),
            HumanMessage(content=_truncate(payload)),
        ]
    )
    return {
        "macro_analysis": resp.content,
        "log": ["macro research complete"],
    }
