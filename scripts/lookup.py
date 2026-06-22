#!/usr/bin/env python3
"""Quick Finnhub lookup for one or more tickers.

Usage:
    python3 scripts/lookup.py NDAQ
    python3 scripts/lookup.py AAPL TSLA NDAQ
    python3 scripts/lookup.py AAPL --news-days 14 --no-insider
    python3 scripts/lookup.py AAPL --section quote
    python3 scripts/lookup.py AAPL --section metrics --limit 30

Sections: all (default) | profile | quote | metrics | recommendation | news | insider
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

# ── path setup ───────────────────────────────────────────────────────────────
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))


# ── formatting helpers ────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
DIM    = "\033[2m"


def header(text: str) -> str:
    return f"\n{BOLD}{CYAN}{'─' * 50}{RESET}\n{BOLD}{CYAN}  {text}{RESET}\n{BOLD}{CYAN}{'─' * 50}{RESET}"


def kv(key: str, value, width: int = 28) -> str:
    val_str = str(value) if value is not None else f"{DIM}n/a{RESET}"
    return f"  {key:<{width}} {val_str}"


def fmt_price(value, suffix: str = "") -> str:
    if value is None:
        return f"{DIM}n/a{RESET}"
    color = GREEN if value >= 0 else RED
    return f"{color}{value:+.2f}{suffix}{RESET}" if suffix == "%" else f"{CYAN}${value:.2f}{RESET}"


def fmt_change(change, pct) -> str:
    if change is None:
        return f"{DIM}n/a{RESET}"
    color = GREEN if change >= 0 else RED
    arrow = "▲" if change >= 0 else "▼"
    return f"{color}{arrow} {change:+.2f}  ({pct:+.2f}%){RESET}"


# ── section printers ──────────────────────────────────────────────────────────

def print_profile(symbol: str, data: dict) -> None:
    p = data.get("profile", {})
    print(header(f"PROFILE — {symbol}"))
    print(kv("Name",            p.get("name")))
    print(kv("Exchange",        p.get("exchange")))
    print(kv("Industry",        p.get("finnhubIndustry")))
    print(kv("Country",         p.get("country")))
    print(kv("Currency",        p.get("currency")))
    cap = p.get("marketCapitalization")
    print(kv("Market Cap",      f"${cap:,.2f}M" if cap else "n/a"))
    shares = p.get("shareOutstanding")
    print(kv("Shares Out.",     f"{shares:,.2f}M" if shares else "n/a"))
    print(kv("IPO Date",        p.get("ipo")))
    print(kv("Website",         p.get("weburl")))


def print_quote(symbol: str, data: dict) -> None:
    q = data.get("quote", {})
    print(header(f"QUOTE — {symbol}"))
    print(kv("Price",           fmt_price(q.get("price"))))
    print(kv("Change",          fmt_change(q.get("change"), q.get("change_pct", 0))))
    print(kv("Open",            fmt_price(q.get("open"))))
    print(kv("Day High",        fmt_price(q.get("high"))))
    print(kv("Day Low",         fmt_price(q.get("low"))))
    print(kv("Prev Close",      fmt_price(q.get("prev_close"))))


def print_metrics(symbol: str, data: dict, limit: int | None = None) -> None:
    m = data.get("metrics", {})
    print(header(f"METRICS — {symbol}  ({len(m)} total)"))

    # Always show these key ones first
    priority = [
        "peNormalizedAnnual", "forwardPE", "beta",
        "52WeekHigh", "52WeekLow", "52WeekHighDate", "52WeekLowDate",
        "52WeekPriceReturnDaily", "5DayPriceReturnDaily",
        "epsNormalizedAnnual", "epsTTM", "epsGrowth5Y",
        "revenueGrowth5Y", "grossMarginTTM", "netProfitMarginTTM",
        "roeTTM", "roaTTM", "pb", "psTTM", "dividendYieldIndicatedAnnual",
        "marketCapitalization", "enterpriseValue",
    ]
    printed = set()
    for k in priority:
        if k in m:
            v = m[k]
            display = f"{v:.4f}" if isinstance(v, float) else str(v)
            print(kv(k, display))
            printed.add(k)

    remaining = [(k, v) for k, v in m.items() if k not in printed]
    if limit is not None:
        remaining = remaining[:max(0, limit - len(printed))]

    if remaining:
        print(f"\n  {DIM}── other metrics ──{RESET}")
        for k, v in remaining:
            display = f"{v:.4f}" if isinstance(v, float) else str(v)
            print(kv(k, display))

    if limit is not None and len(m) > limit:
        skipped = len(m) - limit
        print(f"\n  {DIM}... {skipped} more metrics (remove --limit to see all){RESET}")


def print_recommendation(symbol: str, data: dict) -> None:
    recs = data.get("recommendation", [])
    print(header(f"ANALYST RECOMMENDATIONS — {symbol}"))
    if not recs:
        print(f"  {DIM}No data{RESET}")
        return
    print(f"  {'Period':<14} {'StrongBuy':>10} {'Buy':>6} {'Hold':>6} {'Sell':>6} {'StrongSell':>12}")
    print(f"  {'─'*14} {'─'*10} {'─'*6} {'─'*6} {'─'*6} {'─'*12}")
    for r in recs[:6]:
        sb, b, h, s, ss = r["strongBuy"], r["buy"], r["hold"], r["sell"], r["strongSell"]
        total = sb + b + h + s + ss or 1
        bull_pct = (sb + b) / total * 100
        color = GREEN if bull_pct >= 60 else (YELLOW if bull_pct >= 40 else RED)
        print(f"  {r['period']:<14} {color}{sb:>10} {b:>6}{RESET} {h:>6} {RED}{s:>6} {ss:>12}{RESET}")


def print_news(symbol: str, data: dict, max_items: int = 10) -> None:
    news = data.get("news", [])
    print(header(f"NEWS — {symbol}  ({len(news)} items in window)"))
    if not news:
        print(f"  {DIM}No news in window{RESET}")
        return
    for item in news[:max_items]:
        ts = item.get("datetime")
        dt_str = datetime.fromtimestamp(ts).strftime("%b %d %H:%M") if ts else "?"
        print(f"  {DIM}{dt_str}{RESET}  [{item.get('source', '?')}]")
        print(f"  {BOLD}{item.get('headline', '')}{RESET}")
        summary = item.get("summary", "")
        if summary:
            print(f"  {DIM}{summary[:120]}...{RESET}")
        print()
    if len(news) > max_items:
        print(f"  {DIM}... {len(news) - max_items} more articles{RESET}")


def print_insider(symbol: str, data: dict) -> None:
    entries = data.get("insider_sentiment", [])
    print(header(f"INSIDER SENTIMENT — {symbol}"))
    if not entries:
        print(f"  {DIM}No data{RESET}")
        return
    print(f"  {DIM}MSPR = Market Sentiment Percentage Ratio  (-100 bearish → +100 bullish){RESET}\n")
    print(f"  {'Month':<12} {'MSPR':>8} {'Change':>10}")
    print(f"  {'─'*12} {'─'*8} {'─'*10}")
    for e in entries:
        mspr = e.get("mspr", 0) or 0
        change = e.get("change", 0) or 0
        color = GREEN if mspr > 0 else (RED if mspr < 0 else DIM)
        print(f"  {e.get('month', '?'):<12} {color}{mspr:>8.2f}{RESET} {change:>10.0f}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Finnhub data for one or more tickers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("tickers", nargs="+", help="Ticker symbols, e.g. AAPL TSLA NDAQ")
    parser.add_argument("--section", default="all",
                        choices=["all", "profile", "quote", "metrics",
                                 "recommendation", "news", "insider"],
                        help="Which section to show (default: all)")
    parser.add_argument("--news-days", type=int, default=7,
                        help="Days of news to fetch (default: 7)")
    parser.add_argument("--insider-days", type=int, default=180,
                        help="Days of insider sentiment to fetch (default: 180)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max metrics to display (default: all)")
    parser.add_argument("--no-insider", action="store_true",
                        help="Skip insider sentiment fetch")
    parser.add_argument("--json", action="store_true",
                        help="Dump raw JSON instead of formatted output")
    args = parser.parse_args()

    from burry.tools.finnhub import fetch_company_data

    tickers = [t.upper() for t in args.tickers]
    print(f"\n{BOLD}Fetching Finnhub data for: {', '.join(tickers)}{RESET}")

    data = fetch_company_data(
        tickers,
        news_days=args.news_days,
        insider_days=0 if args.no_insider else args.insider_days,
    )

    if args.json:
        print(json.dumps(data, indent=2, default=str))
        return

    section = args.section
    for symbol in tickers:
        d = data[symbol]
        if section in ("all", "profile"):
            print_profile(symbol, d)
        if section in ("all", "quote"):
            print_quote(symbol, d)
        if section in ("all", "metrics"):
            print_metrics(symbol, d, limit=args.limit)
        if section in ("all", "recommendation"):
            print_recommendation(symbol, d)
        if section in ("all", "news"):
            print_news(symbol, d)
        if section in ("all", "insider") and not args.no_insider:
            print_insider(symbol, d)

    print()


if __name__ == "__main__":
    main()
