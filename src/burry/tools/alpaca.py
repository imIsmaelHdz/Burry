"""Alpaca clients: OHLCV market data (in) and order execution (out).

Uses alpaca-py. Lazily constructed so importing this module never requires keys.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from ..config import get_settings


@lru_cache
def _data_client():
    from alpaca.data.historical import StockHistoricalDataClient

    s = get_settings()
    return StockHistoricalDataClient(s.alpaca_api_key, s.alpaca_secret_key)


@lru_cache
def _trading_client():
    from alpaca.trading.client import TradingClient

    s = get_settings()
    return TradingClient(s.alpaca_api_key, s.alpaca_secret_key, paper=s.alpaca_paper)


def fetch_ohlcv(tickers: list[str], lookback_days: int = 90) -> dict[str, Any]:
    """Daily bars for each ticker over the lookback window."""
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    req = StockBarsRequest(
        symbol_or_symbols=tickers,
        timeframe=TimeFrame.Day,
        start=datetime.now(timezone.utc) - timedelta(days=lookback_days),
    )
    bars = _data_client().get_stock_bars(req)
    # bars.df is a multi-index (symbol, timestamp) DataFrame
    return {"bars": bars.df.reset_index().to_dict(orient="records")}


def get_account() -> dict[str, Any]:
    acct = _trading_client().get_account()
    return {
        "equity": float(acct.equity),
        "cash": float(acct.cash),
        "buying_power": float(acct.buying_power),
    }


def get_positions() -> list[dict[str, Any]]:
    return [
        {
            "symbol": p.symbol,
            "qty": float(p.qty),
            "market_value": float(p.market_value),
        }
        for p in _trading_client().get_all_positions()
    ]


def submit_order(
    symbol: str,
    side: str,
    qty: float | None = None,
    notional: float | None = None,
) -> dict[str, Any]:
    """Submit a market order. Provide exactly one of qty / notional."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    order = MarketOrderRequest(
        symbol=symbol,
        side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        qty=qty,
        notional=notional,
    )
    submitted = _trading_client().submit_order(order)
    return {
        "id": str(submitted.id),
        "symbol": submitted.symbol,
        "side": str(submitted.side),
        "status": str(submitted.status),
        "qty": submitted.qty,
        "notional": submitted.notional,
    }
