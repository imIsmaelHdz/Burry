"""Data Ingestion Node — pulls Alpaca OHLCV, sentiment, and Finnhub data."""

from __future__ import annotations

from ..state import TradingState
from ..tools import alpaca, finnhub, sentiment


def ingest(state: TradingState) -> TradingState:
    tickers = state["tickers"]

    ohlcv = alpaca.fetch_ohlcv(tickers)
    news = sentiment.fetch_sentiment(tickers)
    fundamentals = finnhub.fetch_company_data(tickers)

    return {
        "ohlcv": ohlcv,
        "sentiment": news,
        "finnhub": fundamentals,
        "log": [f"ingested data for {', '.join(tickers)}"],
    }
