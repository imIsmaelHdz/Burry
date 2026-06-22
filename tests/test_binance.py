"""Integration tests for the Binance/crypto data layer.

Hits all four real endpoints — no mocking, no API keys required.
Covers every public function in src/burry/tools/binance.py plus
the internal EMA and RSI math.

Run with:
    pytest tests/test_binance.py -v -s
"""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


# Module-level fixture — CoinGecko is called exactly ONCE for the whole suite.
# This avoids 429s from the free-tier rate limit (~30 req/min).
@pytest.fixture(scope="module")
def btc_dominance_data():
    import time
    time.sleep(2)   # brief pause to avoid rate limit from prior test runs
    from burry.tools.binance import get_btc_dominance
    return get_btc_dominance()


@pytest.fixture(scope="module")
def macro_data():
    from burry.tools.binance import get_macro_context
    return get_macro_context()


# ===========================================================================
# 1. Connectivity — one ping per external host before anything else
# ===========================================================================

class TestConnectivity:
    def test_binance_spot_reachable(self):
        import requests
        r = requests.get("https://api.binance.com/api/v3/ping", timeout=8)
        assert r.status_code == 200, f"Binance spot ping failed: {r.status_code}"
        print("\n  Binance Spot → 200 ✓")

    def test_binance_futures_reachable(self):
        import requests
        r = requests.get("https://fapi.binance.com/fapi/v1/ping", timeout=8)
        assert r.status_code == 200, f"Binance futures ping failed: {r.status_code}"
        print("\n  Binance Futures → 200 ✓")

    def test_alternative_me_reachable(self):
        import requests
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8)
        assert r.status_code == 200
        print("\n  alternative.me → 200 ✓")

    def test_coingecko_reachable(self):
        import requests, time
        time.sleep(2)
        r = requests.get("https://api.coingecko.com/api/v3/ping", timeout=8)
        assert r.status_code in (200, 429), f"Unexpected status: {r.status_code}"
        if r.status_code == 429:
            pytest.skip("CoinGecko rate-limited during connectivity check — API is reachable")
        print("\n  CoinGecko → 200 ✓")


# ===========================================================================
# 2. Internal math — EMA and RSI (no network)
# ===========================================================================

class TestInternalMath:
    def test_ema_length_matches_input(self):
        from burry.tools.binance import _ema
        data = list(range(1, 26))   # 25 values
        result = _ema(data, 20)
        assert len(result) == len(data)

    def test_ema_first_values_are_nan(self):
        from burry.tools.binance import _ema
        result = _ema(list(range(1, 26)), 20)
        assert all(math.isnan(v) for v in result[:19])
        assert not math.isnan(result[19])   # seed SMA at index 19

    def test_ema_too_short_input(self):
        from burry.tools.binance import _ema
        result = _ema([1.0, 2.0], 20)
        assert all(math.isnan(v) for v in result)

    def test_ema_values_are_numeric(self):
        from burry.tools.binance import _ema
        closes = [float(i) for i in range(1, 51)]
        result = _ema(closes, 20)
        non_seed = [v for v in result if not math.isnan(v)]
        assert all(isinstance(v, float) for v in non_seed)

    def test_rsi_length_matches_input(self):
        from burry.tools.binance import _rsi
        closes = [float(i) for i in range(1, 31)]
        result = _rsi(closes, 14)
        assert len(result) == len(closes)

    def test_rsi_first_values_are_nan(self):
        from burry.tools.binance import _rsi
        closes = [float(i) for i in range(1, 31)]
        result = _rsi(closes, 14)
        assert all(math.isnan(v) for v in result[:14])
        assert not math.isnan(result[14])

    def test_rsi_range(self):
        """RSI must always be 0–100."""
        from burry.tools.binance import _rsi
        import random
        random.seed(42)
        closes = [100.0 + random.uniform(-5, 5) for _ in range(100)]
        result = _rsi(closes, 14)
        for v in result:
            if not math.isnan(v):
                assert 0.0 <= v <= 100.0, f"RSI out of range: {v}"

    def test_rsi_constant_series_is_100(self):
        """All-same prices → no losses → RSI should be 100."""
        from burry.tools.binance import _rsi
        closes = [50.0] * 30
        result = _rsi(closes, 14)
        valid = [v for v in result if not math.isnan(v)]
        assert all(v == 100.0 for v in valid)

    def test_rsi_printed(self):
        from burry.tools.binance import _rsi
        import random; random.seed(0)
        closes = [100.0 + random.uniform(-3, 3) for _ in range(50)]
        result = _rsi(closes, 14)
        latest = next(v for v in reversed(result) if not math.isnan(v))
        print(f"\n  Sample RSI (synthetic): {latest:.2f}")


# ===========================================================================
# 3. F1 — Macro context endpoints
# ===========================================================================

class TestBTCPrice:
    def test_returns_dict(self):
        from burry.tools.binance import get_btc_price
        data = get_btc_price()
        assert isinstance(data, dict)

    def test_required_fields(self):
        from burry.tools.binance import get_btc_price
        data = get_btc_price()
        for field in ["price", "change_pct", "high_24h", "low_24h", "volume_24h"]:
            assert field in data, f"Missing field: {field}"

    def test_price_is_positive(self):
        from burry.tools.binance import get_btc_price
        data = get_btc_price()
        assert data["price"] > 0, f"BTC price is {data['price']}"

    def test_high_gte_low(self):
        from burry.tools.binance import get_btc_price
        data = get_btc_price()
        assert data["high_24h"] >= data["low_24h"]

    def test_volume_positive(self):
        from burry.tools.binance import get_btc_price
        data = get_btc_price()
        assert data["volume_24h"] > 0

    def test_printed(self):
        from burry.tools.binance import get_btc_price
        d = get_btc_price()
        print(f"\n  BTC price: ${d['price']:,.2f}  ({d['change_pct']:+.2f}%)")
        print(f"  24h range: ${d['low_24h']:,.2f} – ${d['high_24h']:,.2f}")
        print(f"  24h volume: ${d['volume_24h']:,.0f}")


class TestFearGreed:
    def test_returns_dict(self):
        from burry.tools.binance import get_fear_greed
        data = get_fear_greed()
        assert isinstance(data, dict)

    def test_required_fields(self):
        from burry.tools.binance import get_fear_greed
        data = get_fear_greed()
        for field in ["value", "label", "timestamp"]:
            assert field in data, f"Missing field: {field}"

    def test_value_in_range(self):
        from burry.tools.binance import get_fear_greed
        data = get_fear_greed()
        assert 0 <= data["value"] <= 100, f"F&G out of range: {data['value']}"

    def test_label_is_string(self):
        from burry.tools.binance import get_fear_greed
        data = get_fear_greed()
        assert isinstance(data["label"], str) and len(data["label"]) > 0

    def test_label_is_known_category(self):
        from burry.tools.binance import get_fear_greed
        data = get_fear_greed()
        valid = {"Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"}
        assert data["label"] in valid, f"Unknown label: {data['label']}"

    def test_printed(self):
        from burry.tools.binance import get_fear_greed
        d = get_fear_greed()
        print(f"\n  Fear & Greed: {d['value']} — {d['label']}")


class TestBTCDominance:
    def test_returns_dict(self, btc_dominance_data):
        assert isinstance(btc_dominance_data, dict)

    def test_field_present(self, btc_dominance_data):
        assert "btc_dominance_pct" in btc_dominance_data

    def test_dominance_in_range(self, btc_dominance_data):
        pct = btc_dominance_data["btc_dominance_pct"]
        assert 20.0 <= pct <= 80.0, f"BTC dominance looks wrong: {pct}%"

    def test_printed(self, btc_dominance_data):
        print(f"\n  BTC dominance: {btc_dominance_data['btc_dominance_pct']}%")


class TestBTCFundingRate:
    def test_returns_dict(self):
        from burry.tools.binance import get_btc_funding_rate
        data = get_btc_funding_rate()
        assert isinstance(data, dict)

    def test_required_fields(self):
        from burry.tools.binance import get_btc_funding_rate
        data = get_btc_funding_rate()
        assert "funding_rate_pct" in data
        assert "label" in data

    def test_rate_is_numeric(self):
        from burry.tools.binance import get_btc_funding_rate
        data = get_btc_funding_rate()
        assert isinstance(data["funding_rate_pct"], float)

    def test_label_matches_sign(self):
        from burry.tools.binance import get_btc_funding_rate
        data = get_btc_funding_rate()
        rate = data["funding_rate_pct"]
        if rate > 0:
            assert "positive" in data["label"]
        else:
            assert "negative" in data["label"]

    def test_printed(self):
        from burry.tools.binance import get_btc_funding_rate
        d = get_btc_funding_rate()
        print(f"\n  BTC funding: {d['funding_rate_pct']}%  ({d['label']})")


class TestMacroContext:
    def test_all_sections_present(self, macro_data):
        for key in ["btc", "fear_greed", "dominance", "funding", "session_bias"]:
            assert key in macro_data, f"Missing key: {key}"

    def test_session_bias_is_valid(self, macro_data):
        assert macro_data["session_bias"] in ("risk-on", "risk-off", "neutral"), \
            f"Unknown bias: {macro_data['session_bias']}"

    def test_bias_logic_risk_off_when_fg_low(self, macro_data):
        fg   = macro_data["fear_greed"]["value"]
        chg  = macro_data["btc"]["change_pct"]
        bias = macro_data["session_bias"]
        if fg <= 40 or chg < -2:
            assert bias == "risk-off", f"Expected risk-off, got {bias} (F&G={fg}, chg={chg})"
        elif fg >= 60 and chg > 0:
            assert bias == "risk-on"

    def test_printed(self, macro_data):
        d = macro_data
        print(f"\n  Session bias : {d['session_bias'].upper()}")
        print(f"  BTC          : ${d['btc']['price']:,.2f} ({d['btc']['change_pct']:+.2f}%)")
        print(f"  Fear & Greed : {d['fear_greed']['value']} ({d['fear_greed']['label']})")
        print(f"  Dominance    : {d['dominance']['btc_dominance_pct']}%")
        print(f"  Funding      : {d['funding']['funding_rate_pct']}%")


# ===========================================================================
# 4. F2 — Pair scanning
# ===========================================================================

class TestTopFuturesTickers:
    def test_returns_list(self):
        from burry.tools.binance import get_top_futures_tickers
        data = get_top_futures_tickers(10)
        assert isinstance(data, list)

    def test_respects_limit(self):
        from burry.tools.binance import get_top_futures_tickers
        data = get_top_futures_tickers(10)
        assert len(data) <= 10

    def test_all_end_with_usdt(self):
        from burry.tools.binance import get_top_futures_tickers
        data = get_top_futures_tickers(10)
        for item in data:
            assert item["symbol"].endswith("USDT"), \
                f"Non-USDT symbol: {item['symbol']}"

    def test_required_fields(self):
        from burry.tools.binance import get_top_futures_tickers
        data = get_top_futures_tickers(5)
        for item in data:
            for field in ["symbol", "price", "change_pct", "volume_24h"]:
                assert field in item

    def test_sorted_by_volume_desc(self):
        from burry.tools.binance import get_top_futures_tickers
        data = get_top_futures_tickers(10)
        vols = [d["volume_24h"] for d in data]
        assert vols == sorted(vols, reverse=True), "Not sorted by volume desc"

    def test_btcusdt_in_top_10(self):
        from burry.tools.binance import get_top_futures_tickers
        data = get_top_futures_tickers(10)
        symbols = [d["symbol"] for d in data]
        assert "BTCUSDT" in symbols, f"BTCUSDT not in top 10: {symbols}"

    def test_printed(self):
        from burry.tools.binance import get_top_futures_tickers
        data = get_top_futures_tickers(5)
        print(f"\n  Top 5 futures by volume:")
        for d in data:
            print(f"  {d['symbol']:15} ${d['price']:>12,.4f}  "
                  f"vol=${d['volume_24h']:>14,.0f}  {d['change_pct']:+.2f}%")


class TestFundingRates:
    def test_returns_dict(self):
        from burry.tools.binance import get_funding_rates
        data = get_funding_rates(["BTCUSDT", "ETHUSDT"])
        assert isinstance(data, dict)

    def test_requested_symbols_present(self):
        from burry.tools.binance import get_funding_rates
        data = get_funding_rates(["BTCUSDT", "ETHUSDT"])
        assert "BTCUSDT" in data
        assert "ETHUSDT" in data

    def test_values_are_floats(self):
        from burry.tools.binance import get_funding_rates
        data = get_funding_rates(["BTCUSDT", "ETHUSDT"])
        for sym, rate in data.items():
            assert isinstance(rate, float), f"{sym} rate not float: {type(rate)}"

    def test_rates_in_realistic_range(self):
        """Funding rates are almost always between -0.5% and +0.5%."""
        from burry.tools.binance import get_funding_rates
        data = get_funding_rates(["BTCUSDT", "ETHUSDT"])
        for sym, rate in data.items():
            assert -1.0 <= rate <= 1.0, f"{sym} funding out of range: {rate}%"

    def test_printed(self):
        from burry.tools.binance import get_funding_rates
        data = get_funding_rates(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        print("\n  Funding rates:")
        for sym, rate in data.items():
            direction = "longs pay" if rate > 0 else "shorts pay"
            print(f"  {sym:15} {rate:+.4f}%  ({direction})")


# ===========================================================================
# 5. F3 — 4H technical indicators
# ===========================================================================

class Test4HIndicators:
    @pytest.fixture(scope="class")
    def btc_indicators(self):
        from burry.tools.binance import get_4h_indicators
        return get_4h_indicators("BTCUSDT", candles=220)

    def test_returns_dict(self, btc_indicators):
        assert isinstance(btc_indicators, dict)

    def test_required_fields(self, btc_indicators):
        expected = [
            "symbol", "price", "ema20", "ema50", "ema200",
            "rsi", "rsi_zone", "above_ema20", "above_ema50", "above_ema200",
            "long_signal", "short_signal", "recent_candles",
        ]
        for field in expected:
            assert field in btc_indicators, f"Missing field: {field}"

    def test_symbol_matches(self, btc_indicators):
        assert btc_indicators["symbol"] == "BTCUSDT"

    def test_price_positive(self, btc_indicators):
        assert btc_indicators["price"] > 0

    def test_emas_positive(self, btc_indicators):
        assert btc_indicators["ema20"] > 0
        assert btc_indicators["ema50"] > 0
        assert btc_indicators["ema200"] > 0

    def test_rsi_in_range(self, btc_indicators):
        rsi = btc_indicators["rsi"]
        assert 0 <= rsi <= 100, f"RSI out of range: {rsi}"

    def test_rsi_zone_is_valid(self, btc_indicators):
        valid = {"overbought", "oversold", "neutral (40-60)", "weak", "strong"}
        assert btc_indicators["rsi_zone"] in valid, \
            f"Unknown RSI zone: {btc_indicators['rsi_zone']}"

    def test_boolean_flags(self, btc_indicators):
        for flag in ["above_ema20", "above_ema50", "above_ema200",
                     "long_signal", "short_signal"]:
            assert isinstance(btc_indicators[flag], bool), \
                f"{flag} is not bool: {type(btc_indicators[flag])}"

    def test_signal_logic_consistency(self, btc_indicators):
        """long and short signals can't both be True simultaneously."""
        assert not (btc_indicators["long_signal"] and btc_indicators["short_signal"]), \
            "Both long and short signals are True — logic error"

    def test_recent_candles_shape(self, btc_indicators):
        candles = btc_indicators["recent_candles"]
        assert isinstance(candles, list)
        assert len(candles) == 3
        for c in candles:
            for field in ["open", "high", "low", "close", "volume"]:
                assert field in c
            assert c["high"] >= c["low"], "Candle high < low"

    def test_ema_ordering_reasonable(self, btc_indicators):
        """EMA200 should not be wildly far from price in a liquid market."""
        price = btc_indicators["price"]
        e200  = btc_indicators["ema200"]
        diff_pct = abs(price - e200) / e200 * 100
        assert diff_pct < 50, \
            f"EMA200 is {diff_pct:.1f}% away from price — looks wrong"

    def test_printed(self, btc_indicators):
        d = btc_indicators
        price = d["price"]
        print(f"\n  BTCUSDT 4H indicators:")
        print(f"  Price : ${price:,.2f}")
        print(f"  EMA20 : ${d['ema20']:,.2f}  {'✅' if d['above_ema20'] else '❌'}")
        print(f"  EMA50 : ${d['ema50']:,.2f}  {'✅' if d['above_ema50'] else '❌'}")
        print(f"  EMA200: ${d['ema200']:,.2f}  {'✅' if d['above_ema200'] else '❌'}")
        print(f"  RSI   : {d['rsi']:.2f}  ({d['rsi_zone']})")
        print(f"  Long signal : {d['long_signal']}  |  Short signal: {d['short_signal']}")


# ===========================================================================
# 6. Full F2 scan (slowest test — runs last)
# ===========================================================================

class TestScanCandidates:
    @pytest.fixture(scope="class")
    def candidates(self):
        from burry.tools.binance import scan_candidates
        return scan_candidates(top_n=30)

    def test_returns_dict_with_longs_shorts(self, candidates):
        assert isinstance(candidates, dict)
        assert "longs" in candidates
        assert "shorts" in candidates

    def test_max_two_per_side(self, candidates):
        assert len(candidates["longs"])  <= 2
        assert len(candidates["shorts"]) <= 2

    def test_long_candidates_meet_criteria(self, candidates):
        """Every long candidate must satisfy RSI 40-60 and be above EMA20+EMA50."""
        for c in candidates["longs"]:
            rsi = c.get("rsi", 0)
            assert 40 <= rsi <= 60, \
                f"{c['symbol']} long candidate RSI {rsi} outside 40-60"
            assert c.get("above_ema20"),  f"{c['symbol']} long not above EMA20"
            assert c.get("above_ema50"),  f"{c['symbol']} long not above EMA50"

    def test_short_candidates_meet_criteria(self, candidates):
        """Every short candidate must have RSI >70 and be below EMA200."""
        for c in candidates["shorts"]:
            rsi = c.get("rsi", 0)
            assert rsi > 70, \
                f"{c['symbol']} short candidate RSI {rsi} not >70"
            assert not c.get("above_ema200"), \
                f"{c['symbol']} short not below EMA200"

    def test_candidate_has_required_fields(self, candidates):
        required = ["symbol", "price", "rsi", "ema20", "ema50", "ema200",
                    "funding_rate_pct", "volume_24h"]
        for side in ("longs", "shorts"):
            for c in candidates[side]:
                for field in required:
                    assert field in c, f"{c.get('symbol')} missing '{field}'"

    def test_printed(self, candidates):
        print(f"\n  🟢 LONG candidates ({len(candidates['longs'])}):")
        for c in candidates["longs"]:
            print(f"  {c['symbol']:15} RSI={c['rsi']:.1f}  "
                  f"funding={c['funding_rate_pct']:+.4f}%  "
                  f"price=${c['price']:,.4f}")
        print(f"  🔴 SHORT candidates ({len(candidates['shorts'])}):")
        for c in candidates["shorts"]:
            print(f"  {c['symbol']:15} RSI={c['rsi']:.1f}  "
                  f"funding={c['funding_rate_pct']:+.4f}%  "
                  f"price=${c['price']:,.4f}")
