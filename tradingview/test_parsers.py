"""Offline tests for the TradingView parsers and reference resolvers.

    python -m pytest tradingview/test_parsers.py -q

Fixtures are real responses captured 2026-11-03 (tradingview/fixtures/, see
parsers.py's docstring). No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingview import parsers as P, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


# ---- refs ----------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("NASDAQ:AAPL", "NASDAQ:AAPL"), ("aapl", "AAPL"), ("BINANCE:BTCUSDT.P", "BINANCE:BTCUSDT.P"),
    ("CBOT_MINI:10Y1!", "CBOT_MINI:10Y1!"),
    ("https://www.tradingview.com/symbols/NASDAQ-AAPL/", "NASDAQ:AAPL"),
    ("https://www.tradingview.com/symbols/NASDAQ-AAPL/financials-income-statement/", "NASDAQ:AAPL"),
    ("https://www.tradingview.com/symbols/BTCUSD/?exchange=CRYPTO", "CRYPTO:BTCUSD"),
    ("https://www.tradingview.com/symbols/XAUUSD/", "XAUUSD"),
    ("https://www.tradingview.com/chart/?symbol=BINANCE%3ABTCUSDT", "BINANCE:BTCUSDT"),
    ("//www.tradingview.com/symbols/NSE-RELIANCE/", "NSE:RELIANCE"),
])
def test_resolve_symbol(value, expected):
    assert refs.resolve_symbol(value) == expected


@pytest.mark.parametrize("value", ["", "https://example.com/symbols/NASDAQ-AAPL/", "https://www.tradingview.com/u/x/",
                                   "A:B:C", "ticker with spaces and more"])
def test_resolve_symbol_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_symbol(value)


def test_resolve_records():
    assert refs.resolve_idea("https://www.tradingview.com/chart/AAPL/qNLedwY9-Apple-AAPL-Is/") == "qNLedwY9"
    assert refs.resolve_idea("qNLedwY9") == "qNLedwY9"
    assert refs.resolve_script("https://www.tradingview.com/script/iKBJt1S8-Edo-Range-State/") == "iKBJt1S8"
    assert refs.resolve_mind("https://www.tradingview.com/symbols/NASDAQ-AAPL/minds/?mind=YBPAw86OQ5y0P_rrBEJgYQ") == "YBPAw86OQ5y0P_rrBEJgYQ"
    assert refs.resolve_story("https://www.tradingview.com/news/DJN_DN20261103001622:0-court-enters/") == "DJN_DN20261103001622:0"
    assert refs.resolve_story("moodys:4e028df70c3f1:0") == "moodys:4e028df70c3f1:0"
    assert refs.resolve_user("https://www.tradingview.com/u/moneyflow_trader/#published-ideas") == "moneyflow_trader"
    for fn, bad in [(refs.resolve_idea, "https://www.tradingview.com/ideas/crypto/"), (refs.resolve_script, "iKBJt1S"),
                    (refs.resolve_mind, "https://www.tradingview.com/symbols/NASDAQ-AAPL/minds/"),
                    (refs.resolve_story, "https://www.tradingview.com/news/"), (refs.resolve_user, "")]:
        with pytest.raises(ValueError):
            fn(bad)


def test_links_and_split():
    assert refs.symbol_link("NASDAQ:AAPL") == "https://www.tradingview.com/symbols/NASDAQ-AAPL/"
    assert refs.symbol_link("EURUSD") == "https://www.tradingview.com/symbols/EURUSD/"
    assert refs.split_symbol("NASDAQ:AAPL") == ("NASDAQ", "AAPL")
    assert refs.split_symbol("EURUSD") == (None, "EURUSD")
    assert refs.logo_link("apple") == "https://s3-symbol-logo.tradingview.com/apple.svg"
    assert refs.logo_link(None) is None
    assert refs.idea_link("/chart/AAPL/x-y/") == "https://www.tradingview.com/chart/AAPL/x-y/"


def test_tables_are_consistent():
    assert len(refs.MARKETS) == len(set(refs.MARKETS)) == 78
    assert all(p in refs.COLUMN_PRESETS for p in ("overview", "technicals", "cashflow"))
    for sort, order, filters in refs.SCREENER_PRESETS.values():
        assert order in ("asc", "desc")
        for left, op, _right in filters:
            assert op in refs.FILTER_OPERATIONS
    assert refs.INTERVALS["1d"] == ("", "1D") and refs.INTERVALS["1mo"] == ("|1M", "1M")


# ---- value helpers -------------------------------------------------------------------

def test_value_helpers():
    assert P.epoch_date(1793707200) == "2026-11-03"
    assert P.epoch_date(None) is None
    assert P.epoch_datetime(1793694281) == "2026-11-03T08:24:41+00:00"
    assert P.iso_datetime("2026-10-27T20:38:43.411516Z") == "2026-10-27T20:38:43+00:00"
    assert P.iso_datetime("2026-11-03T09:12:07+00:00") == "2026-11-03T09:12:07+00:00"
    assert P.iso_datetime(None) is None
    assert P.clean(" N/A ") is None and P.clean("") is None and P.clean(0) == 0
    assert [P.rating_label(v) for v in (0.7, 0.3, 0, -0.3, -0.8, None)] == \
        ["strong_buy", "buy", "neutral", "sell", "strong_sell", None]
    assert P.field_key("market_cap_basic") == "market_cap"
    assert P.field_key("Perf.YTD") == "performance_ytd"
    assert P.field_key("RSI|1W") == "rsi_1w"
    assert P.field_key("Stoch.K[1]") == "stoch_k_prev1"


def test_ast_text():
    story = fixture("news_story_tradingview.json")
    text = P.ast_text(story["astDescription"])
    assert text.startswith("- Apple (AAPL) beat fiscal Q4 estimates")
    assert "stocktwits" not in text          # story-refs dropped
    mind = fixture("mind_detail.json")
    assert P.ast_text(mind["text_ast"]).startswith("AAPL the after hours")


# ---- scanner -------------------------------------------------------------------------

STOCK_COLUMNS = ["name", "description", "logoid", "update_mode", "type", "typespecs", "close", "pricescale", "minmov",
                 "fractional", "minmove2", "currency", "change", "volume", "relative_volume_10d_calc",
                 "market_cap_basic", "fundamental_currency_code", "price_earnings_ttm",
                 "earnings_per_share_diluted_ttm", "earnings_per_share_diluted_yoy_growth_ttm",
                 "dividends_yield_current", "sector.tr", "market", "sector", "recommendation_mark", "exchange",
                 "Recommend.All", "RSI"]


def test_parse_scan_stocks():
    total, rows = P.parse_scan(fixture("scan_america_stocks.json"), STOCK_COLUMNS)
    assert total == 7467 and len(rows) == 50
    aapl = rows[0]
    assert aapl["symbol"] == "NASDAQ:AAPL" and aapl["ticker"] == "AAPL" and aapl["exchange"] == "NASDAQ"
    assert aapl["link"] == "https://www.tradingview.com/symbols/NASDAQ-AAPL/"
    assert aapl["name"] == "Apple Inc." and aapl["logo"] == "https://s3-symbol-logo.tradingview.com/apple.svg"
    assert aapl["price"] == 338.32 and aapl["market_cap"] == pytest.approx(4937502941831.124)
    assert aapl["change_percent"] == pytest.approx(-1.8309, abs=1e-3)
    assert aapl["technical_rating"] == pytest.approx(-0.1121, abs=1e-3) and aapl["rsi"] == pytest.approx(47.87, abs=0.01)
    assert aapl["data_mode"] == "delayed_streaming_900" and aapl["typespecs"] == ["common"]
    assert aapl["exchange"] == "NASDAQ"


def test_parse_scan_custom_columns_keep_raw_names():
    total, rows = P.parse_scan(fixture("scan_quotes_batch.json"),
                               ["name", "description", "close", "change", "volume", "market_cap_basic", "Recommend.All",
                                "RSI", "type", "exchange", "currency", "logoid", "update_mode"], rename=False)
    assert total == 6 and rows[2]["symbol"] == "BINANCE:BTCUSDT"
    assert rows[2]["market_cap_basic"] is None and rows[2]["close"] == 76834.01
    assert rows[0]["Recommend.All"] == pytest.approx(-0.112, abs=1e-3)


def test_parse_scan_coins_and_etfs():
    total, rows = P.parse_scan(fixture("scan_coin.json"), [
        "base_currency", "base_currency_desc", "base_currency_logoid", "update_mode", "type", "typespecs", "exchange",
        "crypto_total_rank", "close", "pricescale", "minmov", "fractional", "minmove2", "currency", "24h_close_change|5",
        "market_cap_calc", "fundamental_currency_code", "24h_vol_cmc", "circulating_supply",
        "crypto_common_categories.tr", "Recommend.All"])
    assert total == 2450 and rows[0]["symbol"] == "CRYPTO:BTCUSD" and rows[0]["ticker"] == "BTC"
    assert rows[0]["name"] == "Bitcoin" and rows[0]["rank"] == 1 and rows[0]["crypto_common_categories_tr"] == ["Cryptocurrencies", "Layer 1"]
    assert rows[0]["logo"] == "https://s3-symbol-logo.tradingview.com/crypto/XTVCBTC.svg"
    total, rows = P.parse_scan(fixture("scan_america_etf.json"),
                               ["name", "description", "close", "change", "aum", "fund_flows.1M", "expense_ratio",
                                "nav_total_return.1Y", "focus.tr", "asset_class.tr"])
    assert total == 6109 and rows[0]["symbol"] == "AMEX:VOO" and rows[0]["aum"] > 1e12
    assert rows[0]["focus"] == "Large cap" and rows[0]["asset_class"] == "Equity" and rows[0]["fund_flows_1m"] > 0


def test_parse_scan_calendars_dates():
    total, rows = P.parse_scan(fixture("scan_earnings_calendar.json"), [
        "logoid", "name", "description", "earnings_per_share_forecast_next_fq", "earnings_per_share_fq",
        "eps_surprise_fq", "eps_surprise_percent_fq", "revenue_forecast_next_fq", "revenue_fq",
        "earnings_release_next_date", "earnings_release_date", "earnings_release_next_time", "earnings_release_time",
        "market_cap_basic", "earnings_publication_type_next_fq", "earnings_publication_type_fq", "currency",
        "fundamental_currency_code"])
    assert total == 1505 and rows[0]["symbol"] == "NYSE:BRK.A"
    assert rows[0]["earnings_release_next_date"] == "2026-11-03" and rows[0]["earnings_release_date"] == P.epoch_date(1786223520)
    assert rows[0]["earnings_per_share_fq"] == pytest.approx(9030.337331)
    total, rows = P.parse_scan(fixture("scan_dividends_calendar.json"), list(refs.DIVIDEND_COLUMNS)[:1] + [
        "name", "description", "dividend_ex_date_upcoming", "dividend_payment_date_upcoming", "dividends_per_share_fq",
        "dividend_amount_upcoming", "dividends_yield_current", "dividend_frequency", "dividend_ex_date_recent",
        "dividend_payment_date_recent", "dividend_amount_recent", "market_cap_basic", "currency"])
    assert total == 127 and rows[0]["symbol"] == "NYSE:WFC"
    assert rows[0]["dividend_ex_date_upcoming"] == "2026-11-06" and rows[0]["dividend_amount_upcoming"] == 0.5
    assert rows[0]["dividends_per_share_fq"] is None


def test_parse_scan_empty_and_error_payloads():
    assert P.parse_scan({"totalCount": 0, "data": []}, ["name"]) == (0, [])
    assert P.parse_scan(None, ["name"]) == (None, [])
    assert P.parse_scan({"data": [{"s": "X:Y"}]}, ["name", "close"]) == (None, [
        {"symbol": "X:Y", "ticker": "Y", "exchange": "X", "link": "https://www.tradingview.com/symbols/X-Y/"}])


def test_parse_symbol_fields_profile():
    fields = ["description", "business_description", "web_site_url", "number_of_employees", "isin", "sector", "industry",
              "exchange", "total_revenue_fq_h", "price_target_average", "recommendation_buy", "dividend_ex_date_upcoming",
              "earnings_release_next_date", "High.All", "Perf.YTD", "float_shares_outstanding"]
    out = P.parse_symbol_fields(fixture("symbol_fields_aapl_profile.json"), fields)
    assert out["name"] == "Apple Inc." and out["business_description"] is None and out["employees"] == 166000
    assert out["isin"] == "US0378331005" and out["industry"] == "Telecommunications Equipment"
    assert out["total_revenue_fq_h"][:2] == [109417000000, 111184000000]
    assert out["price_target_average"] == pytest.approx(334.646576) and out["recommendation_buy"] == 18
    assert out["dividend_ex_date_upcoming"] is None and out["earnings_release_next_date"] == P.epoch_date(1801742400)
    assert out["all_time_high"] == 351.73 and out["performance_ytd"] == pytest.approx(24.27, abs=0.01)
    assert P.parse_symbol_fields(None, ["close"]) == {"price": None}
    # two fields share one key: a later null never hides the earlier value
    merged = P.parse_symbol_fields({"logoid": "nvidia", "base_currency_logoid": None, "market_cap_basic": None,
                                    "market_cap_calc": 5}, ["logoid", "base_currency_logoid", "market_cap_basic", "market_cap_calc"])
    assert merged == {"logo": "https://s3-symbol-logo.tradingview.com/nvidia.svg", "market_cap": 5}


# ---- technicals / financials ---------------------------------------------------------

def test_technical_fields_and_parse():
    daily = P.technical_fields("")
    assert "Recommend.All" in daily and "Pivot.M.Classic.S1" in daily and "ADX+DI" in daily
    hourly = P.technical_fields("|60")
    assert hourly[0] == "Recommend.All|60" and "RSI[1]|60" in hourly
    out = P.parse_technicals(fixture("symbol_fields_aapl_technicals.json"), "")
    assert out["summary"] == {"rating": pytest.approx(-0.112, abs=1e-3), "label": "sell"}
    assert out["moving_averages"]["label"] in ("sell", "strong_sell", "neutral", "buy", "strong_buy")
    assert out["oscillator_values"]["rsi"] == pytest.approx(47.87, abs=0.01)
    assert out["oscillator_values"]["macd"] == pytest.approx(3.02, abs=0.01)
    assert out["moving_average_values"]["sma200"] == pytest.approx(296.96, abs=0.01)
    assert set(out["pivots"]) == {"classic", "fibonacci", "camarilla", "woodie", "demark"}
    assert out["pivots"]["classic"]["r1"] is not None and out["bollinger_bands"]["upper"] is not None
    assert out["indicator_signals"]["ichimoku"] in ("strong_buy", "buy", "neutral", "sell", "strong_sell")
    # the 15-min fields of the same fixture
    out15 = P.parse_technicals(fixture("symbol_fields_aapl_technicals.json"), "|15")
    assert out15["oscillator_values"]["rsi"] == pytest.approx(48.23, abs=0.01) and out15["summary"]["label"] == "neutral"
    assert out15["pivots"]["classic"]["r1"] is None


def test_statement_fields_and_parse():
    fields = P.statement_fields("income", "fy")
    assert "total_revenue_fy_h" in fields and "fiscal_period_fy_h" in fields and "total_revenue_ttm" in fields
    out = P.parse_statement(fixture("symbol_fields_aapl_financials.json"), "income", "fy")
    assert out["currency"] == "USD" and out["periods"][:3] == [2025, 2024, 2023]
    assert out["history"]["revenue"][:2] == [416161000000, 391035000000]
    assert out["history"]["cost_of_goods"] is None          # kept for logged-in users
    assert out["latest"]["revenue"] == 416161000000 and out["trailing_twelve_months"]["net_income"] > 0
    out_q = P.parse_statement(fixture("symbol_fields_aapl_financials.json"), "income", "fq")
    assert out_q["periods"] is None and out_q["history"]["revenue"][0] == 109417000000
    out_b = P.parse_statement(fixture("symbol_fields_aapl_financials.json"), "balance", "fy")
    assert out_b["history"]["total_assets"][0] == 359241000000 and out_b["history"]["net_debt"] is None
    empty = P.parse_statement({}, "cashflow", "fy")
    assert empty["periods"] is None and empty["trailing_twelve_months"] is None and set(empty["history"]) == set(refs.STATEMENTS["cashflow"])


# ---- search --------------------------------------------------------------------------

def test_parse_search():
    results, remaining = P.parse_search(fixture("symbol_search_apple.json"))
    assert remaining == 943 and len(results) == 50
    assert results[0]["symbol"] == "NASDAQ:AAPL" and results[0]["name"] == "Apple Inc."
    assert results[0]["isin"] == "US0378331005" and results[0]["is_primary_listing"] is True
    assert results[0]["exchange_name"] == "Nasdaq Stock Market" and results[0]["logo"].endswith("/apple.svg")
    assert "<em>" not in json.dumps(results)
    assert P.parse_search(fixture("symbol_search_nomatch.json")) == ([], 0)
    crypto, _ = P.parse_search(fixture("symbol_search_crypto_a.json"))
    assert crypto and all(":" in r["symbol"] for r in crypto)


# ---- news ----------------------------------------------------------------------------

def test_parse_news_feed():
    items = [P.parse_news_item(i) for i in fixture("news_flow_aapl.json")["items"]]
    assert len(items) == 200
    first = items[0]
    assert first["id"] == "moodys:4e028df70c3f1:0" and first["published"] == "2026-11-03T08:24:41+00:00"
    assert first["link"].startswith("https://www.tradingview.com/news/moodys:4e028df70c3f1:0-")
    assert first["provider"] == {"id": "asian_news_international", "name": "Asian News International", "link": None}
    assert first["related_symbols"][0]["symbol"] == "NASDAQ:AAPL" and first["is_paywalled"] is False
    stocktwits = items[1]
    assert stocktwits["source_link"].startswith("https://stocktwits.com/") and stocktwits["provider"]["link"] == "https://stocktwits.com/"
    assert any(i["is_paywalled"] for i in items)


def test_parse_story():
    story = P.parse_story(fixture("news_story_tradingview.json"))
    assert story["title"].startswith("Key facts: Apple Beats Q4") and story["is_paywalled"] is False
    assert story["text"].startswith("- Apple (AAPL) beat fiscal Q4") and "\n\n\n" not in story["text"]
    assert story["related_symbols"][0]["symbol"] == "NASDAQ:AAPL" and story["language"] == "en"
    reuters = P.parse_story(fixture("news_story_reuters.json"))
    assert reuters["provider"]["id"] == "reuters" and reuters["text"].startswith("By Mike Dolan")
    assert reuters["is_paywalled"] is True and reuters["is_preview"] is True and reuters["permission"] == "headline"
    assert fixture("news_story_unknown.json")["status"] == "error"


# ---- economic calendar ---------------------------------------------------------------

def test_parse_economic_event():
    events = [P.parse_economic_event(e) for e in fixture("economic_calendar_week.json")["result"]]
    assert len(events) == 195
    first = events[0]
    assert first["title"] == "S&P Global Manufacturing PMI Final" and first["country"] == "JP"
    assert first["date"] == "2026-11-02T00:30:00+00:00" and first["importance"] == "low"
    assert first["source"] == "Markit" and first["source_link"] is None and first["description"].startswith("The Purchasing")
    with_actual = [e for e in events if e["actual"] is not None]
    assert with_actual and all(e["importance"] in ("low", "medium", "high") for e in events)


# ---- ideas ---------------------------------------------------------------------------

def test_parse_feed_page_and_api_list():
    items, total, has_next = P.parse_feed_page(fixture("ideas_page_aapl.json"))
    assert total == 1000 and has_next is True and len(items) == 24
    first = items[0]
    assert first["id"] == "qNLedwY9" and first["numeric_id"] == 23999383
    assert first["title"].startswith("Apple (AAPL)") and first["link"].startswith("https://www.tradingview.com/chart/AAPL/qNLedwY9-")
    assert first["published"] == "2026-10-27T20:38:43+00:00" and first["interval"] == "1W" and first["direction"] == "neutral"
    assert first["symbol"]["symbol"] == "NASDAQ:AAPL" and first["symbol"]["logo"].endswith("/apple.svg")
    assert first["likes"] == 18 and first["comments_count"] == 13 and first["is_hot"] is True
    assert first["author"]["username"] == "Mehdi_Abbasi_EWP" and first["author"]["link"] == "https://www.tradingview.com/u/Mehdi_Abbasi_EWP/"
    assert "script" not in first
    assert {i["direction"] for i in items} <= {"neutral", "long", "short"}
    items, count, size, pages = P.parse_api_list(fixture("ideas_api_aapl.json"))
    assert count == 1000 and size == 24 and pages == 42 and len(items) == 24
    assert P.parse_feed_page({}) == ([], None, False) and P.parse_api_list(None) == ([], None, None, None)


def test_parse_idea_detail_and_comments():
    detail = P.parse_idea_detail(fixture("idea_detail_qNLedwY9.json"))
    assert detail["id"] == "qNLedwY9" and detail["views"] == 626 and detail["likes"] == 18
    assert detail["text"].startswith("**Reading time: 3 minutes**")
    assert detail["symbol"]["symbol"] == "NASDAQ:AAPL" and detail["symbol"]["name"] == "Apple Inc"
    assert detail["tags"][0] == {"tag": "mtfa", "title": "Multiple Time Frame Analysis",
                                 "ideas_link": "https://www.tradingview.com/ideas/mtfa/",
                                 "scripts_link": "https://www.tradingview.com/scripts/mtfa/"}
    assert detail["related_ideas"][0]["id"] == "EYbQQsEL" and detail["related_ideas"][0]["symbol"] == "PYTH:TSLA"
    assert detail["author"]["socials"]["twitter"] == "NobodyElliott" and detail["author"]["socials"]["youtube"].startswith("https://www.youtube.com/")
    assert detail["image"] == "https://s3.tradingview.com/q/qNLedwY9_big.png" and detail["video"] is None
    assert "script" not in detail
    comments, has_next = P.parse_comments(fixture("idea_comments_qNLedwY9.json"))
    assert has_next is False and comments[0]["id"] == 15511269 and comments[0]["text"] == "Amazing excited work"
    assert comments[0]["replies_count"] == 3 and comments[0]["author"]["username"] == "MrErick_yt_Analysis"
    assert comments[0]["author"]["badges"] == ["Premium"] and comments[0]["platform"] == "android"
    replies, _ = P.parse_comments(fixture("idea_comment_replies_15511269.json"))
    assert replies[0]["parent_id"] == 15511269 and replies[0]["text"].startswith("@MrErick_yt_Analysis")
    assert P.parse_comments(None) == ([], False)
    assert fixture("idea_detail_unknown.json")["detail"] == "No Chart matches the given query."


def test_parse_search_pages():
    """The site's own text search: /ideas/search/<q>/ and /scripts/search/<q>/."""
    items, total, has_next = P.parse_feed_page(fixture("ideas_search_page_nvidia.json"))
    assert total == 1000 and has_next and len(items) == 24
    assert all("nvidia" in (i["title"] + (i["description"] or "") + i["symbol"]["symbol"]).lower() for i in items[:5])
    items, total, has_next = P.parse_feed_page(fixture("scripts_search_page_squeeze_momentum.json"))
    assert total == 189 and has_next and "squeeze" in items[0]["title"].lower() and items[0]["script"]["pine_id"]
    assert P.parse_feed_page(fixture("ideas_search_page_empty.json")) == ([], 0, False)


# ---- scripts -------------------------------------------------------------------------

def test_parse_scripts_lists():
    items, total, has_next = P.parse_feed_page(fixture("scripts_page_indicators_recent.json"))
    assert total == 12000 and has_next and items[0]["script"] == {
        "type": "indicator", "access": "open_source", "pine_id": "PUB;8eb87677ae7d4fcfb0a84aee27e29405", "version": "1"}
    assert items[0]["link"].startswith("https://www.tradingview.com/script/mFMTYEYR-")
    items, count, _, _ = P.parse_api_list(fixture("scripts_api_by_tradingview.json"))
    assert count == 38 and all(i["author"]["username"] == "TradingView" for i in items)
    assert all(i["script"]["type"] in ("indicator", "strategy", "library") for i in items)
    items, count, _, _ = P.parse_api_list(fixture("scripts_api_strategies_rsi.json"))
    assert all(i["script"]["type"] == "strategy" for i in items)
    assert fixture("scripts_api_unknown_user.json")["code"] == "wrong_parameter_request"


def test_parse_script_page_and_pine():
    record = P.parse_script_page(fixture("script_page_iKBJt1S8.html"))
    assert record["id"] == "iKBJt1S8" and record["title"] == "Edo Range State"
    assert record["link"] == "https://www.tradingview.com/script/iKBJt1S8-Edo-Range-State/"
    assert record["script"] == {"type": "indicator", "access": "open_source", "pine_id": "PUB;743b29e24b554405b37bbd5eebb9a2be",
                                "version": 1, "library_id": None, "terms": None}
    assert record["likes"] == 16 and record["views"] == 251 and record["symbol"]["symbol"] == "NASDAQ:NVDA"
    assert record["author"]["username"] == "EdoLab-Markets" and record["author"]["socials"]["website"] == "https://www.edolab.io"
    assert record["image"].endswith("iKBJt1S8_big.png?v=1793636589") and record["text"].startswith("Edo Range State")
    assert record["tags"][0]["tag"] == "breakout"
    second = P.parse_script_page(fixture("script_page_protected.html"))
    assert second["id"] == "CDQo43CF" and second["symbol"]["symbol"] == "FX:XAUUSD" and second["interval"] == "5"
    assert P.parse_script_page(fixture("symbol_page_unknown.html")) is None
    assert P.parse_script_page("") is None
    pine = P.parse_pine(fixture("pine_source_open.json"))
    assert pine["name"] == "Strong Pressure Signals" and pine["access"] == "open_no_auth" and pine["kind"] == "study"
    assert pine["source"].startswith("//@version=6") and pine["created"] == "2026-11-02T11:38:48+00:00"
    assert P.parse_pine(fixture("pine_source_protected.json")) is None and P.parse_pine(None) is None


# ---- minds ---------------------------------------------------------------------------

def test_parse_minds():
    posts, cursor = P.parse_minds(fixture("minds_aapl.json"))
    assert cursor == "Im8iOiItaWQiLCJ2IjpbMzQ2MjY3NV0" and len(posts) == 20
    first = posts[0]
    assert first["id"] == "YBPAw86OQ5y0P_rrBEJgYQ" and first["text"].startswith("$AAPL the after hours")
    assert first["link"] == "https://www.tradingview.com/symbols/NASDAQ-AAPL/minds/?mind=YBPAw86OQ5y0P_rrBEJgYQ"
    assert first["published"] == "2026-11-03T00:25:47+00:00" and first["likes"] == 6 and first["comments_count"] == 1
    assert first["symbols"][0] == {"symbol": "NASDAQ:AAPL", "link": "https://www.tradingview.com/symbols/NASDAQ-AAPL/",
                                   "name": "Apple Inc", "ticker": "AAPL", "logo": "https://s3-symbol-logo.tradingview.com/apple.svg"}
    assert first["author"]["username"] == "moneyflow_trader" and first["author"]["picture"] is None   # data: URI avatar
    detail = P.parse_mind(fixture("mind_detail.json"))
    assert detail["id"] == first["id"] and detail["symbols"][0]["symbol"] == "NASDAQ:AAPL" and detail["symbols"][0]["name"] is None
    comments = [P.parse_mind_comment(c) for c in fixture("mind_comments.json")]
    assert comments[0]["author"]["username"] == "kensington201" and comments[0]["text"].startswith("stock has been propped")
    assert P.parse_minds(fixture("minds_empty.json")) == ([], None)


# ---- users ---------------------------------------------------------------------------

def test_parse_user_profile():
    profile = P.parse_user_profile(fixture("user_profile_tradingview.json"))
    assert profile["username"] == "TradingView" and profile["id"] == 6171439
    assert profile["link"] == "https://www.tradingview.com/u/TradingView/"
    assert profile["stats"] == {"followers": 795600, "following": 447, "ideas": 512, "scripts": 38}
    assert profile["joined"] == P.epoch_datetime(1315641759.0) == "2011-09-10T08:02:39+00:00" and profile["badges"] == ["TradingView employee", "TradingView moderator", "Ultimate"]
    assert profile["socials"]["twitter"] == "TradingView" and profile["socials"]["youtube"].startswith("https://www.youtube.com/")
    assert profile["bio"] is None and profile["is_banned"] is False
    assert fixture("user_profile_unknown.json") == {"code": 404, "locale": "en"}


# ---- symbol page / markets -------------------------------------------------------------

def test_parse_symbol_page():
    page = P.parse_symbol_page(fixture("symbol_page_aapl.html"))
    assert page["description"].startswith("Apple, Inc engages in the design") and page["category"] == "Stock"
    assert page["faq"][0]["question"] == "What is Apple Inc stock price today?" and "338.32" in page["faq"][0]["answer"]
    assert page["symbol_info"]["isin_displayed"] == "US0378331005" and page["symbol_info"]["timezone"] == "America/New_York"
    btc = P.parse_symbol_page(fixture("symbol_page_btcusd.html"))
    assert btc["description"].startswith("Bitcoin is the world") and btc["symbol_info"]["is_crypto"] is True
    unknown = P.parse_symbol_page(fixture("symbol_page_unknown.html"))
    assert unknown["description"] is None and unknown["faq"] == []
    assert P.parse_symbol_page("")["symbol_info"] is None


def test_parse_symbol_markets():
    total, rows = P.parse_symbol_markets(fixture("symbol_markets_btcusd.json"))
    assert total == 289 and len(rows) == 100     # the tab embeds one page of values
    first = rows[0]
    assert first["symbol"] == "COINBASE:BTCUSD.P" and first["name"] == "BTC / USD PERPETUAL CONTRACT"
    assert first["exchange_name"] == "Coinbase" and first["type"] == "swap" and first["price"] == 76742
    assert first["change_percent"] == pytest.approx(0.0417, abs=1e-3) and first["logo"].endswith("XTVCBTC.svg")
    assert "technical_rating_label" in first
    assert P.parse_symbol_markets(None) == (None, [])


# ---- chart websocket -----------------------------------------------------------------

def test_parse_ws_frames():
    out = P.parse_ws_frames(fixture("ws_frames_aapl_1d.json"))
    assert out["error"] is None and len(out["bars"]) == 50
    assert out["bars"][0]["timestamp"] < out["bars"][-1]["timestamp"]
    last = out["bars"][-1]
    assert set(last) == {"time", "timestamp", "open", "high", "low", "close", "volume"} and last["close"] == 338.32
    assert out["symbol_info"]["symbol"] == "NASDAQ:AAPL" and out["symbol_info"]["currency"] == "USD"
    assert out["symbol_info"]["exchange"] in ("NASDAQ", "BATS", "Cboe One")   # anonymous US stocks resolve to Cboe One
    btc = P.parse_ws_frames(fixture("ws_frames_btcusdt_60.json"))
    assert len(btc["bars"]) == 20 and btc["symbol_info"]["symbol"] == "BINANCE:BTCUSDT"
    unknown = P.parse_ws_frames(fixture("ws_frames_unknown.json"))
    assert unknown["error"] == "invalid symbol" and unknown["bars"] == []
    assert P.parse_ws_frames([]) == {"error": None, "bars": [], "symbol_info": None}


def test_script_details_without_pine_id(monkeypatch):
    """A script page whose ssrIdeaData carries no script_id_part must answer
    with source null, not crash on None.startswith."""
    from tradingview import api
    monkeypatch.setattr(api.fetch, "script_page", lambda uuid: "<html></html>")
    monkeypatch.setattr(api.parsers, "parse_script_page",
                        lambda html: {"id": "abcdefgh", "script": {"pine_id": None, "type": "indicator"}})
    record = api._script_details("abcdefgh")
    assert record["source"] is None and record["is_source_available"] is False
