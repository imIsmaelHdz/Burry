"""Assembles the LangGraph pipeline.

    Start
      │
      ▼
    ingestion ───────────────► (Alpaca OHLCV, sentiment, Finnhub)
      │
      ├──────────────┐         parallel research
      ▼              ▼
    technical      macro
      │              │
      └──────┬───────┘
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

from .nodes.approval import human_approval, route_after_approval
from .nodes.critic import critic_review
from .nodes.execution import execute
from .nodes.ingestion import ingest
from .nodes.research import macro_research, technical_research
from .state import TradingState


def build_graph():
    g = StateGraph(TradingState)

    g.add_node("ingestion", ingest)
    g.add_node("technical", technical_research)
    g.add_node("macro", macro_research)
    g.add_node("critic", critic_review)
    g.add_node("human_approval", human_approval)
    g.add_node("execute", execute)

    g.add_edge(START, "ingestion")

    # Fan out to the two research agents (run in parallel)…
    g.add_edge("ingestion", "technical")
    g.add_edge("ingestion", "macro")

    # …and fan back in to the critic (waits for both).
    g.add_edge("technical", "critic")
    g.add_edge("macro", "critic")

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
