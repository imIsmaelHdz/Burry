"""Data Ingestion Node — pulls Alpaca OHLCV, sentiment, and Finnhub data.

Alpaca is optional: when keys are missing the OHLCV and sentiment fields are
populated with empty stubs so the research agents can still run on Finnhub data.
"""

from __future__ import annotations

from ..config import get_settings
from ..state import TradingState
from ..tools import finnhub


def ingest(state: TradingState) -> TradingState:
    tickers = state["tickers"]
    s = get_settings()
    log = []

    # Alpaca OHLCV (optional)
    if s.alpaca_api_key:
        try:
            from ..tools import alpaca
            ohlcv = alpaca.fetch_ohlcv(tickers)
            log.append("ingested OHLCV from Alpaca")
        except Exception as exc:
            ohlcv = {"bars": []}
            log.append(f"WARN: Alpaca OHLCV failed: {exc}")
    else:
        ohlcv = {"bars": []}
        log.append("SKIP: Alpaca OHLCV — no API key configured")

    # Sentiment / news (optional — uses Alpaca news client)
    if s.alpaca_api_key:
        try:
            from ..tools import sentiment
            news = sentiment.fetch_sentiment(tickers)
            log.append("ingested sentiment from Alpaca news")
        except Exception as exc:
            news = {t: {"headline_count": 0, "headlines": []} for t in tickers}
            log.append(f"WARN: Alpaca sentiment failed: {exc}")
    else:
        # Fall back to Finnhub news we already fetch below
        news = {t: {"headline_count": 0, "headlines": []} for t in tickers}
        log.append("SKIP: Alpaca sentiment — will use Finnhub news instead")

    # Finnhub fundamentals (always runs)
    fundamentals = finnhub.fetch_company_data(tickers)
    log.append(f"ingested Finnhub data for {', '.join(tickers)}")

    # Backfill sentiment headlines from Finnhub news when Alpaca is absent
    if not s.alpaca_api_key:
        for ticker in tickers:
            fh_news = fundamentals.get(ticker, {}).get("news", [])
            headlines = [n["headline"] for n in fh_news if n.get("headline")]
            news[ticker] = {"headline_count": len(headlines), "headlines": headlines[:20]}

    return {
        "ohlcv": ohlcv,
        "sentiment": news,
        "finnhub": fundamentals,
        "log": log,
    }
