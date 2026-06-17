"""Massive.com market-data client (optional extra research source).

Massive (https://massive.com) is a Polygon-style financial data API covering
stocks, options, crypto, forex, indices, fundamentals, news-with-sentiment, and
macroeconomic indicators. It is wired in as an *optional* third research agent;
see ENABLE_MASSIVE in config and nodes/massive_research.py.

Lazily constructed so importing this module never requires the SDK or a key.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Any

from ..config import get_settings


@lru_cache
def _client():
    from massive import RESTClient

    return RESTClient(api_key=get_settings().massive_api_key)


def fetch_ohlcv(tickers: list[str], lookback_days: int = 90) -> dict[str, Any]:
    """Daily OHLC aggregate bars per ticker."""
    client = _client()
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    end = date.today().isoformat()

    out: dict[str, Any] = {}
    for symbol in tickers:
        bars = [
            {
                "t": getattr(a, "timestamp", None),
                "o": getattr(a, "open", None),
                "h": getattr(a, "high", None),
                "l": getattr(a, "low", None),
                "c": getattr(a, "close", None),
                "v": getattr(a, "volume", None),
            }
            for a in client.list_aggs(
                ticker=symbol,
                multiplier=1,
                timespan="day",
                from_=start,
                to=end,
                limit=50_000,
            )
        ]
        out[symbol] = bars
    return out


def fetch_news(tickers: list[str], limit: int = 20) -> dict[str, Any]:
    """Recent news articles with Massive's own sentiment scoring."""
    client = _client()
    out: dict[str, Any] = {}
    for symbol in tickers:
        articles = []
        for n in client.list_ticker_news(ticker=symbol, limit=limit):
            articles.append(
                {
                    "title": getattr(n, "title", None),
                    "published_utc": getattr(n, "published_utc", None),
                    "insights": getattr(n, "insights", None),  # sentiment payload
                }
            )
        out[symbol] = articles
    return out


def fetch_fundamentals(tickers: list[str]) -> dict[str, Any]:
    """Ticker overview / reference + financials where available."""
    client = _client()
    out: dict[str, Any] = {}
    for symbol in tickers:
        try:
            details = client.get_ticker_details(symbol)
            out[symbol] = getattr(details, "__dict__", details)
        except Exception as exc:  # be tolerant — this is an optional enrichment
            out[symbol] = {"error": str(exc)}
    return out


def fetch_macro() -> dict[str, Any]:
    """Macroeconomic indicators (the Economy category) for the macro view.

    Endpoint surface varies by plan; kept best-effort so a missing entitlement
    never breaks the optional step.
    """
    client = _client()
    try:
        return {"inflation": list(client.list_inflation())}  # type: ignore[attr-defined]
    except Exception as exc:
        return {"error": str(exc)}
