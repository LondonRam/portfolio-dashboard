# Portfolio Command

Unified portfolio dashboard across IBKR and IG accounts. Prices update daily via GitHub Actions using Yahoo Finance.

## Structure

```
data/holdings.json          # Position config (edit when you trade)
scripts/update_prices.py    # Fetches prices, outputs JSON
docs/index.html             # Dashboard UI
docs/data/portfolio.json    # Generated output (auto-committed by Actions)
.github/workflows/update.yml
```

## Setup

1. Create a GitHub repo and push this code
2. Enable GitHub Pages: Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder: `/docs`
3. The workflow runs automatically at 22:00 UTC (Mon–Fri) and can be triggered manually via Actions tab
4. Dashboard available at `https://<username>.github.io/<repo-name>/`
5. Raw JSON at `https://<username>.github.io/<repo-name>/data/portfolio.json`

## Updating Holdings

Edit `data/holdings.json` when you:
- Open a new position: add entry with ticker, shares, avgCost, account, theme
- Close a position: remove the entry
- Add/reduce shares: update shares and avgCost

Then either wait for the daily run or trigger manually.

### Yahoo Ticker Format
- US stocks: `AAPL`, `NVDA`
- London: `BRWM.L`, `SEMI.L`
- Taiwan: `2330.TW`
- Frankfurt: `HY9H.F`
- FX pairs fetched automatically: GBP/USD, EUR/USD, TWD/USD

### Margin Debt
Update `accounts.IBKR.marginDebt` in holdings.json when your margin balance changes.

## Local Development

```bash
pip install yfinance pandas
python scripts/update_prices.py
# Open docs/index.html in browser
```
