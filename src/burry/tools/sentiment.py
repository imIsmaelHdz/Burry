"""News sentiment.

Alpaca exposes a news endpoint; Finnhub also has news sentiment. We use Alpaca
news here and leave room to blend in other sources. Replace the scoring stub
with a real model or Finnhub's `news_sentiment` as needed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from ..config import get_settings


@lru_cache
def _news_client():
    from alpaca.data.historical.news import NewsClient

    s = get_settings()
    return NewsClient(s.alpaca_api_key, s.alpaca_secret_key)


def fetch_sentiment(tickers: list[str], lookback_days: int = 7) -> dict[str, Any]:
    from alpaca.data.requests import NewsRequest

    req = NewsRequest(
        symbols=",".join(tickers),
        start=datetime.now(timezone.utc) - timedelta(days=lookback_days),
        include_content=False,
    )
    news = _news_client().get_news(req)

    headlines: dict[str, list[str]] = {t: [] for t in tickers}
    for article in news.data.get("news", []):
        for sym in getattr(article, "symbols", []):
            if sym in headlines:
                headlines[sym].append(getattr(article, "headline", ""))

    # TODO: replace count-based stub with a real sentiment score.
    return {
        sym: {"headline_count": len(hl), "headlines": hl[:20]}
        for sym, hl in headlines.items()
    }
