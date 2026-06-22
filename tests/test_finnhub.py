"""Integration tests for the Finnhub API layer.

These tests hit the real Finnhub API using the key in .env — no mocking.
They verify the shape, types, and completeness of every field we consume
so we know exactly what we're getting before wiring it into the agents.

Run with:
    pytest tests/test_finnhub.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

# Make sure the package is importable from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Load .env so config.py picks up the key
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_TICKERS = ["AAPL", "TSLA"]   # well-known tickers — reliable on free tier


@pytest.fixture(scope="module")
def raw_client():
    """Bare finnhub.Client — lets us probe endpoints not yet wrapped."""
    import finnhub
    key = os.getenv("FINNHUB_API_KEY")
    assert key, "FINNHUB_API_KEY is missing from .env"
    return finnhub.Client(api_key=key)


@pytest.fixture(scope="module")
def company_data():
    """Result of our wrapper fetch_company_data for TEST_TICKERS."""
    from burry.tools.finnhub import fetch_company_data
    return fetch_company_data(TEST_TICKERS)


# ===========================================================================
# 1. Connectivity
# ===========================================================================

class TestConnectivity:
    def test_api_key_is_set(self):
        key = os.getenv("FINNHUB_API_KEY")
        assert key is not None, "FINNHUB_API_KEY not found in environment"
        assert len(key) > 10, "FINNHUB_API_KEY looks too short — check .env"

    def test_client_instantiates(self, raw_client):
        assert raw_client is not None

    def test_market_status_reachable(self, raw_client):
        """Simple ping — market status endpoint is always available."""
        status = raw_client.market_status(exchange="US")
        assert isinstance(status, dict), f"Expected dict, got {type(status)}"
        assert "isOpen" in status, f"'isOpen' missing from response: {status}"
        print(f"\n  Market open: {status['isOpen']}")


# ===========================================================================
# 2. Company Profile (fetch_company_data → profile)
# ===========================================================================

class TestCompanyProfile:
    def test_all_tickers_present(self, company_data):
        for ticker in TEST_TICKERS:
            assert ticker in company_data, f"{ticker} missing from result"

    def test_profile_is_dict(self, company_data):
        for ticker in TEST_TICKERS:
            profile = company_data[ticker]["profile"]
            assert isinstance(profile, dict), \
                f"{ticker}.profile is {type(profile)}, expected dict"

    def test_profile_core_fields(self, company_data):
        """Fields the agents rely on for identifying the company."""
        expected = ["name", "ticker", "exchange", "finnhubIndustry", "currency",
                    "marketCapitalization", "shareOutstanding", "weburl", "logo",
                    "country", "ipo"]
        for ticker in TEST_TICKERS:
            profile = company_data[ticker]["profile"]
            missing = [f for f in expected if f not in profile]
            assert not missing, \
                f"{ticker}.profile missing fields: {missing}\nGot: {list(profile.keys())}"

    def test_profile_types(self, company_data):
        for ticker in TEST_TICKERS:
            p = company_data[ticker]["profile"]
            assert isinstance(p.get("name"), str),              f"{ticker} name not str"
            assert isinstance(p.get("ticker"), str),            f"{ticker} ticker not str"
            assert isinstance(p.get("marketCapitalization"), (int, float)), \
                f"{ticker} marketCapitalization not numeric"
            assert p.get("marketCapitalization", 0) > 0,        f"{ticker} marketCap is 0"

    def test_profile_values_printed(self, company_data):
        """Not an assertion — prints the raw profile so you can eyeball it."""
        for ticker in TEST_TICKERS:
            print(f"\n--- {ticker} profile ---")
            for k, v in company_data[ticker]["profile"].items():
                print(f"  {k}: {v}")


# ===========================================================================
# 3. Basic Financials / Metrics (fetch_company_data → metrics)
# ===========================================================================

class TestBasicFinancials:
    def test_metrics_is_dict(self, company_data):
        for ticker in TEST_TICKERS:
            metrics = company_data[ticker]["metrics"]
            assert isinstance(metrics, dict), \
                f"{ticker}.metrics is {type(metrics)}"

    def test_metrics_not_empty(self, company_data):
        for ticker in TEST_TICKERS:
            metrics = company_data[ticker]["metrics"]
            assert len(metrics) > 0, f"{ticker}.metrics is empty"

    def test_key_valuation_metrics_present(self, company_data):
        """P/E, beta, 52-week range are used for fundamental screening."""
        desired = ["peNormalizedAnnual", "beta", "52WeekHigh", "52WeekLow"]
        for ticker in TEST_TICKERS:
            metrics = company_data[ticker]["metrics"]
            missing = [f for f in desired if f not in metrics]
            # Warn but don't fail — free tier may omit some
            if missing:
                print(f"\n  WARNING {ticker}: missing metrics {missing}")

    def test_metrics_numeric_values(self, company_data):
        # Finnhub returns a handful of date strings alongside numeric metrics.
        # Known string fields: 52WeekHighDate, 52WeekLowDate (format: YYYY-MM-DD)
        known_string_fields = {"52WeekHighDate", "52WeekLowDate"}
        for ticker in TEST_TICKERS:
            metrics = company_data[ticker]["metrics"]
            non_numeric = {
                k: type(v).__name__
                for k, v in metrics.items()
                if not isinstance(v, (int, float, type(None)))
                and k not in known_string_fields
            }
            assert not non_numeric, \
                f"{ticker}.metrics has unexpected non-numeric values: {non_numeric}"

            # Also verify the date strings are well-formed (YYYY-MM-DD)
            import re
            date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
            for date_field in known_string_fields:
                if date_field in metrics:
                    assert date_pattern.match(metrics[date_field]), \
                        f"{ticker}.{date_field} not a valid date: {metrics[date_field]}"

    def test_metrics_keys_printed(self, company_data):
        for ticker in TEST_TICKERS:
            keys = list(company_data[ticker]["metrics"].keys())
            print(f"\n--- {ticker} metric keys ({len(keys)}) ---")
            print("  " + ", ".join(keys))


# ===========================================================================
# 4. Recommendation Trends (fetch_company_data → recommendation)
# ===========================================================================

class TestRecommendationTrends:
    def test_recommendation_is_list(self, company_data):
        for ticker in TEST_TICKERS:
            rec = company_data[ticker]["recommendation"]
            assert isinstance(rec, list), \
                f"{ticker}.recommendation is {type(rec)}, expected list"

    def test_recommendation_not_empty(self, company_data):
        for ticker in TEST_TICKERS:
            rec = company_data[ticker]["recommendation"]
            assert len(rec) > 0, f"{ticker}.recommendation is empty"

    def test_recommendation_entry_shape(self, company_data):
        expected_keys = {"buy", "hold", "sell", "strongBuy", "strongSell", "period", "symbol"}
        for ticker in TEST_TICKERS:
            latest = company_data[ticker]["recommendation"][0]
            assert isinstance(latest, dict), f"{ticker} rec entry not a dict"
            missing = expected_keys - set(latest.keys())
            assert not missing, \
                f"{ticker} rec entry missing keys: {missing}\nGot: {list(latest.keys())}"

    def test_recommendation_counts_are_integers(self, company_data):
        count_keys = ["buy", "hold", "sell", "strongBuy", "strongSell"]
        for ticker in TEST_TICKERS:
            latest = company_data[ticker]["recommendation"][0]
            for k in count_keys:
                assert isinstance(latest[k], int), \
                    f"{ticker}.recommendation[0][{k}] is {type(latest[k])}, expected int"

    def test_recommendation_printed(self, company_data):
        for ticker in TEST_TICKERS:
            latest = company_data[ticker]["recommendation"][0]
            print(f"\n--- {ticker} latest recommendation ---")
            for k, v in latest.items():
                print(f"  {k}: {v}")


# ===========================================================================
# 5. Raw endpoints not yet wrapped (exploration for future nodes)
# ===========================================================================

class TestRawEndpoints:
    def test_earnings_calendar(self, raw_client):
        """Upcoming earnings — useful for the macro/catalyst node."""
        from datetime import date, timedelta
        today = date.today().isoformat()
        week = (date.today() + timedelta(days=7)).isoformat()
        data = raw_client.earnings_calendar(_from=today, to=week, symbol="")
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        assert "earningsCalendar" in data, \
            f"'earningsCalendar' missing: {list(data.keys())}"
        print(f"\n  Upcoming earnings entries: {len(data['earningsCalendar'])}")

    def test_news_for_ticker(self, raw_client):
        """Company news — used by sentiment node."""
        from datetime import date, timedelta
        today = date.today().isoformat()
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        news = raw_client.company_news("AAPL", _from=week_ago, to=today)
        assert isinstance(news, list), f"Expected list, got {type(news)}"
        assert len(news) > 0, "No news returned for AAPL in the last 7 days"
        first = news[0]
        for field in ["headline", "source", "datetime", "url", "summary"]:
            assert field in first, f"News item missing '{field}': {list(first.keys())}"
        print(f"\n  AAPL news items (7d): {len(news)}")
        print(f"  Latest: [{first['source']}] {first['headline'][:80]}")

    def test_general_market_news(self, raw_client):
        """General market news feed."""
        news = raw_client.general_news("general", min_id=0)
        assert isinstance(news, list), f"Expected list, got {type(news)}"
        assert len(news) > 0, "No general market news returned"
        print(f"\n  General news items: {len(news)}")

    def test_quote(self, raw_client):
        """Real-time quote — price, change, volume."""
        quote = raw_client.quote("AAPL")
        assert isinstance(quote, dict)
        for field in ["c", "d", "dp", "h", "l", "o", "pc", "t"]:
            # c=current, d=change, dp=change%, h=high, l=low, o=open, pc=prev close, t=timestamp
            assert field in quote, f"Quote missing field '{field}': {list(quote.keys())}"
        assert quote["c"] > 0, f"Current price is 0 or missing: {quote}"
        print(f"\n  AAPL quote — price: ${quote['c']:.2f}, "
              f"change: {quote['dp']:+.2f}%, volume day high: ${quote['h']:.2f}")

    def test_insider_sentiment(self, raw_client):
        """Insider sentiment (MSPR score) — used by research agents."""
        from datetime import date, timedelta
        today = date.today().isoformat()
        six_months = (date.today() - timedelta(days=180)).isoformat()
        data = raw_client.stock_insider_sentiment("AAPL", six_months, today)
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        assert "data" in data, f"'data' key missing: {list(data.keys())}"
        print(f"\n  AAPL insider sentiment entries: {len(data.get('data', []))}")


# ===========================================================================
# 6. fetch_company_data — full wrapper output snapshot
# ===========================================================================

class TestQuote:
    def test_quote_present(self, company_data):
        for ticker in TEST_TICKERS:
            assert "quote" in company_data[ticker], f"{ticker} missing 'quote'"

    def test_quote_fields(self, company_data):
        expected = {"price", "change", "change_pct", "high", "low", "open", "prev_close"}
        for ticker in TEST_TICKERS:
            quote = company_data[ticker]["quote"]
            missing = expected - set(quote.keys())
            assert not missing, f"{ticker}.quote missing fields: {missing}"

    def test_quote_price_positive(self, company_data):
        for ticker in TEST_TICKERS:
            price = company_data[ticker]["quote"]["price"]
            assert isinstance(price, (int, float)), f"{ticker} price not numeric"
            assert price > 0, f"{ticker} price is 0 or negative: {price}"

    def test_quote_printed(self, company_data):
        for ticker in TEST_TICKERS:
            q = company_data[ticker]["quote"]
            print(f"\n--- {ticker} quote ---")
            for k, v in q.items():
                print(f"  {k}: {v}")


class TestNews:
    def test_news_present(self, company_data):
        for ticker in TEST_TICKERS:
            assert "news" in company_data[ticker], f"{ticker} missing 'news'"

    def test_news_is_list(self, company_data):
        for ticker in TEST_TICKERS:
            assert isinstance(company_data[ticker]["news"], list)

    def test_news_item_fields(self, company_data):
        expected = {"headline", "source", "summary", "url", "datetime"}
        for ticker in TEST_TICKERS:
            news = company_data[ticker]["news"]
            if not news:
                continue
            missing = expected - set(news[0].keys())
            assert not missing, f"{ticker}.news[0] missing fields: {missing}"

    def test_news_printed(self, company_data):
        for ticker in TEST_TICKERS:
            news = company_data[ticker]["news"]
            print(f"\n--- {ticker} news ({len(news)} items) ---")
            for item in news[:2]:
                print(f"  [{item['source']}] {item['headline']}")


class TestInsiderSentiment:
    def test_insider_present(self, company_data):
        for ticker in TEST_TICKERS:
            assert "insider_sentiment" in company_data[ticker]

    def test_insider_is_list(self, company_data):
        for ticker in TEST_TICKERS:
            assert isinstance(company_data[ticker]["insider_sentiment"], list)

    def test_insider_printed(self, company_data):
        for ticker in TEST_TICKERS:
            entries = company_data[ticker]["insider_sentiment"]
            print(f"\n--- {ticker} insider sentiment ({len(entries)} months) ---")
            for e in entries[:3]:
                print(f"  {e.get('month')}  mspr={e.get('mspr')}  change={e.get('change')}")


class TestWrapperOutputShape:
    def test_result_structure(self, company_data):
        """Top-level keys must include all 6 data sections."""
        expected = {"profile", "metrics", "recommendation", "quote", "news", "insider_sentiment"}
        for ticker in TEST_TICKERS:
            keys = set(company_data[ticker].keys())
            missing = expected - keys
            assert not missing, f"{ticker} missing keys: {missing}"

    def test_no_none_top_level(self, company_data):
        for ticker in TEST_TICKERS:
            for key, val in company_data[ticker].items():
                assert val is not None, f"{ticker}.{key} is None"
