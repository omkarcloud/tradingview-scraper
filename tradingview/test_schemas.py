"""Offline tests for the /tradingview/* request schemas.

    python -m pytest tradingview/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingview import refs, schemas  # noqa: E402


# ---- symbols -----------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("NASDAQ:AAPL", "NASDAQ:AAPL"),
    ("nasdaq:aapl", "NASDAQ:AAPL"),
    ("AAPL", "AAPL"),
    ("btcusd", "BTCUSD"),
    ("NQ1!", "NQ1!"),
    ("https://www.tradingview.com/symbols/NASDAQ-AAPL/", "NASDAQ:AAPL"),
    ("https://www.tradingview.com/symbols/NASDAQ-AAPL/ideas/", "NASDAQ:AAPL"),
    ("https://www.tradingview.com/symbols/BTCUSD/?exchange=CRYPTO", "CRYPTO:BTCUSD"),
    ("https://www.tradingview.com/symbols/EURUSD/", "EURUSD"),
    ("https://www.tradingview.com/chart/?symbol=NASDAQ%3AAAPL", "NASDAQ:AAPL"),
    ("https://in.tradingview.com/symbols/NSE-RELIANCE/", "NSE:RELIANCE"),
])
def test_symbol_schema_accepts(value, expected):
    assert schemas.SymbolSchema().load({"symbol": value}) == {"symbol": expected}


@pytest.mark.parametrize("value", ["", "https://example.com/symbols/NASDAQ-AAPL/", "https://www.tradingview.com/news/",
                                   "NASDAQ:AAPL:X", "a b c d"])
def test_symbol_schema_rejects(value):
    with pytest.raises(ValidationError) as exc:
        schemas.SymbolSchema().load({"symbol": value})
    assert "symbol" in exc.value.messages


def test_symbol_schema_rejects_sibling_params():
    with pytest.raises(ValidationError):
        schemas.SymbolSchema().load({"symbol": "AAPL", "url": "https://www.tradingview.com/symbols/NASDAQ-AAPL/"})


def test_quote_schema_list():
    loaded = schemas.SymbolsQuoteSchema().load({"symbol": "NASDAQ:AAPL, aapl ,https://www.tradingview.com/symbols/BTCUSD/?exchange=CRYPTO"})
    assert loaded == {"symbol": ["NASDAQ:AAPL", "AAPL", "CRYPTO:BTCUSD"]}
    with pytest.raises(ValidationError):
        schemas.SymbolsQuoteSchema().load({"symbol": ",".join(f"S{i}" for i in range(21))})
    with pytest.raises(ValidationError):
        schemas.SymbolsQuoteSchema().load({})


def test_search_schema():
    loaded = schemas.SymbolsSearchSchema().load({"query": " apple ", "type": "ETF", "page": "2"})
    assert loaded == {"query": "apple", "type": "funds", "exchange": None, "page": 2}
    with pytest.raises(ValidationError) as exc:
        schemas.SymbolsSearchSchema().load({"query": "apple", "type": "bonds"})
    assert "type" in exc.value.messages
    with pytest.raises(ValidationError):
        schemas.SymbolsSearchSchema().load({})


def test_technicals_schema():
    loaded = schemas.SymbolsTechnicalsSchema().load({"symbol": "AAPL"})
    assert loaded == {"symbol": "AAPL", "interval": "1d"}
    assert schemas.SymbolsTechnicalsSchema().load({"symbol": "AAPL", "interval": "1MO"})["interval"] == "1mo"
    with pytest.raises(ValidationError) as exc:
        schemas.SymbolsTechnicalsSchema().load({"symbol": "AAPL", "interval": "3d"})
    assert "interval" in exc.value.messages


def test_financials_schema():
    loaded = schemas.SymbolsFinancialsSchema().load({"symbol": "AAPL", "statement": "Balance", "period": "quarterly"})
    assert loaded == {"symbol": "AAPL", "statement": "balance", "period": "quarterly"}
    assert schemas.SymbolsFinancialsSchema().load({"symbol": "AAPL"})["statement"] == "income"
    with pytest.raises(ValidationError):
        schemas.SymbolsFinancialsSchema().load({"symbol": "AAPL", "statement": "pnl"})


def test_history_schema():
    loaded = schemas.SymbolsHistorySchema().load({"symbol": "BTCUSD", "interval": "1h", "bars": "50"})
    assert loaded == {"symbol": "BTCUSD", "interval": "1h", "bars": 50}
    assert schemas.SymbolsHistorySchema().load({"symbol": "BTCUSD"})["bars"] == 300
    with pytest.raises(ValidationError) as exc:
        schemas.SymbolsHistorySchema().load({"symbol": "BTCUSD", "bars": "5001"})
    assert "bars" in exc.value.messages
    with pytest.raises(ValidationError):
        schemas.SymbolsHistorySchema().load({"symbol": "BTCUSD", "bars": "0"})


# ---- screener ----------------------------------------------------------------------

def test_screener_schema_defaults():
    loaded = schemas.ScreenerScanSchema().load({})
    assert loaded == {"market": "america", "preset": None, "filters": None, "columns": None, "sort": None,
                      "order": None, "page": 1}


def test_screener_schema_filters_and_columns():
    loaded = schemas.ScreenerScanSchema().load({
        "market": "India", "preset": "Gainers",
        "filters": "market_cap_basic:greater:1000000000, RSI:in_range:30|70,sector:equal:Finance,is_primary:equal:true",
        "columns": "performance,RSI,Perf.YTD", "sort": "Perf.YTD", "order": "ASC", "page": "3"})
    assert loaded["market"] == "india" and loaded["preset"] == "gainers"
    assert loaded["filters"] == [
        {"left": "market_cap_basic", "operation": "greater", "right": 1000000000},
        {"left": "RSI", "operation": "in_range", "right": [30, 70]},
        {"left": "sector", "operation": "equal", "right": "Finance"},
        {"left": "is_primary", "operation": "equal", "right": True},
    ]
    assert loaded["columns"]["custom"] is True
    assert loaded["columns"]["fields"][:3] == list(refs.COLUMN_PRESETS["performance"][:3])
    assert "RSI" in loaded["columns"]["fields"] and loaded["columns"]["fields"].count("Perf.YTD") == 1
    assert loaded["sort"] == "Perf.YTD" and loaded["order"] == "asc" and loaded["page"] == 3


@pytest.mark.parametrize("params,field", [
    ({"market": "mars"}, "market"),
    ({"preset": "moon-shots"}, "preset"),
    ({"filters": "RSI:frobnicate:3"}, "filters"),
    ({"filters": "RSI<30"}, "filters"),
    ({"filters": "RSI:less:"}, "filters"),
    ({"columns": "drop table"}, "columns"),
    ({"sort": "a b"}, "sort"),
    ({"order": "up"}, "order"),
    ({"page": "401"}, "page"),
])
def test_screener_schema_rejects(params, field):
    with pytest.raises(ValidationError) as exc:
        schemas.ScreenerScanSchema().load(params)
    assert field in exc.value.messages


def test_crypto_and_etf_schemas():
    assert schemas.ScreenerCryptoSchema().load({}) == {"sort": "crypto_total_rank", "order": None, "page": 1}
    assert schemas.ScreenerCryptoSchema().load({"sort": "Volume"})["sort"] == "24h_vol_cmc"
    assert schemas.ScreenerEtfSchema().load({"market": "uk", "sort": "return_1y"}) == {
        "market": "uk", "sort": "nav_total_return.1Y", "order": None, "page": 1}
    with pytest.raises(ValidationError):
        schemas.ScreenerEtfSchema().load({"market": "crypto"})


# ---- calendars ---------------------------------------------------------------------

def test_calendar_schemas():
    loaded = schemas.CalendarEconomicSchema().load({"from": "2026-11-03", "to": "2026-11-10", "countries": "us, eu,gb", "importance": "High"})
    assert loaded == {"from_date": "2026-11-03", "to_date": "2026-11-10", "countries": ["US", "EU", "GB"], "importance": 1}
    assert schemas.CalendarEconomicSchema().load({})["countries"] is None
    with pytest.raises(ValidationError) as exc:
        schemas.CalendarEconomicSchema().load({"from": "2026-11-10", "to": "2026-11-03"})
    assert "to" in exc.value.messages
    with pytest.raises(ValidationError) as exc:
        schemas.CalendarEconomicSchema().load({"from": "3 Nov 2026"})
    assert "from" in exc.value.messages
    loaded = schemas.CalendarEarningsSchema().load({"status": "Reported", "market": "japan"})
    assert loaded["status"] == "reported" and loaded["market"] == "japan" and loaded["page"] == 1
    assert schemas.CalendarDividendsSchema().load({})["market"] == "america"


# ---- news --------------------------------------------------------------------------

def test_news_schemas():
    loaded = schemas.NewsSearchSchema().load({"symbol": "aapl", "limit": "5"})
    assert loaded == {"symbol": "AAPL", "market": None, "provider": None, "top": None, "lang": "en", "limit": 5}
    assert schemas.NewsSearchSchema().load({"top": "true"})["top"] is True
    with pytest.raises(ValidationError):
        schemas.NewsSearchSchema().load({"top": "false"})
    with pytest.raises(ValidationError) as exc:
        schemas.NewsSearchSchema().load({"market": "stocks"})
    assert "market" in exc.value.messages
    with pytest.raises(ValidationError):
        schemas.NewsSearchSchema().load({"limit": "201"})
    for value, expected in [
        ("tradingview:ab5c900008e42:0", "tradingview:ab5c900008e42:0"),
        ("tag:reuters.com,2026:newsml_L6N46J0OT:0", "tag:reuters.com,2026:newsml_L6N46J0OT:0"),
        ("DJN_DN20261103001622:0", "DJN_DN20261103001622:0"),
        ("https://www.tradingview.com/news/tradingview:ab5c900008e42:0-key-facts-apple-beats-q4/", "tradingview:ab5c900008e42:0"),
        ("https://www.tradingview.com/news/tag:reuters.com,2026:newsml_L6N46J0OT:0-a-brutal-october/", "tag:reuters.com,2026:newsml_L6N46J0OT:0"),
    ]:
        assert schemas.NewsDetailsSchema().load({"story": value})["story"] == expected
    with pytest.raises(ValidationError):
        schemas.NewsDetailsSchema().load({"story": "https://www.tradingview.com/symbols/NASDAQ-AAPL/"})
    with pytest.raises(ValidationError):
        schemas.NewsDetailsSchema().load({"story": "hello"})


# ---- ideas / scripts ---------------------------------------------------------------

def test_ideas_search_schema():
    loaded = schemas.IdeasSearchSchema().load({"symbol": "NASDAQ:AAPL", "sort": "Popular", "type": "education"})
    assert loaded == {"symbol": "NASDAQ:AAPL", "user": None, "query": None, "topic": None, "type": "education",
                      "sort": "week_popular", "page": 1}
    assert schemas.IdeasSearchSchema().load({})["sort"] == "recent"
    assert schemas.IdeasSearchSchema().load({"topic": "Trend-Analysis"})["topic"] == "Trend-Analysis"
    assert schemas.IdeasSearchSchema().load({"user": "https://www.tradingview.com/u/TradingView/"})["user"] == "TradingView"
    with pytest.raises(ValidationError) as exc:
        schemas.IdeasSearchSchema().load({"topic": "crypto", "symbol": "AAPL"})
    assert "topic" in exc.value.messages
    with pytest.raises(ValidationError):
        schemas.IdeasSearchSchema().load({"topic": "crypto/../x"})
    assert schemas.IdeasSearchSchema().load({"query": "nvidia earnings"})["query"] == "nvidia earnings"
    with pytest.raises(ValidationError) as exc:
        schemas.IdeasSearchSchema().load({"query": "nvidia", "symbol": "NASDAQ:NVDA"})
    assert "query" in exc.value.messages
    with pytest.raises(ValidationError) as exc:
        schemas.IdeasSearchSchema().load({"topic": "crypto", "type": "education"})
    assert "type" in exc.value.messages
    with pytest.raises(ValidationError):
        schemas.IdeasSearchSchema().load({"page": "43"})


def test_idea_schema():
    assert schemas.IdeaSchema().load({"idea": "qNLedwY9"}) == {"idea": "qNLedwY9"}
    link = "https://www.tradingview.com/chart/AAPL/qNLedwY9-Apple-AAPL-Is-the-Larger-Wave-III-Still-Unfolding/"
    assert schemas.IdeaSchema().load({"idea": link}) == {"idea": "qNLedwY9"}
    assert schemas.IdeaCommentsSchema().load({"idea": link, "page": "2"})["page"] == 2
    for bad in ["qNLedwY", "qNLedwY9x", "https://www.tradingview.com/script/iKBJt1S8-Edo-Range-State/"]:
        with pytest.raises(ValidationError) as exc:
            schemas.IdeaSchema().load({"idea": bad})
        assert "idea" in exc.value.messages


def test_scripts_schemas():
    loaded = schemas.ScriptsSearchSchema().load({"query": "rsi", "type": "Strategy"})
    assert loaded == {"query": "rsi", "user": None, "tag": None, "type": "strategies", "sort": "week_popular", "page": 1}
    with pytest.raises(ValidationError) as exc:
        schemas.ScriptsSearchSchema().load({"tag": "rsi", "query": "x"})
    assert "tag" in exc.value.messages
    with pytest.raises(ValidationError) as exc:
        schemas.ScriptsSearchSchema().load({"query": "squeeze momentum", "user": "LazyBear"})
    assert "query" in exc.value.messages
    assert schemas.ScriptSchema().load({"script": "https://www.tradingview.com/script/iKBJt1S8-Edo-Range-State/"}) == {"script": "iKBJt1S8"}
    with pytest.raises(ValidationError):
        schemas.ScriptSchema().load({"script": "https://www.tradingview.com/chart/AAPL/qNLedwY9-x/"})


# ---- minds / users -----------------------------------------------------------------

def test_minds_schemas():
    assert schemas.MindsSearchSchema().load({"symbol": "AAPL"}) == {"symbol": "AAPL", "user": None, "cursor": None}
    assert schemas.MindsSearchSchema().load({"user": "moneyflow_trader", "cursor": "abc"})["cursor"] == "abc"
    with pytest.raises(ValidationError) as exc:
        schemas.MindsSearchSchema().load({})
    assert "symbol" in exc.value.messages
    with pytest.raises(ValidationError):
        schemas.MindsSearchSchema().load({"symbol": "AAPL", "user": "x"})
    uid = "YBPAw86OQ5y0P_rrBEJgYQ"
    assert schemas.MindSchema().load({"mind": uid}) == {"mind": uid}
    assert schemas.MindSchema().load({"mind": f"https://www.tradingview.com/symbols/NASDAQ-AAPL/minds/?mind={uid}"}) == {"mind": uid}
    with pytest.raises(ValidationError):
        schemas.MindSchema().load({"mind": "short"})


def test_user_schema():
    assert schemas.UserSchema().load({"user": "TradingView"}) == {"user": "TradingView"}
    assert schemas.UserSchema().load({"user": "https://www.tradingview.com/u/Mehdi_Abbasi_EWP/"}) == {"user": "Mehdi_Abbasi_EWP"}
    with pytest.raises(ValidationError) as exc:
        schemas.UserSchema().load({"user": "https://example.com/u/x/"})
    assert "user" in exc.value.messages
    with pytest.raises(ValidationError):
        schemas.UserSchema().load({"user": "has space"})


def test_every_field_documents_itself():
    """The metadata description becomes the public docs."""
    for name in dir(schemas):
        cls = getattr(schemas, name)
        if isinstance(cls, type) and issubclass(cls, schemas.BaseSchema) and cls is not schemas.BaseSchema \
                and not name.startswith("_"):
            for field_name, field in cls().fields.items():
                assert field.metadata.get("description"), f"{name}.{field_name} has no description"
