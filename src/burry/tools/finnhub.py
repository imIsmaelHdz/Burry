"""Finnhub: company fundamentals, news, sentiment, and real-time quotes.

fetch_company_data() is the main entry point used by the ingestion node.
It bundles every data source the research agents need into one dict per ticker:

    {
      "profile":           company_profile2
      "metrics":           basic_financials["metric"]  (130+ KPIs)
      "recommendation":    analyst buy/hold/sell trends
      "quote":             real-time price, change, day range
      "news":              last N days of company-specific headlines
      "insider_sentiment": monthly MSPR + change scores
    }
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Any

from ..config import get_settings

# How many days of news to pull per ticker
_NEWS_LOOKBACK_DAYS = 7


@lru_cache
def _client():
    import finnhub

    return finnhub.Client(api_key=get_settings().finnhub_api_key)


def fetch_quote(symbol: str) -> dict[str, Any]:
    """Real-time quote: current price, change, day high/low, prev close."""
    q = _client().quote(symbol)
    return {
        "price":      q.get("c"),   # current
        "change":     q.get("d"),   # absolute change
        "change_pct": q.get("dp"),  # % change
        "high":       q.get("h"),
        "low":        q.get("l"),
        "open":       q.get("o"),
        "prev_close": q.get("pc"),
    }


def fetch_news(symbol: str, lookback_days: int = _NEWS_LOOKBACK_DAYS) -> list[dict[str, Any]]:
    """Recent company news headlines with source, summary, and URL."""
    today = date.today().isoformat()
    since = (date.today() - timedelta(days=lookback_days)).isoformat()
    raw = _client().company_news(symbol, _from=since, to=today)
    return [
        {
            "headline": item.get("headline"),
            "source":   item.get("source"),
            "summary":  item.get("summary"),
            "url":      item.get("url"),
            "datetime": item.get("datetime"),
        }
        for item in raw
    ]


def fetch_insider_sentiment(symbol: str, lookback_days: int = 180) -> list[dict[str, Any]]:
    """Monthly insider sentiment (MSPR score + net change) over lookback window."""
    today = date.today().isoformat()
    since = (date.today() - timedelta(days=lookback_days)).isoformat()
    data = _client().stock_insider_sentiment(symbol, since, today)
    return data.get("data", [])


def fetch_company_data(
    tickers: list[str],
    news_days: int = _NEWS_LOOKBACK_DAYS,
    insider_days: int = 180,
) -> dict[str, Any]:
    """Full data bundle per ticker for the ingestion node.

    Args:
        tickers:      List of ticker symbols.
        news_days:    How many days of news headlines to include.
        insider_days: Lookback window for insider sentiment.

    Returns:
        Dict keyed by ticker symbol, each value containing:
        profile, metrics, recommendation, quote, news, insider_sentiment.
    """
    client = _client()
    out: dict[str, Any] = {}
    for symbol in tickers:
        out[symbol] = {
            "profile":           client.company_profile2(symbol=symbol),
            "metrics":           client.company_basic_financials(symbol, "all").get("metric", {}),
            "recommendation":    client.recommendation_trends(symbol),
            "quote":             fetch_quote(symbol),
            "news":              fetch_news(symbol, lookback_days=news_days),
            "insider_sentiment": fetch_insider_sentiment(symbol, lookback_days=insider_days),
        }
    return out
