"""Raw TradingView JSON / HTML -> clean dicts for every /tradingview/* endpoint.
Pure functions, no I/O.

Value conventions (shared with the other scraper packages):
  * keys      snake_case; `link` not `url`; booleans as questions
  * dates     ISO; epoch seconds -> "YYYY-MM-DD" for date-only fields
              (ex-dividend / earnings dates), full UTC datetimes elsewhere
  * numbers   as numbers; the scanner's percentages are kept as the site
              shows them (change = -1.83 means -1.83 %)
  * missing   null, never "" / "N/A"; a paywalled story body is null
  * noise     dropped: logo style objects, avatar data: URIs, tracking ids,
              `is_liked` / `is_favorite` (the anonymous viewer's own state)

Fixtures captured 2026-11-03 (tradingview/fixtures/): scanner scans (US
stocks, coins, ETFs, the earnings and dividend calendars, a batch quote),
single-symbol field sets (key stats, profile, technicals, statements,
analysts; an unknown symbol's `null`), symbol search (apple / no match /
crypto), the AAPL news feed, two stories (TradingView's own, a Reuters
preview), one economic-calendar week, the AAPL ideas feed page JSON and
api/v1 page, one idea with its comments and a replies thread, the scripts
feed page + api/v1 pages, an open-source script's Pine source and the
"not allowed" refusal, the AAPL Minds feed with one post's detail and
comments, a user profile, the BTCUSD markets tab, raw chart websocket
frames (AAPL 1D, BTCUSDT 60, an unknown symbol) and three symbol pages.
The HTML fixtures keep only the blocks the parsers read (ld+json,
window.initData.symbolInfo, the ssrIdeaData init-data); the site's other
inline scripts, styles and SVG were stripped. Text search pages
(/ideas/search/<q>/, /scripts/search/<q>/) were captured the same day.
"""
import json
import re
from datetime import datetime, timezone

from tradingview.refs import (
    COIN_COLUMNS, ETF_COLUMNS, IDEA_DIRECTIONS, SCRIPT_ACCESS, SITE, STATEMENTS, TA_MOVING_AVERAGES,
    TA_OSCILLATORS, TA_OTHER, TA_PIVOT_LEVELS, TA_PIVOT_SYSTEMS, TA_RATINGS, TA_SIGNALS, idea_link, logo_link,
    mind_link, story_link, symbol_link, user_link,
)

# ---- value helpers ---------------------------------------------------------------

_DATE_FIELD_RE = re.compile(r"(_date|_date_recent|_date_upcoming|release_date|release_next_date|launch_date)$")


def epoch_date(value):
    """Epoch seconds -> 'YYYY-MM-DD' (UTC); None / non-numbers -> None."""
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def epoch_datetime(value):
    """Epoch seconds (float ok) -> ISO 8601 UTC datetime, or None."""
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def iso_datetime(value):
    """'2026-10-27T20:38:43.411516Z' / '+00:00' -> second precision ISO UTC."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def clean(value):
    """'' / 'N/A' / '-' -> None; everything else unchanged."""
    if isinstance(value, str):
        text = value.strip()
        if text in ("", "N/A", "-", "null"):
            return None
        return text
    return value


def rating_label(value):
    """TradingView's own thresholds for the Buy/Sell gauge (-1 .. 1)."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value >= 0.5:
        return "strong_buy"
    if value >= 0.1:
        return "buy"
    if value > -0.1:
        return "neutral"
    if value > -0.5:
        return "sell"
    return "strong_sell"


def field_key(field):
    """A scanner field id -> a readable snake_case key when we know it, else a
    safe generic transliteration ("Perf.YTD" -> "perf_ytd", "RSI|1W" -> "rsi_1w")."""
    if field in FIELD_RENAMES:
        return FIELD_RENAMES[field]
    key = field.replace("|", "_").replace(".", "_").replace("[", "_prev").replace("]", "")
    key = re.sub(r"[^A-Za-z0-9_]", "_", key)
    return re.sub(r"_+", "_", key).strip("_").lower()


FIELD_RENAMES = {
    "name": "ticker", "description": "name", "logoid": "logo", "close": "price", "change": "change_percent",
    "change_abs": "change", "market_cap_basic": "market_cap", "market_cap_calc": "market_cap",
    "fundamental_currency_code": "fundamental_currency", "price_earnings_ttm": "pe_ratio_ttm",
    "earnings_per_share_diluted_ttm": "eps_diluted_ttm", "earnings_per_share_basic_ttm": "eps_basic_ttm",
    "earnings_per_share_diluted_yoy_growth_ttm": "eps_growth_yoy_ttm", "dividends_yield_current": "dividend_yield",
    "dividends_yield": "dividend_yield_trailing", "relative_volume_10d_calc": "relative_volume_10d",
    "average_volume_10d_calc": "average_volume_10d", "Recommend.All": "technical_rating",
    "Recommend.MA": "moving_averages_rating", "Recommend.Other": "oscillators_rating", "RSI": "rsi",
    "update_mode": "data_mode", "price_earnings_growth_ttm": "peg_ratio_ttm", "price_sales_current": "ps_ratio",
    "price_book_fq": "pb_ratio", "price_free_cash_flow_ttm": "price_to_free_cash_flow_ttm",
    "price_to_cash_f_operating_activities_ttm": "price_to_operating_cash_flow_ttm",
    "enterprise_value_current": "enterprise_value", "enterprise_value_ebitda_ttm": "ev_to_ebitda_ttm",
    "enterprise_value_to_revenue_ttm": "ev_to_revenue_ttm", "enterprise_value_to_ebit_ttm": "ev_to_ebit_ttm",
    "total_revenue_ttm": "revenue_ttm", "total_revenue_yoy_growth_ttm": "revenue_growth_yoy_ttm",
    "oper_income_ttm": "operating_income_ttm", "cash_n_short_term_invest_fq": "cash_and_short_term_investments",
    "cash_n_short_term_invest_to_total_debt_fq": "cash_to_total_debt", "total_assets_fq": "total_assets",
    "total_current_assets_fq": "total_current_assets", "total_liabilities_fq": "total_liabilities",
    "total_debt_fq": "total_debt", "net_debt_fq": "net_debt", "total_equity_fq": "total_equity",
    "current_ratio_fq": "current_ratio", "quick_ratio_fq": "quick_ratio", "debt_to_equity_fq": "debt_to_equity",
    "return_on_assets_fq": "return_on_assets", "return_on_equity_fq": "return_on_equity",
    "return_on_invested_capital_fq": "return_on_invested_capital",
    "cash_f_operating_activities_ttm": "operating_cash_flow_ttm",
    "cash_f_investing_activities_ttm": "investing_cash_flow_ttm",
    "cash_f_financing_activities_ttm": "financing_cash_flow_ttm",
    "dps_common_stock_prim_issue_fy": "dividends_per_share_fy",
    "dps_common_stock_prim_issue_yoy_growth_fy": "dividends_per_share_growth_yoy_fy",
    "continuous_dividend_payout": "dividend_payout_streak_years", "continuous_dividend_growth": "dividend_growth_streak_years",
    "sell_gen_admin_exp_other_ratio_ttm": "sga_ratio_ttm", "research_and_dev_ratio_ttm": "rd_ratio_ttm",
    "Perf.W": "performance_week", "Perf.1M": "performance_1m", "Perf.3M": "performance_3m",
    "Perf.6M": "performance_6m", "Perf.YTD": "performance_ytd", "Perf.Y": "performance_1y",
    "Perf.5Y": "performance_5y", "Perf.10Y": "performance_10y", "Perf.All": "performance_all_time",
    "Volatility.D": "volatility_daily", "Volatility.W": "volatility_week", "Volatility.M": "volatility_month",
    "High.1M": "high_1m", "Low.1M": "low_1m", "High.All": "all_time_high", "Low.All": "all_time_low",
    "price_52_week_high": "high_52_week", "price_52_week_low": "low_52_week", "beta_1_year": "beta",
    "MACD.macd": "macd", "MACD.signal": "macd_signal", "Stoch.K": "stochastic_k", "Stoch.D": "stochastic_d",
    "CCI20": "cci", "ADX": "adx", "ATR": "atr", "AO": "awesome_oscillator", "Mom": "momentum",
    "BB.upper": "bollinger_upper", "BB.lower": "bollinger_lower", "EMA20": "ema20", "SMA20": "sma20",
    "EMA50": "ema50", "SMA50": "sma50", "EMA200": "ema200", "SMA200": "sma200",
    "base_currency": "ticker", "base_currency_desc": "name", "base_currency_logoid": "logo",
    "crypto_total_rank": "rank", "24h_close_change|5": "change_24h_percent", "24h_vol_cmc": "volume_24h",
    "24h_vol_change_cmc": "volume_24h_change_percent", "crypto_common_categories": "categories",
    "fund_flows.1M": "fund_flows_1m", "fund_flows.1Y": "fund_flows_1y", "nav_total_return.1Y": "return_1y",
    "nav_total_return.3Y": "return_3y", "nav_total_return.5Y": "return_5y", "focus.tr": "focus",
    "asset_class.tr": "asset_class", "category.tr": "category", "brand.tr": "brand", "index_tracked.tr": "index_tracked",
    "number_of_employees": "employees", "premarket_close": "premarket_price", "premarket_change": "premarket_change_percent",
    "postmarket_close": "postmarket_price", "postmarket_change": "postmarket_change_percent",
}


def _value(field, value):
    """Field-aware value cleaning: epoch dates for *_date fields, logo ids to links."""
    if field in ("logoid", "base_currency_logoid"):
        return logo_link(value)
    if _DATE_FIELD_RE.search(field) and isinstance(value, (int, float)):
        return epoch_date(value)
    return clean(value)


# ---- scanner -------------------------------------------------------------------

def parse_scan(payload, columns, rename=True):
    """{totalCount, data: [{s, d}]} -> (total, rows). Each row carries the full
    symbol, its ticker and exchange, the symbol page link, then one key per
    requested column (renamed through FIELD_RENAMES unless rename=False, for a
    caller's own column list)."""
    total = (payload or {}).get("totalCount")
    rows = []
    for entry in (payload or {}).get("data") or []:
        full = (entry or {}).get("s") or ""
        values = (entry or {}).get("d") or []
        exchange, _, ticker = full.partition(":")
        row = {"symbol": full, "ticker": ticker or full, "exchange": exchange or None, "link": symbol_link(full)}
        for field, value in zip(columns, values):
            key = field_key(field) if rename else field
            if key in ("symbol", "link"):
                key = f"{key}_field"
            _merge(row, key, _value(field, value))
        rows.append(row)
    return total, rows


def parse_symbol_fields(payload, fields):
    """GET /symbol -> {renamed field: cleaned value} for `fields` (a missing
    field is null)."""
    payload = payload or {}
    out = {}
    for f in fields:
        _merge(out, field_key(f), _value(f, payload.get(f)))
    return out


def _merge(row, key, value):
    """Several scanner fields share one readable key (market_cap_basic /
    market_cap_calc, logoid / base_currency_logoid): a later null never
    overwrites an earlier value."""
    if value is not None or key not in row:
        row[key] = value


# ---- symbol search -------------------------------------------------------------

_EM_RE = re.compile(r"</?em>")


def parse_search(payload):
    """symbol_search/v3 -> (results, remaining)."""
    results = []
    for item in (payload or {}).get("symbols") or []:
        ticker = _EM_RE.sub("", item.get("symbol") or "")
        # `exchange` is a display name ("Binance"); source_id is the code the scanner wants
        exchange = item.get("source_id") or item.get("exchange") or ""
        full = f"{exchange}:{ticker}" if exchange and ticker else ticker
        source = item.get("source2") or {}
        logo = item.get("logo") or {}
        results.append({
            "symbol": full,
            "ticker": ticker,
            "exchange": exchange or None,
            "name": _EM_RE.sub("", item.get("description") or "") or None,
            "link": symbol_link(full),
            "type": item.get("type"),
            "typespecs": item.get("typespecs") or [],
            "exchange_name": source.get("name") or item.get("exchange"),
            "country": item.get("country"),
            "currency": item.get("currency_code"),
            "isin": item.get("isin"),
            "cusip": item.get("cusip"),
            "cik": item.get("cik_code"),
            "is_primary_listing": item.get("is_primary_listing"),
            "logo": logo_link(logo.get("logoid") or item.get("logoid")),
            "logo_secondary": logo_link(logo.get("logoid2")),
            "provider": item.get("provider_id"),
        })
    return results, int((payload or {}).get("symbols_remaining") or 0)


# ---- technicals ----------------------------------------------------------------

def technical_fields(suffix):
    """Every scanner field the technicals endpoint asks for at one interval."""
    names = list(TA_RATINGS) + list(TA_OSCILLATORS.values()) + list(TA_MOVING_AVERAGES.values())
    names += list(TA_SIGNALS.values()) + list(TA_OTHER.values())
    names += [f"Pivot.M.{system}.{level}" for system in TA_PIVOT_SYSTEMS for level in TA_PIVOT_LEVELS]
    return [n + suffix for n in names]


def parse_technicals(payload, suffix):
    payload = payload or {}

    def get(name):
        return clean(payload.get(name + suffix))

    def gauge(name):
        value = get(name)
        return {"rating": value, "label": rating_label(value)}

    pivots = {}
    for system in TA_PIVOT_SYSTEMS:
        pivots[system.lower()] = {level.lower(): get(f"Pivot.M.{system}.{level}") for level in TA_PIVOT_LEVELS}
    return {
        "price": get("close"),
        "summary": gauge("Recommend.All"),
        "moving_averages": gauge("Recommend.MA"),
        "oscillators": gauge("Recommend.Other"),
        "oscillator_values": {key: get(field) for key, field in TA_OSCILLATORS.items()},
        "moving_average_values": {key: get(field) for key, field in TA_MOVING_AVERAGES.items()},
        "indicator_signals": {key: rating_label(get(field)) for key, field in TA_SIGNALS.items()},
        "pivots": pivots,
        "bollinger_bands": {"upper": get("BB.upper"), "lower": get("BB.lower")},
        "atr": get("ATR"),
        "volatility_daily": get("Volatility.D"),
    }


# ---- financial statements ---------------------------------------------------------

def statement_fields(statement, period):
    """Scanner fields for one statement at one period: the history arrays
    plus the period labels and, for annual, the latest FY + TTM values."""
    stems = STATEMENTS[statement]
    fields = [f"{stem}_{period}_h" for stem in stems.values()]
    fields += [f"fiscal_period_{period}_h", f"fiscal_period_end_{period}_h"]
    fields += [f"{stem}_{period}" for stem in stems.values()]
    fields += [f"{stem}_ttm" for stem in stems.values()]
    fields += ["currency", "fundamental_currency_code"]
    return fields


def parse_statement(payload, statement, period):
    payload = payload or {}
    stems = STATEMENTS[statement]
    periods = payload.get(f"fiscal_period_{period}_h")
    period_ends = payload.get(f"fiscal_period_end_{period}_h")
    if isinstance(period_ends, list):
        period_ends = [epoch_date(v) for v in period_ends]
    rows = {}
    for key, stem in stems.items():
        history = payload.get(f"{stem}_{period}_h")
        rows[key] = history if isinstance(history, list) else None
    latest = {key: clean(payload.get(f"{stem}_{period}")) for key, stem in stems.items()}
    ttm = {key: clean(payload.get(f"{stem}_ttm")) for key, stem in stems.items()}
    return {
        "currency": payload.get("fundamental_currency_code") or payload.get("currency"),
        "periods": periods if isinstance(periods, list) else None,
        "period_ends": period_ends if isinstance(period_ends, list) else None,
        "history": rows,
        "latest": latest,
        "trailing_twelve_months": ttm if any(v is not None for v in ttm.values()) else None,
    }


# ---- symbol page (HTML) ---------------------------------------------------------

_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_SYMBOL_INFO_RE = re.compile(r"window\.initData\.symbolInfo\s*=\s*(\{.*?\});\s*(?:</script>|\n)", re.S)
_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)


def _unescape(text):
    import html
    return html.unescape(text or "")


def parse_symbol_page(html_text):
    """The server-rendered /symbols/<X>/ page -> {description, category,
    faq, symbol_info}. The business description lives only in the page's
    ld+json FinancialProduct block (the scanner's business_description is
    null for anonymous clients)."""
    out = {"description": None, "category": None, "faq": [], "symbol_info": None, "title": None}
    title = _TITLE_RE.search(html_text or "")
    out["title"] = _unescape(title.group(1)).strip() if title else None
    for match in _LD_RE.finditer(html_text or ""):
        try:
            block = json.loads(match.group(1))
        except ValueError:
            continue
        kind = block.get("@type")
        if kind == "FinancialProduct":
            out["description"] = clean(block.get("description"))
            out["category"] = clean(block.get("category"))
        elif kind == "FAQPage":
            for entry in block.get("mainEntity") or []:
                answer = (entry.get("acceptedAnswer") or {}).get("text") or ""
                out["faq"].append({
                    "question": _unescape(entry.get("name")),
                    "answer": _unescape(re.sub(r"<[^>]+>", "", answer)).strip() or None,
                })
    info = _SYMBOL_INFO_RE.search(html_text or "")
    if info:
        try:
            out["symbol_info"] = json.loads(info.group(1))
        except ValueError:
            out["symbol_info"] = None
    return out


# ---- symbol markets (listings) -----------------------------------------------------

_MARKET_COLUMN_KEYS = {
    "TickerUniversal": "listing", "Exchange": "exchange_name", "Price": "price", "Change": "change_percent",
    "Volume24h": "volume_24h", "Volume24hChange": "volume_24h_change_percent", "High": "high", "Low": "low",
    "Volume": "volume", "TechnicalRating": "technical_rating",
}


def parse_symbol_markets(payload):
    """The /symbols/<X>/markets/ page JSON (column-oriented) -> one row per
    listing."""
    screener = (((payload or {}).get("data") or {}).get("screener") or {}).get("data") or {}
    symbols = screener.get("symbols") or []
    columns = {}
    for column in screener.get("data") or []:
        key = _MARKET_COLUMN_KEYS.get(column.get("id"), field_key(column.get("id") or ""))
        columns[key] = column.get("rawValues") or []
    rows = []
    # the page carries every listing's symbol but only its first page of
    # column values (100 rows)
    width = max((len(v) for v in columns.values()), default=len(symbols))
    for index, full in enumerate(symbols[:width]):
        exchange, _, ticker = full.partition(":")
        row = {"symbol": full, "ticker": ticker, "exchange": exchange, "link": symbol_link(full)}
        for key, values in columns.items():
            value = values[index] if index < len(values) else None
            if key == "listing" and isinstance(value, dict):
                row["name"] = value.get("description")
                row["type"] = value.get("type")
                row["typespecs"] = value.get("typespecs") or []
                row["logo"] = logo_link((value.get("logo") or {}).get("logoid"))
            elif key == "technical_rating":
                row[key] = clean(value)
                row["technical_rating_label"] = rating_label(value)
            else:
                row[key] = clean(value)
        rows.append(row)
    return screener.get("totalCount"), rows


# ---- news ----------------------------------------------------------------------

def _related_symbols(items):
    out = []
    for entry in items or []:
        if not isinstance(entry, dict):
            continue
        symbol = entry.get("symbol")
        if symbol:
            out.append({"symbol": symbol, "link": symbol_link(symbol),
                        "logo": logo_link(entry.get("logoid") or (entry.get("logo") or {}).get("logoid"))})
    return out


def _provider(value):
    if not isinstance(value, dict):
        return {"id": value, "name": None, "link": None} if value else None
    return {"id": value.get("id"), "name": value.get("name"), "link": value.get("url")}


def parse_news_item(item):
    item = item or {}
    path = item.get("storyPath") or item.get("story_path")
    provider = item.get("provider")
    if not isinstance(provider, dict):      # the story payload carries the id as a string + `source`
        provider = {"id": provider, "name": item.get("source")}
    return {
        "id": item.get("id"),
        "title": clean(item.get("title")),
        "link": story_link(path),
        "source_link": clean(item.get("link")),
        "published": epoch_datetime(item.get("published")),
        "provider": _provider(provider),
        "urgency": item.get("urgency"),
        "is_flash": item.get("urgency") == 1,
        "is_paywalled": bool(item.get("paywall")),
        "permission": item.get("permission"),
        "related_symbols": _related_symbols(item.get("relatedSymbols") or item.get("related_symbols")),
    }


def ast_text(node):
    """Render TradingView's text AST (stories, ideas, minds) to plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(ast_text(child) for child in node)
    if not isinstance(node, dict):
        return str(node)
    kind = node.get("type")
    params = node.get("params") or {}
    children = node.get("children")
    if kind == "symbol":
        return params.get("text") or params.get("symbol") or ""
    if kind == "url":
        return params.get("linkText") or params.get("url") or ast_text(children)
    if kind in ("image", "story-refs", "video", "br"):
        return "\n" if kind == "br" else ""
    inner = ast_text(children)
    if kind in ("p", "quote", "h1", "h2", "h3", "h4", "pre", "table-row"):
        return inner.rstrip("\n") + "\n\n"
    if kind in ("*", "li", "list-item"):
        return "- " + inner.rstrip("\n") + "\n"
    if kind == "list":
        return inner + "\n"
    return inner


def parse_story(payload):
    payload = payload or {}
    ast = payload.get("astDescription") or payload.get("ast_description")
    text = re.sub(r"\n{3,}", "\n\n", ast_text(ast)).strip() if ast else None
    paywalled = bool(payload.get("paywall")) or payload.get("permission") == "headline"
    record = parse_news_item(payload)
    record.update({
        "short_description": clean(payload.get("shortDescription") or payload.get("short_description")),
        "text": text or None,
        "is_paywalled": paywalled,
        "is_preview": paywalled and bool(text),
        "language": payload.get("language"),
        "read_time_seconds": payload.get("read_time"),
        "copyright": clean(payload.get("copyright")),
        "tags": [t.get("title") or t.get("tag") if isinstance(t, dict) else t for t in payload.get("tags") or []],
    })
    return record


# ---- economic calendar ----------------------------------------------------------

_IMPORTANCE_LABELS = {-1: "low", 0: "medium", 1: "high"}


def parse_economic_event(event):
    event = event or {}
    return {
        "id": event.get("id"),
        "title": clean(event.get("title")),
        "indicator": clean(event.get("indicator")),
        "country": event.get("country"),
        "currency": event.get("currency"),
        "date": iso_datetime(event.get("date")),
        "period": clean(event.get("period")),
        "reference_date": iso_datetime(event.get("referenceDate")),
        "importance": _IMPORTANCE_LABELS.get(event.get("importance")),
        "actual": event.get("actual"),
        "forecast": event.get("forecast"),
        "previous": event.get("previous"),
        "actual_raw": event.get("actualRaw"),
        "forecast_raw": event.get("forecastRaw"),
        "previous_raw": event.get("previousRaw"),
        "unit": clean(event.get("unit")),
        "scale": clean(event.get("scale")),
        "category": event.get("category"),
        "source": clean(event.get("source")),
        "source_link": clean(event.get("source_url")),
        "description": clean(event.get("comment")),
    }


# ---- ideas / scripts -------------------------------------------------------------

def _user(user):
    """The compact author block carried by list items, details and comments."""
    if not isinstance(user, dict):
        return None
    avatars = user.get("avatars") or {}
    picture = user.get("picture_url") or avatars.get("big") or avatars.get("mid") or avatars.get("small")
    if isinstance(picture, str) and picture.startswith("data:"):
        picture = None
    badges = [b.get("verbose_name") or b.get("name") for b in user.get("badges") or [] if isinstance(b, dict)]
    out = {
        "id": user.get("id"),
        "username": user.get("username"),
        "link": user_link(user.get("username")),
        "picture": picture,
        "badges": badges,
        "plan": clean(user.get("pro_plan")),
        "is_pro": bool(user.get("is_pro")) if "is_pro" in user else None,
        "is_broker": bool(user.get("is_broker")),
        "is_moderator": user.get("is_moderator"),
    }
    socials = {key: clean(user.get(key)) for key in (
        "website", "twitter_username", "instagram_username", "facebook_username", "youtube_channel_name", "youtube_channel")}
    if any(socials.values()):
        out["socials"] = {
            "website": socials["website"],
            "twitter": socials["twitter_username"],
            "instagram": socials["instagram_username"],
            "facebook": socials["facebook_username"],
            "youtube": socials["youtube_channel"] or socials["youtube_channel_name"],
        }
    return out


def _symbol_block(symbol):
    if not isinstance(symbol, dict):
        return None
    full = symbol.get("name") or symbol.get("full_name") or symbol.get("pro_symbol")
    return {
        "symbol": full,
        "ticker": symbol.get("short_name"),
        "exchange": symbol.get("exchange"),
        "name": symbol.get("instrument_name") or symbol.get("description") or symbol.get("short_description"),
        "type": symbol.get("type"),
        "link": symbol_link(full) if full else None,
        "logo": logo_link(symbol.get("logo_id") or (symbol.get("logo") or {}).get("logoid")),
    }


def _tags(tags):
    out = []
    for tag in tags or []:
        if isinstance(tag, dict):
            out.append({"tag": tag.get("tag"), "title": tag.get("title") or tag.get("tag"),
                        "ideas_link": SITE + tag["idea_full_url"] if tag.get("idea_full_url") else None,
                        "scripts_link": SITE + tag["script_full_url"] if tag.get("script_full_url") else None})
        elif tag:
            out.append({"tag": tag, "title": tag, "ideas_link": None, "scripts_link": None})
    return out


def parse_idea_item(item):
    """One idea (or script) from a feed page / api/v1 list."""
    item = item or {}
    symbol = item.get("symbol") or {}
    image = item.get("image") or {}
    record = {
        "id": item.get("image_url"),
        "numeric_id": item.get("id"),
        "title": clean(item.get("name")),
        "description": clean(item.get("description")),
        "link": idea_link(item.get("chart_url")),
        "image": image.get("big") or image.get("middle"),
        "published": iso_datetime(item.get("created_at")),
        "updated": iso_datetime(item.get("updated_at")),
        "symbol": _symbol_block(symbol),
        "interval": clean(symbol.get("interval")),
        "direction": IDEA_DIRECTIONS.get(symbol.get("direction")),
        "likes": item.get("likes_count"),
        "comments_count": item.get("comments_count"),
        "views": item.get("views_count") or None,
        "is_video": bool(item.get("is_video")),
        "video_duration_seconds": _int(item.get("video_duration")) or None,
        "is_education": bool(item.get("is_education")),
        "is_editors_pick": bool(item.get("is_picked")),
        "is_hot": bool(item.get("is_hot")),
        "is_broker_idea": bool(item.get("is_platinum_broker_idea")),
        "author": _user(item.get("user")),
    }
    if item.get("is_script"):
        record["script"] = {
            "type": item.get("script_type"),
            "access": SCRIPT_ACCESS.get(item.get("script_access"), item.get("script_access")),
            "pine_id": item.get("script_id_part"),
            "version": clean(item.get("version")),
        }
    return record


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_feed_page(payload):
    """An /ideas/... or /scripts/... page JSON -> (items, total, has_next)."""
    data = (((payload or {}).get("data") or {}).get("ideas") or {}).get("data") or {}
    items = [parse_idea_item(i) for i in data.get("items") or []]
    return items, data.get("total"), bool(data.get("next"))


def parse_api_list(payload):
    """An api/v1/ideas/ or /scripts/ page -> (items, count, page_size, page_count)."""
    payload = payload or {}
    items = [parse_idea_item(i) for i in payload.get("results") or []]
    return items, payload.get("count"), payload.get("page_size"), payload.get("page_count")


def _idea_image(detail):
    image = detail.get("image") or {}
    previews = detail.get("preview_image_urls") or {}
    return image.get("big") or previews.get("crop") or previews.get("original") or image.get("middle") or detail.get("webp_url")


def parse_idea_detail(detail):
    """api/v1/ideas/<uuid>/ (and a script page's ssrIdeaData, which has the
    same shape plus `script`) -> the full record."""
    detail = detail or {}
    symbol = detail.get("symbol") or {}
    flags = detail.get("flags") or {}
    user = dict(detail.get("user") or {})
    socials = detail.get("user_signature_socials") or {}
    for key in ("website", "twitter_username", "instagram_username", "facebook_username", "youtube_channel"):
        user.setdefault(key, socials.get(key))
    ast = detail.get("description_ast")
    full = symbol.get("pro_symbol") or symbol.get("name")
    record = {
        "id": detail.get("uuid"),
        "numeric_id": detail.get("id"),
        "title": clean(detail.get("name")),
        "description": clean(detail.get("description")),
        "text": re.sub(r"\n{3,}", "\n\n", ast_text(ast)).strip() or None if ast else None,
        "link": idea_link(detail.get("chart_url")),
        "image": _idea_image(detail),
        "published": iso_datetime(detail.get("created_at")),
        "updated": iso_datetime(detail.get("updated_at")),
        "symbol": {
            "symbol": full,
            "ticker": symbol.get("short_name"),
            "exchange": symbol.get("exchange"),
            "name": symbol.get("instrument_name") or symbol.get("description"),
            "type": symbol.get("type"),
            "link": symbol_link(full) if full else None,
            "logo": logo_link(symbol.get("logo_id") or (symbol.get("logo") or {}).get("logoid")),
        } if symbol else None,
        "interval": clean(detail.get("interval")),
        "direction": IDEA_DIRECTIONS.get(detail.get("direction")),
        "likes": detail.get("like_score") if detail.get("like_score") is not None else detail.get("likes_count"),
        "comments_count": detail.get("comments_count"),
        "views": detail.get("views"),
        "is_education": bool(detail.get("is_education") if "is_education" in detail else flags.get("is_education")),
        "is_editors_pick": bool(flags.get("is_picked")),
        "is_public": bool(detail.get("is_public") if "is_public" in detail else flags.get("is_public")),
        "language": detail.get("language") or (detail.get("misc") or {}).get("language"),
        "tags": _tags(detail.get("tags")),
        "updates": [{"text": ast_text(u.get("text_ast") or u.get("text")) or None,
                     "published": iso_datetime(u.get("created_at") or u.get("created"))}
                    for u in detail.get("updates") or [] if isinstance(u, dict)],
        "related_ideas": [{
            "id": r.get("uuid"), "title": clean(r.get("name")), "link": idea_link(r.get("chart_url")),
            "symbol": (r.get("symbol") or {}).get("pro_symbol"), "interval": r.get("interval"),
            "direction": IDEA_DIRECTIONS.get(r.get("direction")), "published": iso_datetime(r.get("created_at")),
        } for r in detail.get("related") or [] if isinstance(r, dict)],
        "author": _user(user),
        "video": _video(detail.get("video")),
    }
    script = detail.get("script")
    if isinstance(script, dict) and script:
        record["script"] = {
            "type": {"study": "indicator"}.get(script.get("script_type"), script.get("script_type")),
            "access": SCRIPT_ACCESS.get(script.get("access"), script.get("access")),
            "pine_id": script.get("script_id_part"),
            "version": script.get("version_maj"),
            "library_id": clean(script.get("lib_id")),
            "terms": clean(detail.get("script_terms")),
        }
    return record


def _video(video):
    if not isinstance(video, dict) or not any(video.values()):
        return None
    return {"duration_seconds": _int(video.get("video_duration")),
            "file": clean(video.get("video_filename"))}


def parse_comment(comment):
    comment = comment or {}
    return {
        "id": comment.get("id"),
        "parent_id": comment.get("parent_id"),
        "text": clean(comment.get("comment")) or ast_text(comment.get("comment_ast")).strip() or None,
        "published": iso_datetime(comment.get("created_at")),
        "likes": comment.get("likes_count"),
        "replies_count": comment.get("replies_count"),
        "platform": clean(comment.get("platform")),
        "is_hidden": bool(comment.get("is_hidden")),
        "author": _user(comment.get("user")),
        "replies": [],
    }


def parse_comments(payload):
    """A comments / replies page -> (comments, has_next)."""
    payload = payload or {}
    return [parse_comment(c) for c in payload.get("results") or []], bool(payload.get("next"))


_SSR_IDEA_RE = re.compile(r'<script type="application/prs\.init-data\+json">\s*(\{"[A-Za-z0-9]+":\{"ssrIdeaData".*?\})\s*</script>', re.S)


def parse_script_page(html_text):
    """A /script/<uuid>-<slug>/ page -> the ssrIdeaData block parsed like an
    idea, or None when the page carries none (an error shell)."""
    match = _SSR_IDEA_RE.search(html_text or "")
    if not match:
        return None
    try:
        block = json.loads(match.group(1))
    except ValueError:
        return None
    for value in block.values():
        if isinstance(value, dict) and isinstance(value.get("ssrIdeaData"), dict):
            return parse_idea_detail(value["ssrIdeaData"])
    return None


def parse_pine(payload):
    """pine-facade get -> {source, ...} or None when the author hides the source."""
    if not isinstance(payload, dict) or payload.get("success") is False or not payload.get("source"):
        return None
    extra = payload.get("extra") or {}
    return {
        "name": clean(payload.get("scriptName")),
        "access": clean(payload.get("scriptAccess")),
        "version": clean(payload.get("version")),
        "kind": clean(extra.get("kind")),
        "is_overlay": extra.get("is_price_study"),
        "created": iso_datetime(payload.get("created")),
        "updated": iso_datetime(payload.get("updated")),
        "source": payload.get("source"),
    }


# ---- minds ---------------------------------------------------------------------

def _mind_author(author):
    if not isinstance(author, dict):
        return None
    avatars = author.get("avatars") or {}
    picture = avatars.get("big") or avatars.get("mid")
    if isinstance(picture, str) and picture.startswith("data:"):
        picture = None
    return {
        "username": author.get("username"),
        "link": user_link(author.get("username")),
        "picture": picture,
        "badges": [b.get("verbose_name") or b.get("name") for b in author.get("badges") or [] if isinstance(b, dict)],
        "is_broker": bool(author.get("is_broker")),
    }


def parse_mind(post, symbols_info=None):
    post = post or {}
    symbols = []
    for full in (post.get("symbols") or {}).values():
        info = (symbols_info or {}).get(full) or {}
        symbols.append({"symbol": full, "link": symbol_link(full), "name": info.get("instrument_name"),
                        "ticker": info.get("short_name"), "logo": logo_link(info.get("logo_id"))})
    primary = symbols[0]["symbol"] if symbols else None
    return {
        "id": post.get("uid"),
        "link": post.get("url") or mind_link(primary, post.get("uid")),
        "text": clean(post.get("text")) or ast_text(post.get("text_ast")).strip() or None,
        "published": iso_datetime(post.get("created")),
        "updated": iso_datetime(post.get("modified")),
        "likes": post.get("total_likes"),
        "comments_count": post.get("total_comments"),
        "symbols": symbols,
        "access": post.get("access"),
        "is_hidden": bool(post.get("hidden")),
        "author": _mind_author(post.get("author")),
    }


def parse_minds(payload):
    """api/v1/minds/ -> (posts, next_cursor)."""
    payload = payload or {}
    meta = payload.get("meta") or {}
    posts = [parse_mind(p, meta.get("symbols_info")) for p in payload.get("results") or []]
    cursor = None
    next_link = payload.get("next") or ""
    match = re.search(r"[?&]c=([^&]+)", next_link)
    if match:
        cursor = match.group(1)
    return posts, cursor


def parse_mind_comment(comment):
    comment = comment or {}
    return {
        "id": comment.get("uid"),
        "text": clean(comment.get("text")) or ast_text(comment.get("text_ast")).strip() or None,
        "published": iso_datetime(comment.get("created")),
        "updated": iso_datetime(comment.get("modified")),
        "link": comment.get("url"),
        "is_hidden": bool(comment.get("hidden")),
        "author": _mind_author(comment.get("author")),
    }


# ---- users ---------------------------------------------------------------------

def parse_user_profile(payload):
    payload = payload or {}
    ssr = payload.get("ssrData") or {}
    stats = ssr.get("statistics") or {}
    socials = ssr.get("social_links") or {}
    username = ssr.get("username")
    return {
        "id": payload.get("userId"),
        "username": username,
        "link": user_link(username),
        "picture": ssr.get("picture_url_orig") or ssr.get("picture_url"),
        "bio": clean(ssr.get("bio")),
        "badges": [b.get("verbose_name") or b.get("name") for b in ssr.get("badges") or [] if isinstance(b, dict)],
        "joined": epoch_datetime(ssr.get("date_joined")),
        "last_seen": epoch_datetime(ssr.get("last_login")),
        "is_online": bool(ssr.get("is_online")),
        "is_banned": bool(payload.get("isBanned")),
        "is_inactive": bool(ssr.get("is_inactive")),
        "stats": {
            "followers": stats.get("followers"),
            "following": stats.get("following"),
            "ideas": stats.get("charts_total"),
            "scripts": stats.get("scripts_total"),
        },
        "socials": {
            "website": clean(socials.get("website")),
            "twitter": clean(socials.get("twitter_username")),
            "instagram": clean(socials.get("instagram_username")),
            "facebook": clean(socials.get("facebook_username")),
            "youtube": clean(socials.get("youtube_channel")) or clean(socials.get("youtube_channel_name")),
        },
    }


# ---- chart websocket frames ----------------------------------------------------------

_FRAME_RE = re.compile(r"~m~(\d+)~m~")


def _ws_messages(frames):
    """Split the "~m~<len>~m~<json>" frames into parsed messages."""
    for frame in frames or []:
        parts = _FRAME_RE.split(frame)
        for chunk in parts:
            chunk = chunk.strip()
            if not chunk or chunk.isdigit() or chunk.startswith("~h~"):
                continue
            try:
                yield json.loads(chunk)
            except ValueError:
                continue


def parse_ws_frames(frames):
    """-> {"error": str} for an unknown symbol, else {"bars", "symbol_info"}."""
    bars, info, error = [], None, None
    for message in _ws_messages(frames):
        kind = message.get("m")
        params = message.get("p") or []
        if kind == "symbol_error":
            error = params[2] if len(params) > 2 else "invalid symbol"
        elif kind in ("critical_error", "protocol_error"):
            error = error or (params[1] if len(params) > 1 else kind)
        elif kind == "symbol_resolved" and len(params) > 2 and isinstance(params[2], dict):
            raw = params[2]
            info = {
                "symbol": raw.get("pro_name") or raw.get("full_name"),
                "resolved_symbol": raw.get("full_name"),
                "name": raw.get("description"),
                "exchange": raw.get("exchange"),
                "listed_exchange": raw.get("listed_exchange"),
                "type": raw.get("type"),
                "currency": raw.get("currency_code"),
                "timezone": raw.get("timezone"),
                "session": raw.get("session"),
                "price_scale": raw.get("pricescale"),
                "min_movement": raw.get("minmov"),
                "data_mode": raw.get("update_mode") or raw.get("delay"),
            }
        elif kind == "timescale_update" and len(params) > 1 and isinstance(params[1], dict):
            for series in params[1].values():
                if not isinstance(series, dict):
                    continue
                for bar in series.get("s") or []:
                    values = (bar or {}).get("v") or []
                    if len(values) < 5:
                        continue
                    bars.append({
                        "time": epoch_datetime(values[0]),
                        "timestamp": int(values[0]),
                        "open": values[1], "high": values[2], "low": values[3], "close": values[4],
                        "volume": values[5] if len(values) > 5 else None,
                    })
    if error and not bars:
        return {"error": error, "bars": [], "symbol_info": info}
    bars.sort(key=lambda b: b["timestamp"])
    return {"error": None, "bars": bars, "symbol_info": info}
