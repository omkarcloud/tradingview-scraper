"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. Params go through the same schemas the API uses, so defaults
are filled in and a ticker, EXCHANGE:TICKER or symbol link all work.
"""
import json
import os

from tradingview import api, schemas

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


def run(schema_cls, fn, **params):
    return fn(**schema_cls().load(params))


if __name__ == "__main__":
    # price, market cap, valuation, dividends, earnings, analyst targets and FAQ in one call
    save("symbol_nvda.json", run(schemas.SymbolSchema, api.symbol_details, symbol="NASDAQ:NVDA"))

    # daily Bitcoin candles — 1-minute to monthly bars, up to 5,000 at a time
    save("history_btcusd_daily.json",
         run(schemas.SymbolsHistorySchema, api.symbol_history, symbol="BITSTAMP:BTCUSD", interval="1d", bars="30"))

    # today's top US gainers — 25 presets, any filter, 50 rows a page
    save("screener_us_gainers.json",
         run(schemas.ScreenerScanSchema, api.screener_scan, market="america", preset="gainers"))
