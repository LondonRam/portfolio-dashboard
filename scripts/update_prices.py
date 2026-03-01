#!/usr/bin/env python3
"""
Portfolio price updater.
Fetches live prices from Yahoo Finance, computes P&L, and outputs JSON.
Designed to run daily via GitHub Actions after US market close.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
HOLDINGS_PATH = ROOT / "data" / "holdings.json"
OUTPUT_PATH = ROOT / "docs" / "data" / "portfolio.json"

# FX pairs to fetch
FX_PAIRS = {
    "GBPUSD": "GBPUSD=X",
    "EURUSD": "EURUSD=X",
    "TWDUSD": "TWDUSD=X",
}


def load_holdings():
    with open(HOLDINGS_PATH) as f:
        return json.load(f)


def fetch_prices(yahoo_tickers: list[str]) -> dict[str, float | None]:
    """Fetch latest closing prices for a list of Yahoo Finance tickers."""
    prices = {}
    # Batch download — faster than individual calls
    if not yahoo_tickers:
        return prices

    # yfinance download returns a DataFrame
    # For single day, we just need the last close
    try:
        tickers_str = " ".join(yahoo_tickers)
        data = yf.download(tickers_str, period="5d", progress=False, threads=True)

        if data.empty:
            print("WARNING: yfinance returned empty data", file=sys.stderr)
            return prices

        # Handle both single and multi-ticker DataFrames
        if len(yahoo_tickers) == 1:
            ticker = yahoo_tickers[0]
            if "Close" in data.columns:
                last_close = data["Close"].dropna().iloc[-1]
                prices[ticker] = float(last_close)
        else:
            close_data = data["Close"] if "Close" in data.columns else data.xs("Close", axis=1, level=0) if isinstance(data.columns, __import__('pandas').MultiIndex) else None
            if close_data is not None:
                for ticker in yahoo_tickers:
                    if ticker in close_data.columns:
                        series = close_data[ticker].dropna()
                        if not series.empty:
                            prices[ticker] = float(series.iloc[-1])
                        else:
                            print(f"WARNING: No price data for {ticker}", file=sys.stderr)
                    else:
                        print(f"WARNING: {ticker} not in download results", file=sys.stderr)
    except Exception as e:
        print(f"ERROR in batch download: {e}", file=sys.stderr)
        # Fallback: fetch individually
        for ticker in yahoo_tickers:
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="5d")
                if not hist.empty:
                    prices[ticker] = float(hist["Close"].iloc[-1])
                else:
                    print(f"WARNING: No data for {ticker} in fallback", file=sys.stderr)
            except Exception as e2:
                print(f"ERROR fetching {ticker}: {e2}", file=sys.stderr)

    return prices


def fetch_fx_rates() -> dict[str, float]:
    """Fetch FX rates. Returns dict like {'GBPUSD': 1.26, 'EURUSD': 1.04, 'TWDUSD': 0.031}"""
    rates = {}
    yahoo_tickers = list(FX_PAIRS.values())
    prices = fetch_prices(yahoo_tickers)

    for name, yahoo_ticker in FX_PAIRS.items():
        if yahoo_ticker in prices and prices[yahoo_ticker] is not None:
            rates[name] = prices[yahoo_ticker]
        else:
            # Fallback defaults
            defaults = {"GBPUSD": 1.2615, "EURUSD": 1.0389, "TWDUSD": 0.0308}
            rates[name] = defaults.get(name, 1.0)
            print(f"WARNING: Using fallback FX rate for {name}: {rates[name]}", file=sys.stderr)

    return rates


def to_usd(price: float, ccy: str, fx_rates: dict) -> float:
    """Convert a price in local currency to USD."""
    if ccy == "USD":
        return price
    elif ccy == "GBP":
        return price * fx_rates.get("GBPUSD", 1.2615)
    elif ccy == "EUR":
        return price * fx_rates.get("EURUSD", 1.0389)
    elif ccy == "TWD":
        return price * fx_rates.get("TWDUSD", 0.0308)
    else:
        print(f"WARNING: Unknown currency {ccy}, treating as USD", file=sys.stderr)
        return price


def build_portfolio(config: dict, prices: dict, fx_rates: dict) -> dict:
    """Build the full portfolio output JSON."""
    now = datetime.now(timezone.utc).isoformat()

    enriched = []
    for h in config["holdings"]:
        yahoo_ticker = h["yahooTicker"]
        local_price = prices.get(yahoo_ticker)

        if local_price is None:
            print(f"WARNING: No price for {h['ticker']} ({yahoo_ticker}), skipping", file=sys.stderr)
            continue

        ccy = h["ccy"]
        avg_cost_usd = to_usd(h["avgCost"], ccy, fx_rates)
        price_usd = to_usd(local_price, ccy, fx_rates)
        value_usd = h["shares"] * price_usd
        cost_usd = h["shares"] * avg_cost_usd
        pnl_usd = value_usd - cost_usd
        pnl_pct = (pnl_usd / cost_usd * 100) if cost_usd != 0 else 0

        enriched.append({
            "ticker": h["ticker"],
            "yahooTicker": yahoo_ticker,
            "name": h["name"],
            "shares": h["shares"],
            "avgCost": h["avgCost"],
            "avgCostUSD": round(avg_cost_usd, 4),
            "localPrice": round(local_price, 4),
            "priceUSD": round(price_usd, 4),
            "ccy": ccy,
            "valueUSD": round(value_usd, 2),
            "costUSD": round(cost_usd, 2),
            "pnlUSD": round(pnl_usd, 2),
            "pnlPct": round(pnl_pct, 2),
            "account": h["account"],
            "theme": h["theme"],
        })

    # Totals
    total_value = sum(h["valueUSD"] for h in enriched)
    total_cost = sum(h["costUSD"] for h in enriched)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost != 0 else 0

    # Theme breakdown
    themes = {}
    for h in enriched:
        t = h["theme"]
        if t not in themes:
            themes[t] = {"value": 0, "cost": 0, "positions": 0}
        themes[t]["value"] += h["valueUSD"]
        themes[t]["cost"] += h["costUSD"]
        themes[t]["positions"] += 1

    theme_summary = []
    for t, d in sorted(themes.items(), key=lambda x: -x[1]["value"]):
        pnl = d["value"] - d["cost"]
        pnl_pct = (pnl / d["cost"] * 100) if d["cost"] != 0 else 0
        theme_summary.append({
            "theme": t,
            "valueUSD": round(d["value"], 2),
            "costUSD": round(d["cost"], 2),
            "pnlUSD": round(pnl, 2),
            "pnlPct": round(pnl_pct, 2),
            "positions": d["positions"],
            "weightPct": round(d["value"] / total_value * 100, 2) if total_value else 0,
        })

    # Account breakdown
    accounts = {}
    for h in enriched:
        a = h["account"]
        if a not in accounts:
            accounts[a] = {"value": 0, "cost": 0, "positions": 0}
        accounts[a]["value"] += h["valueUSD"]
        accounts[a]["cost"] += h["costUSD"]
        accounts[a]["positions"] += 1

    account_summary = []
    for a, d in sorted(accounts.items(), key=lambda x: -x[1]["value"]):
        acct_config = config["accounts"].get(a, {})
        pnl = d["value"] - d["cost"]
        pnl_pct = (pnl / d["cost"] * 100) if d["cost"] != 0 else 0
        entry = {
            "account": a,
            "type": acct_config.get("type", "cash"),
            "baseCurrency": acct_config.get("baseCurrency", "USD"),
            "valueUSD": round(d["value"], 2),
            "costUSD": round(d["cost"], 2),
            "pnlUSD": round(pnl, 2),
            "pnlPct": round(pnl_pct, 2),
            "positions": d["positions"],
            "weightPct": round(d["value"] / total_value * 100, 2) if total_value else 0,
        }
        if acct_config.get("type") == "margin":
            entry["marginDebt"] = acct_config.get("marginDebt", 0)
            entry["netLiquidation"] = round(d["value"] - acct_config.get("marginDebt", 0), 2)
            entry["marginUtilPct"] = round(acct_config.get("marginDebt", 0) / d["value"] * 100, 2) if d["value"] else 0
        account_summary.append(entry)

    return {
        "meta": {
            "updatedAt": now,
            "positionCount": len(enriched),
            "baseCurrency": "USD",
            "fxRates": {k: round(v, 6) for k, v in fx_rates.items()},
        },
        "summary": {
            "totalValueUSD": round(total_value, 2),
            "totalCostUSD": round(total_cost, 2),
            "totalPnLUSD": round(total_pnl, 2),
            "totalPnLPct": round(total_pnl_pct, 2),
        },
        "themes": theme_summary,
        "accounts": account_summary,
        "holdings": enriched,
    }


def main():
    print("Loading holdings config...")
    config = load_holdings()

    # Collect all Yahoo tickers
    yahoo_tickers = list(set(h["yahooTicker"] for h in config["holdings"]))
    print(f"Fetching prices for {len(yahoo_tickers)} tickers...")

    # Fetch FX rates first
    print("Fetching FX rates...")
    fx_rates = fetch_fx_rates()
    print(f"  FX: {fx_rates}")

    # Fetch stock prices
    print("Fetching stock prices...")
    prices = fetch_prices(yahoo_tickers)
    print(f"  Got prices for {len(prices)}/{len(yahoo_tickers)} tickers")

    # Check for missing
    missing = [t for t in yahoo_tickers if t not in prices]
    if missing:
        print(f"  MISSING: {missing}", file=sys.stderr)

    # Build output
    print("Building portfolio JSON...")
    portfolio = build_portfolio(config, prices, fx_rates)

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(portfolio, f, indent=2)

    print(f"Written to {OUTPUT_PATH}")
    print(f"  Total value: ${portfolio['summary']['totalValueUSD']:,.2f}")
    print(f"  Total P&L: ${portfolio['summary']['totalPnLUSD']:,.2f} ({portfolio['summary']['totalPnLPct']:+.2f}%)")
    print(f"  Positions: {portfolio['meta']['positionCount']}")


if __name__ == "__main__":
    main()
