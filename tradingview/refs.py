"""Reference resolvers + the slug tables for /tradingview/*.

ONE param per input (tripadvisor QueryOrIdField convention, never a
sibling `url` / `id` pair). Every resolver takes the bare id OR any
www.tradingview.com link for the same record and raises ValueError with a
user-facing message (schema_fields.RefField turns it into a 400):

  symbol   "NASDAQ:AAPL", "AAPL" (bare ticker, resolved through symbol
           search at request time), "/symbols/NASDAQ-AAPL/",
           "/symbols/BTCUSD/?exchange=CRYPTO", "/chart/?symbol=NASDAQ:AAPL"
  idea     the 8-char idea uuid ("qNLedwY9") or the idea's chart link
           "/chart/AAPL/qNLedwY9-Apple-AAPL-.../"
  script   the 8-char script uuid or "/script/iKBJt1S8-Edo-Range-State/"
  mind     the 22-char Minds post uid or
           "/symbols/NASDAQ-AAPL/minds/?mind=YBPAw86OQ5y0P_rrBEJgYQ"
  story    the news story id ("tradingview:ab5c900008e42:0",
           "tag:reuters.com,2026:newsml_L6N46J0OT:0", "DJN_DN20261103001622:0")
           or its "/news/<id>-<slug>/" link
  user     a username or "/u/<username>/"

The scanner market slugs (MARKETS) are every /<market>/scan the scanner
answered on 2026-11-03 (76 country + asset-class markets; the rest of the
world's exchanges live inside "global" through their country market).
"""
import re
from urllib.parse import parse_qs, unquote, urlparse

SITE = "https://www.tradingview.com"

FULL_SYMBOL_RE = re.compile(r"^[A-Z0-9_]{1,24}:[A-Z0-9_.!&$^\-]{1,32}$")
TICKER_RE = re.compile(r"^[A-Z0-9_.!&$^\-]{1,32}$")
UUID_RE = re.compile(r"^[A-Za-z0-9]{8}$")
MIND_UID_RE = re.compile(r"^[A-Za-z0-9_\-]{20,24}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-.]{1,40}$")
STORY_ID_RE = re.compile(r"^[A-Za-z0-9_\-.:,]{6,120}:\d+$")

_SYMBOL_PAGE_RE = re.compile(r"/symbols/([A-Za-z0-9_.!&$^\-]+?)(?:-([A-Za-z0-9_.!&$^\-]+))?/")
_IDEA_LINK_RE = re.compile(r"/chart/[^/]+/([A-Za-z0-9]{8})-")
_SCRIPT_LINK_RE = re.compile(r"/script/([A-Za-z0-9]{8})-")
_STORY_LINK_RE = re.compile(r"/news/(.+:\d+)-")
_USER_LINK_RE = re.compile(r"/u/([A-Za-z0-9_\-.]{1,40})/?")


def _as_url(value):
    """A pasted link -> parsed URL, or None when `value` is not a link."""
    if value.startswith(("http://", "https://", "//")):
        return urlparse(value if not value.startswith("//") else "https:" + value)
    return None


def _check_host(url, what):
    host = (url.hostname or "").lower()
    if not (host == "tradingview.com" or host.endswith(".tradingview.com")):
        raise ValueError(f"Must be a tradingview.com {what} link.")


# ---- symbols --------------------------------------------------------------------

def resolve_symbol(value):
    """-> "EXCHANGE:TICKER" when the exchange is known, else the bare upper-cased
    ticker (api.py resolves it through symbol search)."""
    value = (value or "").strip()
    url = _as_url(value)
    if url is None:
        candidate = value.upper()
        if FULL_SYMBOL_RE.match(candidate) or TICKER_RE.match(candidate):
            return candidate
        raise ValueError("Must be a symbol like NASDAQ:AAPL or BTCUSD, or a "
                         "tradingview.com symbol link.")
    _check_host(url, "symbol")
    query = parse_qs(url.query)
    if query.get("symbol"):          # /chart/?symbol=NASDAQ:AAPL
        return resolve_symbol(unquote(query["symbol"][0]))
    match = _SYMBOL_PAGE_RE.search(url.path + "/")
    if not match:
        raise ValueError("Must be a tradingview.com symbol link "
                         "(https://www.tradingview.com/symbols/NASDAQ-AAPL/).")
    first, second = match.group(1).upper(), (match.group(2) or "").upper()
    exchange = (query.get("exchange") or [""])[0].upper()
    if second:                        # /symbols/NASDAQ-AAPL/
        return f"{first}:{second}"
    if exchange:                      # /symbols/BTCUSD/?exchange=CRYPTO
        return f"{exchange}:{first}"
    return first                      # /symbols/EURUSD/ (bare)


def symbol_link(full_symbol):
    exchange, _, ticker = full_symbol.partition(":")
    if not ticker:
        return f"{SITE}/symbols/{exchange}/"
    return f"{SITE}/symbols/{exchange}-{ticker}/"


def split_symbol(full_symbol):
    """"NASDAQ:AAPL" -> ("NASDAQ", "AAPL"); a bare ticker -> (None, ticker)."""
    exchange, sep, ticker = (full_symbol or "").partition(":")
    return (exchange, ticker) if sep else (None, exchange)


# ---- ideas / scripts / minds / stories / users ----------------------------------

def _resolve_uuid(value, link_re, what, example):
    value = (value or "").strip()
    url = _as_url(value)
    if url is None:
        if UUID_RE.match(value):
            return value
        raise ValueError(f"Must be an 8-character {what} id or a tradingview.com "
                         f"{what} link ({example}).")
    _check_host(url, what)
    match = link_re.search(url.path)
    if match:
        return match.group(1)
    raise ValueError(f"Must be a tradingview.com {what} link ({example}).")


def resolve_idea(value):
    return _resolve_uuid(value, _IDEA_LINK_RE, "idea",
                         "https://www.tradingview.com/chart/AAPL/qNLedwY9-.../")


def resolve_script(value):
    return _resolve_uuid(value, _SCRIPT_LINK_RE, "script",
                         "https://www.tradingview.com/script/iKBJt1S8-.../")


def resolve_mind(value):
    value = (value or "").strip()
    url = _as_url(value)
    if url is None:
        if MIND_UID_RE.match(value):
            return value
        raise ValueError("Must be a Minds post id or a tradingview.com minds link "
                         "(https://www.tradingview.com/symbols/NASDAQ-AAPL/minds/?mind=<id>).")
    _check_host(url, "minds")
    mind = (parse_qs(url.query).get("mind") or [""])[0]
    if MIND_UID_RE.match(mind):
        return mind
    raise ValueError("Must be a tradingview.com minds link with a ?mind=<id> part.")


def resolve_story(value):
    value = (value or "").strip()
    url = _as_url(value)
    if url is None:
        if STORY_ID_RE.match(value):
            return value
        raise ValueError("Must be a news story id (tradingview:ab5c900008e42:0) or a "
                         "tradingview.com news link (https://www.tradingview.com/news/<id>-<slug>/).")
    _check_host(url, "news")
    match = _STORY_LINK_RE.search(unquote(url.path))
    if match:
        return match.group(1)
    raise ValueError("Must be a tradingview.com news story link "
                     "(https://www.tradingview.com/news/<id>-<slug>/).")


def resolve_user(value):
    value = (value or "").strip()
    url = _as_url(value)
    if url is None:
        if USERNAME_RE.match(value):
            return value
        raise ValueError("Must be a TradingView username or a tradingview.com profile link "
                         "(https://www.tradingview.com/u/<username>/).")
    _check_host(url, "profile")
    match = _USER_LINK_RE.search(url.path)
    if match:
        return match.group(1)
    raise ValueError("Must be a tradingview.com profile link "
                     "(https://www.tradingview.com/u/<username>/).")


def idea_link(chart_url):
    """The idea's own chart_url is absolute in list payloads and relative in
    the detail payload."""
    if not chart_url:
        return None
    return chart_url if chart_url.startswith("http") else SITE + chart_url


def user_link(username):
    return f"{SITE}/u/{username}/" if username else None


def story_link(story_path):
    return SITE + story_path if story_path else None


def mind_link(symbol, uid):
    return f"{symbol_link(symbol)}minds/?mind={uid}" if symbol and uid else None


def logo_link(logoid, big=False):
    if not logoid:
        return None
    return f"https://s3-symbol-logo.tradingview.com/{logoid}{'--big' if big else ''}.svg"


# ---- scanner markets ---------------------------------------------------------------

COUNTRY_MARKETS = (
    "america", "argentina", "australia", "austria", "bahrain", "bangladesh", "belgium",
    "brazil", "bulgaria", "canada", "chile", "china", "colombia", "croatia", "cyprus",
    "czech", "denmark", "egypt", "estonia", "finland", "france", "germany", "greece",
    "hongkong", "hungary", "iceland", "india", "indonesia", "ireland", "israel", "italy",
    "japan", "kenya", "korea", "ksa", "kuwait", "latvia", "lithuania", "luxembourg",
    "malaysia", "mexico", "morocco", "netherlands", "newzealand", "nigeria", "norway",
    "pakistan", "peru", "philippines", "poland", "portugal", "qatar", "romania", "rsa",
    "russia", "serbia", "singapore", "slovakia", "slovenia", "spain", "srilanka",
    "sweden", "switzerland", "taiwan", "thailand", "tunisia", "turkey", "uae", "uk",
    "venezuela", "vietnam",
)
ASSET_MARKETS = ("crypto", "coin", "forex", "futures", "bond", "cfd", "economics2")
MARKETS = COUNTRY_MARKETS + ASSET_MARKETS

# Public "stock exchanges" of a country market, for the US movers presets
# (the site's own filter on /markets/stocks-usa/market-movers-*).
US_EXCHANGES = ("AMEX", "NASDAQ", "NYSE")

# ---- choice tables the schemas map to upstream tokens ---------------------------

# Chart / technicals intervals -> the scanner's "|<tf>" suffix (the daily
# fields carry no suffix) and the chart session's resolution string.
INTERVALS = {
    "1m": ("|1", "1"), "5m": ("|5", "5"), "15m": ("|15", "15"), "30m": ("|30", "30"),
    "1h": ("|60", "60"), "2h": ("|120", "120"), "4h": ("|240", "240"),
    "1d": ("", "1D"), "1w": ("|1W", "1W"), "1mo": ("|1M", "1M"),
}

# symbol-search search_type tokens (symbol_search/v3/?search_type=).
SEARCH_TYPES = {
    "stock": "stocks", "etf": "funds", "futures": "futures", "forex": "forex",
    "crypto": "crypto", "index": "index", "bond": "bond", "economy": "economic",
    "cfd": "cfd", "option": "options",
}

# news-flow market filters (filter=market:<x>).
NEWS_MARKETS = ("stock", "crypto", "forex", "futures", "index", "bond", "corp_bond",
                "etf", "economic")

# api/v1/ideas + /scripts sort tokens (the schema maps the public names).
FEED_SORTS = {"recent": "recent", "popular": "week_popular", "trending": "trending"}
# The /ideas/<slug>/ and /scripts/<slug>/ PAGES answer 404 to any other sort
# value (2026-11-03); None = the page's default (this week's popular).
PAGE_SORTS = {"ideas": {"recent": "recent"}, "scripts": {"recent": "recent"}}
IDEA_TYPES = {"trade": "trade", "education": "education", "all": "all"}
SCRIPT_TYPES = {"indicator": "indicators", "strategy": "strategies", "library": "libraries"}
SCRIPT_ACCESS = {1: "open_source", 2: "protected", 3: "invite_only"}
IDEA_DIRECTIONS = {0: "neutral", 1: "long", 2: "short"}

# economic-calendar minImportance.
IMPORTANCE = {"low": -1, "medium": 0, "high": 1}

# ---- scanner column catalogs ------------------------------------------------------

_IDENTITY = ("name", "description", "logoid", "type", "typespecs", "exchange", "currency",
             "fundamental_currency_code", "update_mode")

COLUMN_PRESETS = {
    "overview": _IDENTITY + (
        "close", "change", "change_abs", "volume", "relative_volume_10d_calc", "market_cap_basic",
        "price_earnings_ttm", "earnings_per_share_diluted_ttm", "earnings_per_share_diluted_yoy_growth_ttm",
        "dividends_yield_current", "sector", "industry", "Recommend.All"),
    "performance": _IDENTITY + (
        "close", "change", "Perf.W", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.YTD", "Perf.Y", "Perf.5Y",
        "Perf.10Y", "Perf.All", "Volatility.W", "Volatility.M", "beta_1_year", "High.1M", "Low.1M",
        "price_52_week_high", "price_52_week_low", "High.All", "Low.All"),
    "valuation": _IDENTITY + (
        "close", "market_cap_basic", "price_earnings_ttm", "price_earnings_growth_ttm",
        "price_sales_current", "price_book_fq", "price_to_cash_f_operating_activities_ttm",
        "price_free_cash_flow_ttm", "price_to_cash_ratio", "enterprise_value_current",
        "enterprise_value_to_revenue_ttm", "enterprise_value_to_ebit_ttm", "enterprise_value_ebitda_ttm"),
    "dividends": _IDENTITY + (
        "close", "dividends_yield_current", "dividends_yield", "dividend_payout_ratio_ttm",
        "dps_common_stock_prim_issue_fy", "dps_common_stock_prim_issue_yoy_growth_fy",
        "continuous_dividend_payout", "continuous_dividend_growth", "dividend_ex_date_upcoming",
        "dividend_amount_upcoming"),
    "profitability": _IDENTITY + (
        "close", "gross_margin_ttm", "operating_margin_ttm", "pre_tax_margin_ttm", "net_margin_ttm",
        "free_cash_flow_margin_ttm", "return_on_assets_fq", "return_on_equity_fq",
        "return_on_invested_capital_fq", "research_and_dev_ratio_ttm", "sell_gen_admin_exp_other_ratio_ttm"),
    "income": _IDENTITY + (
        "close", "total_revenue_ttm", "total_revenue_yoy_growth_ttm", "gross_profit_ttm", "oper_income_ttm",
        "net_income_ttm", "ebitda_ttm", "earnings_per_share_diluted_ttm",
        "earnings_per_share_diluted_yoy_growth_ttm"),
    "balance": _IDENTITY + (
        "close", "total_assets_fq", "total_current_assets_fq", "cash_n_short_term_invest_fq",
        "total_liabilities_fq", "total_debt_fq", "net_debt_fq", "total_equity_fq", "current_ratio_fq",
        "quick_ratio_fq", "debt_to_equity_fq", "cash_n_short_term_invest_to_total_debt_fq"),
    "cashflow": _IDENTITY + (
        "close", "cash_f_operating_activities_ttm", "cash_f_investing_activities_ttm",
        "cash_f_financing_activities_ttm", "free_cash_flow_ttm", "capital_expenditures_ttm"),
    "technicals": _IDENTITY + (
        "close", "change", "Recommend.All", "Recommend.MA", "Recommend.Other", "RSI", "Mom", "AO", "CCI20",
        "Stoch.K", "Stoch.D", "MACD.macd", "MACD.signal", "ADX", "ATR", "BB.upper", "BB.lower", "EMA20",
        "SMA20", "EMA50", "SMA50", "EMA200", "SMA200", "Volatility.D"),
}

COIN_COLUMNS = (
    "base_currency", "base_currency_desc", "base_currency_logoid", "type", "typespecs", "exchange",
    "crypto_total_rank", "close", "currency", "24h_close_change|5", "market_cap_calc",
    "fundamental_currency_code", "24h_vol_cmc", "24h_vol_change_cmc", "circulating_supply", "total_supply",
    "max_supply", "crypto_common_categories", "Recommend.All", "Perf.W", "Perf.1M", "Perf.YTD", "Perf.Y",
)
COIN_SORTS = {
    "rank": "crypto_total_rank", "market_cap": "market_cap_calc", "volume": "24h_vol_cmc",
    "change": "24h_close_change|5", "price": "close", "name": "base_currency",
}

ETF_COLUMNS = (
    "name", "description", "logoid", "exchange", "currency", "update_mode", "close", "change", "volume",
    "aum", "fund_flows.1M", "fund_flows.1Y", "expense_ratio", "nav_total_return.1Y", "nav_total_return.3Y",
    "nav_total_return.5Y", "dividends_yield_current", "focus.tr", "asset_class.tr", "category.tr",
    "brand.tr", "launch_date", "holdings_count", "index_tracked.tr",
)
ETF_SORTS = {
    "aum": "aum", "volume": "volume", "change": "change", "expense_ratio": "expense_ratio",
    "return_1y": "nav_total_return.1Y", "flows_1m": "fund_flows.1M", "dividend_yield": "dividends_yield_current",
    "name": "name",
}

# Ready-made stock screens: (sort field, order, extra filters).
SCREENER_PRESETS = {
    "top-market-cap": ("market_cap_basic", "desc", ()),
    "gainers": ("change", "desc", ()),
    "losers": ("change", "asc", ()),
    "most-active": ("volume", "desc", ()),
    "most-volatile": ("Volatility.D", "desc", ()),
    "unusual-volume": ("relative_volume_10d_calc", "desc", ()),
    "overbought": ("RSI", "desc", (("RSI", "greater", 70),)),
    "oversold": ("RSI", "asc", (("RSI", "less", 30),)),
    "strong-buy": ("Recommend.All", "desc", (("Recommend.All", "greater", 0.5),)),
    "strong-sell": ("Recommend.All", "asc", (("Recommend.All", "less", -0.5),)),
    "large-cap": ("market_cap_basic", "desc", (("market_cap_basic", "greater", 10_000_000_000),)),
    "small-cap": ("market_cap_basic", "desc", (("market_cap_basic", "in_range", [300_000_000, 2_000_000_000]),)),
    "penny-stocks": ("volume", "desc", (("close", "less", 5),)),
    "high-dividend": ("dividends_yield_current", "desc", ()),
    "high-beta": ("beta_1_year", "desc", ()),
    "most-expensive": ("close", "desc", ()),
    "highest-revenue": ("total_revenue_ttm", "desc", ()),
    "highest-net-income": ("net_income_ttm", "desc", ()),
    "largest-employers": ("number_of_employees", "desc", ()),
    "pre-market-gainers": ("premarket_change", "desc", ()),
    "pre-market-losers": ("premarket_change", "asc", ()),
    "pre-market-most-active": ("premarket_volume", "desc", ()),
    "after-hours-gainers": ("postmarket_change", "desc", ()),
    "after-hours-losers": ("postmarket_change", "asc", ()),
    "after-hours-most-active": ("postmarket_volume", "desc", ()),
}

FILTER_OPERATIONS = ("greater", "less", "egreater", "eless", "equal", "nequal", "in_range",
                     "not_in_range", "match", "nmatch", "has", "has_none_of")

# ---- single-symbol field sets ------------------------------------------------------

DETAIL_FIELDS = (
    "name", "description", "type", "typespecs", "currency", "fundamental_currency_code", "country", "exchange",
    "logoid", "base_currency_logoid", "update_mode", "close", "open", "high", "low", "change", "change_abs", "volume",
    "average_volume_10d_calc", "relative_volume_10d_calc", "premarket_close", "premarket_change",
    "postmarket_close", "postmarket_change", "market_cap_basic", "sector", "industry", "number_of_employees",
    "isin", "price_52_week_high", "price_52_week_low", "High.All", "Low.All", "Perf.W", "Perf.1M", "Perf.3M",
    "Perf.6M", "Perf.YTD", "Perf.Y", "Perf.5Y", "Perf.10Y", "Perf.All", "Volatility.D", "beta_1_year",
    "price_earnings_ttm", "earnings_per_share_diluted_ttm", "earnings_per_share_basic_ttm",
    "price_sales_current", "price_book_fq", "enterprise_value_current", "enterprise_value_ebitda_ttm",
    "total_revenue_ttm", "net_income_ttm", "gross_margin_ttm", "operating_margin_ttm", "net_margin_ttm",
    "return_on_equity_fq", "total_shares_outstanding", "float_shares_outstanding", "dividends_yield_current",
    "dividend_payout_ratio_ttm", "dividend_ex_date_recent", "dividend_payment_date_recent",
    "dividend_amount_recent", "dividend_ex_date_upcoming", "dividend_payment_date_upcoming",
    "dividend_amount_upcoming", "earnings_release_date", "earnings_release_next_date",
    "earnings_release_next_time", "earnings_per_share_fq", "earnings_per_share_forecast_next_fq",
    "revenue_fq", "revenue_forecast_next_fq", "eps_surprise_percent_fq", "price_target_average",
    "price_target_median", "price_target_high", "price_target_low", "recommendation_buy", "recommendation_over", "recommendation_under",
    "recommendation_hold", "recommendation_sell", "recommendation_total", "recommendation_mark",
    "Recommend.All", "RSI", "crypto_total_rank", "market_cap_calc", "circulating_supply", "total_supply",
    "max_supply", "24h_vol_cmc",
)

QUOTE_FIELDS = (
    "name", "description", "logoid", "type", "typespecs", "exchange", "currency", "update_mode", "close",
    "open", "high", "low", "change", "change_abs", "volume", "market_cap_basic", "Recommend.All", "RSI",
    "premarket_close", "premarket_change", "postmarket_close", "postmarket_change", "pricescale", "minmov",
)

# Technical-analysis fields (the daily set; the interval suffix is appended per request).
TA_RATINGS = ("Recommend.All", "Recommend.MA", "Recommend.Other")
TA_OSCILLATORS = {
    "rsi": "RSI", "rsi_previous": "RSI[1]", "stochastic_k": "Stoch.K", "stochastic_d": "Stoch.D",
    "stochastic_k_previous": "Stoch.K[1]", "stochastic_d_previous": "Stoch.D[1]", "cci": "CCI20",
    "cci_previous": "CCI20[1]", "adx": "ADX", "adx_plus_di": "ADX+DI", "adx_minus_di": "ADX-DI",
    "adx_plus_di_previous": "ADX+DI[1]", "adx_minus_di_previous": "ADX-DI[1]", "awesome_oscillator": "AO",
    "awesome_oscillator_previous": "AO[1]", "momentum": "Mom", "momentum_previous": "Mom[1]",
    "macd": "MACD.macd", "macd_signal": "MACD.signal", "stochastic_rsi_k": "Stoch.RSI.K",
    "williams_r": "W.R", "bull_bear_power": "BBPower", "ultimate_oscillator": "UO",
}
TA_MOVING_AVERAGES = {
    "ema10": "EMA10", "sma10": "SMA10", "ema20": "EMA20", "sma20": "SMA20", "ema30": "EMA30", "sma30": "SMA30",
    "ema50": "EMA50", "sma50": "SMA50", "ema100": "EMA100", "sma100": "SMA100", "ema200": "EMA200",
    "sma200": "SMA200", "ichimoku_base_line": "Ichimoku.BLine", "vwma": "VWMA", "hull_ma9": "HullMA9",
}
TA_SIGNALS = {
    "stochastic_rsi": "Rec.Stoch.RSI", "williams_r": "Rec.WR", "bull_bear_power": "Rec.BBPower",
    "ultimate_oscillator": "Rec.UO", "ichimoku": "Rec.Ichimoku", "vwma": "Rec.VWMA", "hull_ma9": "Rec.HullMA9",
}
TA_PIVOT_SYSTEMS = ("Classic", "Fibonacci", "Camarilla", "Woodie", "Demark")
TA_PIVOT_LEVELS = ("S3", "S2", "S1", "Middle", "R1", "R2", "R3")
TA_OTHER = {"close": "close", "bollinger_upper": "BB.upper", "bollinger_lower": "BB.lower", "atr": "ATR",
            "volatility_daily": "Volatility.D"}

# Financial statements: public key -> scanner stem (period suffix appended).
STATEMENTS = {
    "income": {
        "revenue": "total_revenue", "cost_of_goods": "cost_of_goods", "gross_profit": "gross_profit",
        "operating_income": "oper_income", "net_income": "net_income", "ebitda": "ebitda", "ebit": "ebit",
        "eps_diluted": "earnings_per_share_diluted", "eps_basic": "earnings_per_share_basic",
        "research_and_development": "research_and_dev", "selling_general_admin": "sell_gen_admin_exp_total",
        "pretax_income": "pretax_income", "income_tax": "income_tax",
        "diluted_shares_outstanding": "diluted_shares_outstanding",
    },
    "balance": {
        "total_assets": "total_assets", "total_current_assets": "total_current_assets",
        "cash_and_short_term_investments": "cash_n_short_term_invest", "total_liabilities": "total_liabilities",
        "total_current_liabilities": "total_current_liabilities", "total_debt": "total_debt",
        "net_debt": "net_debt", "total_equity": "total_equity",
    },
    "cashflow": {
        "operating_cash_flow": "cash_f_operating_activities", "investing_cash_flow": "cash_f_investing_activities",
        "financing_cash_flow": "cash_f_financing_activities", "free_cash_flow": "free_cash_flow",
        "capital_expenditures": "capital_expenditures", "dividends_paid": "dividends_paid",
    },
    "ratios": {
        "gross_margin": "gross_margin", "operating_margin": "operating_margin", "net_margin": "net_margin",
        "return_on_equity": "return_on_equity", "return_on_assets": "return_on_assets",
        "debt_to_equity": "debt_to_equity", "current_ratio": "current_ratio", "quick_ratio": "quick_ratio",
        "price_to_earnings": "price_earnings", "price_to_sales": "price_sales", "price_to_book": "price_book",
        "enterprise_value": "enterprise_value", "ev_to_ebitda": "enterprise_value_ebitda",
        "dividends_per_share": "dividends_per_share", "dividend_payout_ratio": "dividend_payout_ratio",
    },
}
PERIODS = {"annual": "fy", "quarterly": "fq"}

EARNINGS_COLUMNS = (
    "logoid", "name", "description", "currency", "fundamental_currency_code", "market_cap_basic",
    "earnings_release_date", "earnings_release_time", "earnings_release_next_date", "earnings_release_next_time",
    "earnings_per_share_fq", "earnings_per_share_forecast_fq", "eps_surprise_fq", "eps_surprise_percent_fq",
    "earnings_per_share_forecast_next_fq", "revenue_fq", "revenue_forecast_fq", "revenue_forecast_next_fq",
    "earnings_publication_type_fq", "earnings_publication_type_next_fq",
)
DIVIDEND_COLUMNS = (
    "logoid", "name", "description", "currency", "fundamental_currency_code", "market_cap_basic", "close",
    "dividend_ex_date_upcoming", "dividend_payment_date_upcoming", "dividend_amount_upcoming",
    "dividend_ex_date_recent", "dividend_payment_date_recent", "dividend_amount_recent",
    "dividends_yield_current", "dividend_frequency", "dividends_per_share_fq",
)

# Idea / script feed slugs the site serves at /ideas/<slug>/ and /scripts/<slug>/.
IDEA_MARKETS = ("stocks", "crypto", "forex", "futures", "indices", "bonds", "economy",
                "currencies", "commodities", "bitcoin", "editors-picks", "education")
