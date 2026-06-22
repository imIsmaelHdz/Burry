"""Binance public market data — no API key required.

Provides everything the crypto research agent needs for the F1-F5 protocol:
  - BTC macro context (price, funding rate)
  - Fear & Greed Index (via alternative.me)
  - BTC dominance (via CoinGecko)
  - Top perpetual futures candidates (price, funding, volume)
  - OHLCV klines for EMA + RSI computation
  - Computed EMA20 / EMA50 / EMA200 and RSI(14) from 4H candles
"""

from __future__ import annotations

import math
from typing import Any

import requests

_BINANCE_BASE = "https://fapi.binance.com"       # Futures API
_BINANCE_SPOT = "https://api.binance.com"
_FEAR_GREED   = "https://api.alternative.me/fng/"
_COINGECKO    = "https://api.coingecko.com/api/v3"

_TIMEOUT = 10  # seconds


# ── helpers ──────────────────────────────────────────────────────────────────

def _get(url: str, params: dict | None = None) -> Any:
    r = requests.get(url, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _ema(values: list[float], period: int) -> list[float]:
    """Exponential moving average."""
    if len(values) < period:
        return [float("nan")] * len(values)
    k = 2 / (period + 1)
    result: list[float] = [float("nan")] * (period - 1)
    result.append(sum(values[:period]) / period)   # seed with SMA
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def _rsi(closes: list[float], period: int = 14) -> list[float]:
    """Wilder RSI."""
    if len(closes) < period + 1:
        return [float("nan")] * len(closes)
    result: list[float] = [float("nan")] * period
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        result.append(100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(100 - 100 / (1 + rs))
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gain = max(diff, 0)
        loss = max(-diff, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - 100 / (1 + rs))
    return result


# ── F1: macro context ─────────────────────────────────────────────────────────

def get_btc_price() -> dict[str, Any]:
    """Current BTC/USDT price and 24h change from Binance spot."""
    data = _get(f"{_BINANCE_SPOT}/api/v3/ticker/24hr", {"symbol": "BTCUSDT"})
    return {
        "price":      float(data["lastPrice"]),
        "change_pct": float(data["priceChangePercent"]),
        "high_24h":   float(data["highPrice"]),
        "low_24h":    float(data["lowPrice"]),
        "volume_24h": float(data["quoteVolume"]),
    }


def get_fear_greed() -> dict[str, Any]:
    """Crypto Fear & Greed Index (0=extreme fear, 100=extreme greed)."""
    data = _get(_FEAR_GREED, {"limit": 1})
    entry = data["data"][0]
    return {
        "value":       int(entry["value"]),
        "label":       entry["value_classification"],   # e.g. "Greed"
        "timestamp":   entry["timestamp"],
    }


def get_btc_dominance() -> dict[str, Any]:
    """BTC market dominance % from CoinGecko."""
    data = _get(f"{_COINGECKO}/global")
    pct = data["data"]["market_cap_percentage"].get("btc", 0)
    return {"btc_dominance_pct": round(pct, 2)}


def get_btc_funding_rate() -> dict[str, Any]:
    """Current funding rate for BTCUSDT perpetual."""
    data = _get(f"{_BINANCE_BASE}/fapi/v1/fundingRate", {
        "symbol": "BTCUSDT", "limit": 1
    })
    rate = float(data[0]["fundingRate"]) * 100  # convert to %
    return {
        "funding_rate_pct": round(rate, 4),
        "label": "positive (longs pay)" if rate > 0 else "negative (shorts pay)",
    }


def get_macro_context() -> dict[str, Any]:
    """Full F1 macro snapshot: BTC price + F&G + dominance + funding."""
    btc     = get_btc_price()
    fg      = get_fear_greed()
    dom     = get_btc_dominance()
    funding = get_btc_funding_rate()

    # Derive session bias
    fg_val = fg["value"]
    change = btc["change_pct"]
    if fg_val >= 60 and change > 0:
        bias = "risk-on"
    elif fg_val <= 40 or change < -2:
        bias = "risk-off"
    else:
        bias = "neutral"

    return {
        "btc":      btc,
        "fear_greed": fg,
        "dominance":  dom,
        "funding":    funding,
        "session_bias": bias,
    }


# ── F2: pair scanning ─────────────────────────────────────────────────────────

def get_top_futures_tickers(limit: int = 50) -> list[dict[str, Any]]:
    """Top perpetual futures by 24h quote volume."""
    data = _get(f"{_BINANCE_BASE}/fapi/v1/ticker/24hr")
    usdt = [
        {
            "symbol":     d["symbol"],
            "price":      float(d["lastPrice"]),
            "change_pct": float(d["priceChangePercent"]),
            "volume_24h": float(d["quoteVolume"]),
        }
        for d in data
        if d["symbol"].endswith("USDT") and float(d["quoteVolume"]) > 0
    ]
    return sorted(usdt, key=lambda x: x["volume_24h"], reverse=True)[:limit]


def get_funding_rates(symbols: list[str] | None = None) -> dict[str, float]:
    """Current funding rates for a list of symbols (or all if None)."""
    data = _get(f"{_BINANCE_BASE}/fapi/v1/premiumIndex")
    rates: dict[str, float] = {}
    for item in data:
        sym = item["symbol"]
        if symbols and sym not in symbols:
            continue
        if item.get("lastFundingRate"):
            rates[sym] = round(float(item["lastFundingRate"]) * 100, 4)
    return rates


# ── F3: technical indicators ──────────────────────────────────────────────────

def get_4h_indicators(symbol: str, candles: int = 250) -> dict[str, Any]:
    """OHLCV + EMA20/50/200 + RSI(14) from 4H candles for a symbol.

    Returns the latest values plus recent candle context.
    """
    raw = _get(f"{_BINANCE_BASE}/fapi/v1/klines", {
        "symbol":   symbol,
        "interval": "4h",
        "limit":    candles,
    })

    opens   = [float(c[1]) for c in raw]
    highs   = [float(c[2]) for c in raw]
    lows    = [float(c[3]) for c in raw]
    closes  = [float(c[4]) for c in raw]
    volumes = [float(c[5]) for c in raw]

    ema20  = _ema(closes, 20)
    ema50  = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    rsi14  = _rsi(closes, 14)

    price   = closes[-1]
    e20     = ema20[-1]
    e50     = ema50[-1]
    e200    = ema200[-1]
    rsi     = rsi14[-1]

    # EMA alignment checks
    above_ema20  = price > e20
    above_ema50  = price > e50
    above_ema200 = price > e200

    # RSI zone
    if rsi >= 70:
        rsi_zone = "overbought"
    elif rsi <= 30:
        rsi_zone = "oversold"
    elif 40 <= rsi <= 60:
        rsi_zone = "neutral (40-60)"
    elif rsi < 40:
        rsi_zone = "weak"
    else:
        rsi_zone = "strong"

    # Simple long/short/no-enter signal following the protocol
    long_signal  = (40 <= rsi <= 60) and above_ema20 and above_ema50
    short_signal = (rsi > 70) and not above_ema200

    # Recent 3 candles for context
    recent = [
        {"open": opens[i], "high": highs[i], "low": lows[i],
         "close": closes[i], "volume": volumes[i]}
        for i in range(-3, 0)
    ]

    return {
        "symbol":       symbol,
        "price":        price,
        "ema20":        round(e20, 4),
        "ema50":        round(e50, 4),
        "ema200":       round(e200, 4),
        "rsi":          round(rsi, 2),
        "rsi_zone":     rsi_zone,
        "above_ema20":  above_ema20,
        "above_ema50":  above_ema50,
        "above_ema200": above_ema200,
        "long_signal":  long_signal,
        "short_signal": short_signal,
        "recent_candles": recent,
    }


def scan_candidates(top_n: int = 50) -> dict[str, list[dict[str, Any]]]:
    """F2 scan: return top 2 long and top 2 short candidates from top_n futures.

    Long criteria:  RSI 40-60, price above EMA20+EMA50, funding negative/neutral
    Short criteria: RSI >70, price below EMA200, funding positive
    """
    tickers  = get_top_futures_tickers(top_n)
    symbols  = [t["symbol"] for t in tickers]
    fundings = get_funding_rates(symbols)

    longs:  list[dict] = []
    shorts: list[dict] = []

    for ticker in tickers:
        sym = ticker["symbol"]
        # Skip stablecoins and leveraged tokens
        if any(x in sym for x in ["BUSD", "USDC", "DOWN", "UP", "BEAR", "BULL"]):
            continue
        try:
            ind = get_4h_indicators(sym, candles=220)
        except Exception:
            continue

        funding = fundings.get(sym, 0.0)
        rsi     = ind["rsi"]

        if ind["long_signal"] and funding <= 0.01:
            longs.append({**ind, "funding_rate_pct": funding, **ticker})
        elif ind["short_signal"] and funding > 0:
            shorts.append({**ind, "funding_rate_pct": funding, **ticker})

        if len(longs) >= 2 and len(shorts) >= 2:
            break

    return {
        "longs":  longs[:2],
        "shorts": shorts[:2],
    }
