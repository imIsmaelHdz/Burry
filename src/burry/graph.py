"""Assembles the LangGraph pipeline.

    Start
      │
      ▼
    ingestion ───────────────► (Alpaca OHLCV, sentiment, Finnhub)
      │
      ├──────────────┐         parallel research
      ▼              ▼
    technical      macro      (massive)   ← optional, ENABLE_MASSIVE
      │              │            │
      └──────┬───────┴────────────┘
             ▼
          critic ────────────► investment memo + hardcoded risk limits
             │
             ▼
       human_approval ───────► interrupt — graph pauses for approval
             │
       (approved & risk ok)
             ▼
         execution ──────────► places orders on Alpaca
             │
             ▼
            End
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .config import get_settings
from .nodes.approval import human_approval, route_after_approval
from .nodes.critic import critic_review
from .nodes.execution import execute
from .nodes.ingestion import ingest
from .nodes.research import macro_research, technical_research
from .state import TradingState


def build_graph():
    settings = get_settings()
    g = StateGraph(TradingState)

    g.add_node("ingestion", ingest)
    g.add_node("technical", technical_research)
    g.add_node("macro", macro_research)
    g.add_node("critic", critic_review)
    g.add_node("human_approval", human_approval)
    g.add_node("execute", execute)

    g.add_edge(START, "ingestion")

    # Fan out to the research agents (run in parallel)…
    g.add_edge("ingestion", "technical")
    g.add_edge("ingestion", "macro")

    # …and fan back in to the critic (waits for all of them).
    g.add_edge("technical", "critic")
    g.add_edge("macro", "critic")

    # Optional extra research step: Massive runs as a third parallel agent only
    # when enabled. Off by default, so the base flow is untouched.
    if settings.enable_massive:
        from .nodes.massive_research import massive_research

        g.add_node("massive", massive_research)
        g.add_edge("ingestion", "massive")
        g.add_edge("massive", "critic")

    # Optional crypto research step: Binance Futures F1-F5 protocol
    if settings.enable_crypto:
        from .nodes.crypto_research import crypto_research

        g.add_node("crypto", crypto_research)
        g.add_edge("ingestion", "crypto")
        g.add_edge("crypto", "critic")

    g.add_edge("critic", "human_approval")

    g.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {"execute": "execute", "end": END},
    )
    g.add_edge("execute", END)

    return g


# A checkpointer is required for `interrupt`/resume to work.
# For production, swap MemorySaver for a SqliteSaver/PostgresSaver.
graph = build_graph().compile(checkpointer=MemorySaver())
