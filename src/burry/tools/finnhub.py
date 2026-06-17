"""Finnhub: company fundamentals, news, and basic financials."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..config import get_settings


@lru_cache
def _client():
    import finnhub

    return finnhub.Client(api_key=get_settings().finnhub_api_key)


def fetch_company_data(tickers: list[str]) -> dict[str, Any]:
    client = _client()
    out: dict[str, Any] = {}
    for symbol in tickers:
        out[symbol] = {
            "profile": client.company_profile2(symbol=symbol),
            "metrics": client.company_basic_financials(symbol, "all").get("metric", {}),
            "recommendation": client.recommendation_trends(symbol),
        }
    return out
