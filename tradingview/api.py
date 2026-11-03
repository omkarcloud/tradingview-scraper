"""The /tradingview/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs). Every endpoint caches inside through
cache.cached_call keyed on its validated params (tofler-style); the two
details-type endpoints that read the same upstream record share ONE cached
fetch (the symbol record behind symbols/details, the script page behind
scripts/details).

A bare ticker ("AAPL", "BTCUSD") is resolved to the site's EXCHANGE:TICKER
through symbol search once and cached for a week (_full_symbol).
"""
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from cache import cached_call
from tradingview import cache_config as ttl
from tradingview import fetch, parsers, refs
from tradingview.fetch import TradingviewNotFound
from tradingview.schemas import FEED_PAGE_SIZE, SCREENER_PAGE_SIZE

SEARCH_PAGE_SIZE = 50      # symbol-search's own page
NEWS_FEED_SIZE = 200       # news-flow's own, unpaged ceiling
MAX_REPLY_FETCHES = 25     # reply threads expanded per comments page


# ---- symbol resolution ----------------------------------------------------------------

def _resolve_ticker(ticker):
    """A bare ticker -> the first exact-match listing (primary listings first)."""
    results, _remaining = parsers.parse_search(fetch.symbol_search(ticker))
    exact = [r for r in results if (r["ticker"] or "").upper() == ticker.upper()]
    if not exact:
        raise TradingviewNotFound(f"symbol {ticker} not found")
    # primary listings first, otherwise the site's own relevance order (a
    # stable sort; BTCUSD -> the listing TradingView itself ranks first)
    exact.sort(key=lambda r: not r.get("is_primary_listing"))
    return exact[0]["symbol"]


def _full_symbol(symbol):
    if ":" in symbol:
        return symbol
    return cached_call("tradingview.resolve", {"ticker": symbol}, _resolve_ticker, ttl.RESOLVE_CACHE)


def _symbol_page_path(full_symbol):
    exchange, ticker = refs.split_symbol(full_symbol)
    return f"/symbols/{exchange}-{ticker}/" if exchange else f"/symbols/{ticker}/"


def _pagination(page, per_page, total=None, has_next=None):
    block = {"page": page, "items_per_page": per_page}
    if total is not None:
        total = int(total)
        block["total_pages"] = max((total + per_page - 1) // per_page, 1)
        block["total_count"] = total
    else:
        block["has_next"] = bool(has_next)
        block["total_pages"] = None
        block["total_count"] = None
    return block


# ---- symbols/search -------------------------------------------------------------------

def _symbols_search(query, type, exchange, page):
    start = (page - 1) * SEARCH_PAGE_SIZE
    results, remaining = parsers.parse_search(fetch.symbol_search(query, type, exchange, start))
    total = start + len(results) + remaining
    return {"query": query, "results": results,
            "pagination": _pagination(page, SEARCH_PAGE_SIZE, total)}


def symbols_search(**data):
    return cached_call("tradingview.symbols_search", data, _symbols_search, ttl.SEARCH_CACHE)


# ---- symbols/quote --------------------------------------------------------------------

def _symbols_quote(symbol):
    full = [_full_symbol(s) for s in symbol]
    body = {"columns": list(refs.QUOTE_FIELDS), "symbols": {"tickers": full}, "options": {"lang": "en"}}
    _total, rows = parsers.parse_scan(fetch.scan("global", body, "quote"), refs.QUOTE_FIELDS)
    found = {row["symbol"] for row in rows}
    for row in rows:
        row["technical_rating_label"] = parsers.rating_label(row.get("technical_rating"))
    missing = [s for s in full if s not in found]
    if not rows:
        raise TradingviewNotFound(f"symbol {', '.join(symbol)} not found")
    return {"count": len(rows), "results": rows, "not_found": missing}


def symbols_quote(**data):
    return cached_call("tradingview.symbols_quote", data, _symbols_quote, ttl.QUOTE_CACHE)


# ---- symbols/details ------------------------------------------------------------------

def _symbol_record(symbol):
    """ONE cached record per symbol: the scanner profile fields plus the
    symbol page's description / FAQ. Unknown symbols raise NotFound from
    the scanner (a `null` body)."""
    full = _full_symbol(symbol)
    fields = parsers.parse_symbol_fields(fetch.symbol_fields(full, refs.DETAIL_FIELDS), refs.DETAIL_FIELDS)
    try:
        page = parsers.parse_symbol_page(fetch.symbol_page(_symbol_page_path(full)))
    except TradingviewNotFound:
        page = {"description": None, "category": None, "faq": [], "symbol_info": None, "title": None}
    return {"symbol": full, "fields": fields, "page": page}


def _record(symbol):
    return cached_call("tradingview.symbol", {"symbol": symbol}, _symbol_record, ttl.DETAILS_CACHE)


def symbol_details(symbol):
    record = _record(symbol)
    full, f, page = record["symbol"], record["fields"], record["page"]
    exchange, ticker = refs.split_symbol(full)
    info = page.get("symbol_info") or {}
    return {
        "symbol": full,
        "ticker": ticker,
        "exchange": exchange,
        "name": f.get("name"),
        "link": refs.symbol_link(full),
        "type": f.get("type"),
        "typespecs": f.get("typespecs") or [],
        "currency": f.get("currency"),
        "fundamental_currency": f.get("fundamental_currency"),
        "country": f.get("country"),
        "isin": f.get("isin") or info.get("isin_displayed"),
        "logo": f.get("logo") or f.get("base_currency_logoid"),
        "description": page.get("description"),
        "category": page.get("category"),
        "sector": f.get("sector"),
        "industry": f.get("industry"),
        "employees": f.get("employees"),
        "exchange_name": (info.get("source2") or {}).get("name"),
        "timezone": info.get("timezone"),
        "data_mode": f.get("data_mode"),
        "price": {
            "last": f.get("price"), "open": f.get("open"), "high": f.get("high"), "low": f.get("low"),
            "change": f.get("change"), "change_percent": f.get("change_percent"),
            "volume": f.get("volume"), "average_volume_10d": f.get("average_volume_10d"),
            "relative_volume_10d": f.get("relative_volume_10d"),
            "premarket": {"price": f.get("premarket_price"), "change_percent": f.get("premarket_change_percent")},
            "postmarket": {"price": f.get("postmarket_price"), "change_percent": f.get("postmarket_change_percent")},
        },
        "market_cap": f.get("market_cap"),
        "performance": {k: f.get(k) for k in (
            "performance_week", "performance_1m", "performance_3m", "performance_6m", "performance_ytd",
            "performance_1y", "performance_5y", "performance_10y", "performance_all_time", "volatility_daily", "beta")},
        "ranges": {k: f.get(k) for k in ("high_52_week", "low_52_week", "all_time_high", "all_time_low")},
        "valuation": {k: f.get(k) for k in (
            "pe_ratio_ttm", "eps_diluted_ttm", "eps_basic_ttm", "ps_ratio", "pb_ratio", "enterprise_value",
            "ev_to_ebitda_ttm", "revenue_ttm", "net_income_ttm", "gross_margin_ttm", "operating_margin_ttm",
            "net_margin_ttm", "return_on_equity", "total_shares_outstanding", "float_shares_outstanding")},
        "dividends": {
            "yield": f.get("dividend_yield"), "payout_ratio_ttm": f.get("dividend_payout_ratio_ttm"),
            "recent": {"ex_date": f.get("dividend_ex_date_recent"), "payment_date": f.get("dividend_payment_date_recent"),
                       "amount": f.get("dividend_amount_recent")},
            "upcoming": {"ex_date": f.get("dividend_ex_date_upcoming"), "payment_date": f.get("dividend_payment_date_upcoming"),
                         "amount": f.get("dividend_amount_upcoming")},
        },
        "earnings": {
            "last_release_date": f.get("earnings_release_date"),
            "next_release_date": f.get("earnings_release_next_date"),
            "next_release_time_code": f.get("earnings_release_next_time"),
            "eps_last_quarter": f.get("earnings_per_share_fq"),
            "eps_surprise_percent": f.get("eps_surprise_percent_fq"),
            "eps_forecast_next_quarter": f.get("earnings_per_share_forecast_next_fq"),
            "revenue_last_quarter": f.get("revenue_fq"),
            "revenue_forecast_next_quarter": f.get("revenue_forecast_next_fq"),
        },
        "analysts": {
            "price_target": {k: f.get(f"price_target_{k}") for k in ("average", "median", "high", "low")},
            # TradingView's 5-point scale: its fields buy / over / hold / under /
            # sell are the site's Strong buy / Buy / Hold / Sell / Strong sell
            # (they sum to recommendation_total, 2026-11-03)
            "recommendations": {
                "strong_buy": f.get("recommendation_buy"), "buy": f.get("recommendation_over"),
                "hold": f.get("recommendation_hold"), "sell": f.get("recommendation_under"),
                "strong_sell": f.get("recommendation_sell"), "total": f.get("recommendation_total"),
            },
            "consensus_score": f.get("recommendation_mark"),
        },
        "technicals": {"rating": f.get("technical_rating"), "label": parsers.rating_label(f.get("technical_rating")),
                       "rsi": f.get("rsi")},
        "crypto": {k: f.get(k) for k in ("rank", "circulating_supply", "total_supply", "max_supply", "volume_24h")}
        if f.get("rank") is not None or f.get("circulating_supply") is not None else None,
        "faq": page.get("faq") or [],
    }


# ---- symbols/technicals ---------------------------------------------------------------

def _symbol_technicals(symbol, interval):
    full = _full_symbol(symbol)
    suffix = refs.INTERVALS[interval][0]
    fields = parsers.technical_fields(suffix)
    payload = fetch.symbol_fields(full, fields)
    return {"symbol": full, "link": refs.symbol_link(full), "interval": interval,
            **parsers.parse_technicals(payload, suffix)}


def symbol_technicals(**data):
    return cached_call("tradingview.symbol_technicals", data, _symbol_technicals, ttl.TECHNICALS_CACHE)


# ---- symbols/financials ---------------------------------------------------------------

def _symbol_financials(symbol, statement, period):
    full = _full_symbol(symbol)
    suffix = refs.PERIODS[period]
    fields = parsers.statement_fields(statement, suffix)
    payload = fetch.symbol_fields(full, fields)
    parsed = parsers.parse_statement(payload, statement, suffix)
    if not any(v for v in parsed["history"].values()) and not any(parsed["latest"].values()):
        parsed["note"] = ("TradingView publishes no statement data for this symbol to anonymous clients "
                          "(non-equity symbols, or lines kept for logged-in users).")
    return {"symbol": full, "link": refs.symbol_link(full), "statement": statement, "period": period, **parsed}


def symbol_financials(**data):
    return cached_call("tradingview.symbol_financials", data, _symbol_financials, ttl.FINANCIALS_CACHE)


# ---- symbols/history ------------------------------------------------------------------

def _symbol_history(symbol, interval, bars):
    full = _full_symbol(symbol)
    resolution = refs.INTERVALS[interval][1]
    parsed = parsers.parse_ws_frames(fetch.chart_history(full, resolution, bars))
    if parsed["error"]:
        raise TradingviewNotFound(f"symbol {full} not found ({parsed['error']})")
    return {"symbol": full, "link": refs.symbol_link(full), "interval": interval, "requested_bars": bars,
            "count": len(parsed["bars"]), "symbol_info": parsed["symbol_info"], "bars": parsed["bars"]}


def symbol_history(**data):
    return cached_call("tradingview.symbol_history", data, _symbol_history, ttl.HISTORY_CACHE)


# ---- symbols/markets ------------------------------------------------------------------

def _symbol_markets(symbol):
    full = _full_symbol(symbol)
    exchange, ticker = refs.split_symbol(full)
    # the Markets tab lives under the bare ticker for multi-listed instruments
    payload = fetch.symbol_markets(f"/symbols/{ticker}/") if ticker else None
    if payload is None and exchange:
        payload = fetch.symbol_markets(_symbol_page_path(full))
    if payload is None:
        fetch.symbol_fields(full, ["name"])     # NotFound for an unknown symbol
        return {"symbol": full, "link": refs.symbol_link(full), "count": 0, "results": [],
                "note": "TradingView shows no Markets tab for this symbol (a single listing)."}
    total, rows = parsers.parse_symbol_markets(payload)
    return {"symbol": full, "link": refs.symbol_link(full), "count": total if total is not None else len(rows),
            "results": rows}


def symbol_markets(**data):
    return cached_call("tradingview.symbol_markets", data, _symbol_markets, ttl.MARKETS_CACHE)


# ---- screener -------------------------------------------------------------------------

def _stock_filters(market):
    filters = [{"left": "is_primary", "operation": "equal", "right": True},
               {"left": "type", "operation": "in_range", "right": ["stock", "dr"]}]
    if market == "america":
        filters.append({"left": "exchange", "operation": "in_range", "right": list(refs.US_EXCHANGES)})
    return filters


def _scan_page(market, columns, filters, sort, order, page, label, rename=True, extra=None):
    body = {"columns": list(columns), "filter": filters, "ignore_unknown_fields": False,
            "options": {"lang": "en"}, "range": [(page - 1) * SCREENER_PAGE_SIZE, page * SCREENER_PAGE_SIZE],
            "sort": {"sortBy": sort, "sortOrder": order}, "symbols": {}, "markets": [market]}
    if extra:
        body.update(extra)
    try:
        payload = fetch.scan(market, body, label)
    except fetch.TradingviewBadRequest as e:
        if "invalid range" not in str(e) or page <= 1:
            raise
        # past the last page: the scanner refuses the range; one cheap scan
        # for the total so the empty page still reports it
        body["range"] = [0, 1]
        payload = {"totalCount": fetch.scan(market, body, label).get("totalCount"), "data": []}
    total, rows = parsers.parse_scan(payload, columns, rename=rename)
    return total, rows


def _screener_scan(market, preset, filters, columns, sort, order, page):
    preset_sort, preset_order, preset_filters = refs.SCREENER_PRESETS.get(preset or "", ("market_cap_basic", "desc", ()))
    sort_by = sort or preset_sort
    sort_order = order or (preset_order if sort is None else "desc")
    all_filters = [] if market in refs.ASSET_MARKETS else _stock_filters(market)
    all_filters += [{"left": left, "operation": op, "right": right} for left, op, right in preset_filters]
    all_filters += filters or []
    chosen = columns or {"fields": list(refs.COLUMN_PRESETS["overview"]), "custom": False}
    fields = list(chosen["fields"])
    if sort_by not in fields:
        fields.append(sort_by)
    total, rows = _scan_page(market, fields, all_filters, sort_by, sort_order, page, "screener",
                             rename=not chosen["custom"])
    if not chosen["custom"]:
        for row in rows:
            if "technical_rating" in row:
                row["technical_rating_label"] = parsers.rating_label(row.get("technical_rating"))
    return {"market": market, "preset": preset, "sort": sort_by, "order": sort_order, "results": rows,
            "pagination": _pagination(page, SCREENER_PAGE_SIZE, total)}


def screener_scan(**data):
    return cached_call("tradingview.screener_scan", data, _screener_scan, ttl.SCREENER_CACHE)


def _screener_crypto(sort, order, page):
    sort_order = order or ("asc" if sort in ("crypto_total_rank", "base_currency") else "desc")
    total, rows = _scan_page("coin", refs.COIN_COLUMNS, [], sort, sort_order, page, "crypto screener")
    for row in rows:
        row["technical_rating_label"] = parsers.rating_label(row.get("technical_rating"))
    return {"sort": sort, "order": sort_order, "results": rows, "pagination": _pagination(page, SCREENER_PAGE_SIZE, total)}


def screener_crypto(**data):
    return cached_call("tradingview.screener_crypto", data, _screener_crypto, ttl.SCREENER_CACHE)


def _screener_etf(market, sort, order, page):
    sort_order = order or ("asc" if sort == "name" else "desc")
    filters = [{"left": "typespecs", "operation": "has", "right": ["etf"]}]
    total, rows = _scan_page(market, refs.ETF_COLUMNS, filters, sort, sort_order, page, "etf screener")
    return {"market": market, "sort": sort, "order": sort_order, "results": rows,
            "pagination": _pagination(page, SCREENER_PAGE_SIZE, total)}


def screener_etf(**data):
    return cached_call("tradingview.screener_etf", data, _screener_etf, ttl.SCREENER_CACHE)


# ---- calendars ------------------------------------------------------------------------

def _date_range(from_date, to_date):
    start = date.fromisoformat(from_date) if from_date else date.today()
    end = date.fromisoformat(to_date) if to_date else start + timedelta(days=7)
    return start.isoformat(), end.isoformat()


def _epoch_range(start_iso, end_iso):
    start = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc) + timedelta(days=1) - timedelta(seconds=1)
    return [int(start.timestamp()), int(end.timestamp())]


def _calendar_economic(from_date, to_date, countries, importance):
    start, end = _date_range(from_date, to_date)
    events = fetch.economic_events(start, end, countries or ["US"], importance)
    results = [parsers.parse_economic_event(e) for e in events]
    return {"from": start, "to": end, "countries": countries or ["US"], "count": len(results), "results": results}


def calendar_economic(**data):
    return cached_call("tradingview.calendar_economic", data, _calendar_economic, ttl.CALENDAR_CACHE)


def _calendar_earnings(from_date, to_date, market, status, page):
    start, end = _date_range(from_date, to_date)
    date_field = "earnings_release_next_date" if status == "upcoming" else "earnings_release_date"
    filters = [{"left": "is_primary", "operation": "equal", "right": True},
               {"left": date_field, "operation": "in_range", "right": _epoch_range(start, end)}]
    total, rows = _scan_page(market, refs.EARNINGS_COLUMNS, filters, "market_cap_basic", "desc", page,
                             "earnings calendar")
    results = []
    for row in rows:
        results.append({
            "symbol": row["symbol"], "ticker": row["ticker"], "exchange": row["exchange"], "name": row.get("name"),
            "link": row["link"], "logo": row.get("logo"), "currency": row.get("fundamental_currency") or row.get("currency"),
            "market_cap": row.get("market_cap"),
            "reported": {
                "date": row.get("earnings_release_date"), "time_code": row.get("earnings_release_time"),
                "eps_actual": row.get("earnings_per_share_fq"), "eps_forecast": row.get("earnings_per_share_forecast_fq"),
                "eps_surprise": row.get("eps_surprise_fq"), "eps_surprise_percent": row.get("eps_surprise_percent_fq"),
                "revenue_actual": row.get("revenue_fq"), "revenue_forecast": row.get("revenue_forecast_fq"),
                "publication_type_code": row.get("earnings_publication_type_fq"),
            },
            "upcoming": {
                "date": row.get("earnings_release_next_date"), "time_code": row.get("earnings_release_next_time"),
                "eps_forecast": row.get("earnings_per_share_forecast_next_fq"),
                "revenue_forecast": row.get("revenue_forecast_next_fq"),
                "publication_type_code": row.get("earnings_publication_type_next_fq"),
            },
        })
    return {"from": start, "to": end, "market": market, "status": status, "results": results,
            "pagination": _pagination(page, SCREENER_PAGE_SIZE, total)}


def calendar_earnings(**data):
    return cached_call("tradingview.calendar_earnings", data, _calendar_earnings, ttl.CALENDAR_CACHE)


def _calendar_dividends(from_date, to_date, market, page):
    start, end = _date_range(from_date, to_date)
    filters = [{"left": "is_primary", "operation": "equal", "right": True},
               {"left": "dividend_ex_date_upcoming", "operation": "in_range", "right": _epoch_range(start, end)}]
    total, rows = _scan_page(market, refs.DIVIDEND_COLUMNS, filters, "market_cap_basic", "desc", page,
                             "dividend calendar")
    results = []
    for row in rows:
        results.append({
            "symbol": row["symbol"], "ticker": row["ticker"], "exchange": row["exchange"], "name": row.get("name"),
            "link": row["link"], "logo": row.get("logo"), "currency": row.get("fundamental_currency") or row.get("currency"),
            "price": row.get("price"), "market_cap": row.get("market_cap"),
            "dividend_yield": row.get("dividend_yield"), "frequency": row.get("dividend_frequency"),
            "dividends_per_share_last_quarter": row.get("dividends_per_share_fq"),
            "upcoming": {"ex_date": row.get("dividend_ex_date_upcoming"), "payment_date": row.get("dividend_payment_date_upcoming"),
                         "amount": row.get("dividend_amount_upcoming")},
            "recent": {"ex_date": row.get("dividend_ex_date_recent"), "payment_date": row.get("dividend_payment_date_recent"),
                       "amount": row.get("dividend_amount_recent")},
        })
    return {"from": start, "to": end, "market": market, "results": results,
            "pagination": _pagination(page, SCREENER_PAGE_SIZE, total)}


def calendar_dividends(**data):
    return cached_call("tradingview.calendar_dividends", data, _calendar_dividends, ttl.CALENDAR_CACHE)


# ---- news -------------------------------------------------------------------------------

def _news_search(symbol, market, provider, top, lang, limit):
    filters = [f"lang:{lang}"]
    full = None
    if symbol:
        full = _full_symbol(symbol)
        filters.append(f"symbol:{full}")
    if market:
        filters.append(f"market:{market}")
    if provider:
        filters.append(f"provider:{provider}")
    if top:
        filters.append("priority:top_stories")
    items = [parsers.parse_news_item(i) for i in (fetch.news_flow(filters).get("items") or [])]
    return {"symbol": full, "market": market, "provider": provider, "count": len(items[:limit]),
            "available": len(items), "results": items[:limit]}


def news_search(**data):
    return cached_call("tradingview.news_search", data, _news_search, ttl.NEWS_CACHE)


def _news_details(story, lang):
    return parsers.parse_story(fetch.news_story(story, lang))


def news_details(**data):
    return cached_call("tradingview.news_details", data, _news_details, ttl.STORY_CACHE)


# ---- ideas -------------------------------------------------------------------------------

_PUBLIC_SORT = {v: k for k, v in refs.FEED_SORTS.items()}
_PUBLIC_SCRIPT_TYPE = {v: k for k, v in refs.SCRIPT_TYPES.items()}


def _feed_sort(sort):
    """The schema already maps the public name to the api/v1 token."""
    return refs.FEED_SORTS.get(sort, sort)


def _page_sort(sort, kind):
    """The feed PAGES accept fewer sort tokens than api/v1 (anything else is
    a 404): ideas pages `recent` or their default (this week's popular);
    scripts pages the same with `recent` as well."""
    return refs.PAGE_SORTS.get(kind, {}).get(sort)


def _public_sort(sort):
    return _PUBLIC_SORT.get(sort, sort)


def _feed(path, page, sort, kind, **extra):
    """One /ideas/... or /scripts/... feed page (topic, tag, text search or
    the scripts index) -> (items, pagination block). These pages are the
    site's own text search too: api/v1's q= / search= params are ignored
    upstream (2026-11-03, every value returned the unfiltered feed)."""
    items, total, has_next = parsers.parse_feed_page(fetch.feed_page(path, page, _page_sort(sort, kind), **extra))
    if total is not None:
        return items, _pagination(page, FEED_PAGE_SIZE, total)
    return items, _pagination(page, FEED_PAGE_SIZE, has_next=has_next)


def _feed_sort_served(sort, kind):
    """Feed pages sort by `recent` or by this week's popular (their default);
    `trending` exists on the symbol / user feeds only."""
    return "recent" if _page_sort(sort, kind) == "recent" else "popular"


def _ideas_search(symbol, user, query, topic, type, sort, page):
    if topic:
        items, block = _feed(f"/ideas/{topic.lower()}/", page, sort, "ideas")
        return {"topic": topic.lower(), "sort": _feed_sort_served(sort, "ideas"), "results": items, "pagination": block}
    if query:
        items, block = _feed(f"/ideas/search/{quote(query, safe='')}/", page, sort, "ideas")
        return {"query": query, "sort": _feed_sort_served(sort, "ideas"), "results": items, "pagination": block}
    params = {"page": page, "per_page": FEED_PAGE_SIZE, "sort": _feed_sort(sort)}
    full = _full_symbol(symbol) if symbol else None
    if full:
        params["symbol"] = full
    if user:
        params["by"] = user
    if type and type != "all":
        params["type"] = type
    payload = fetch.ideas_api(params)
    items, count, _size, _pages = parsers.parse_api_list(payload) if payload else ([], None, None, None)
    return {"symbol": full, "user": user, "sort": _public_sort(sort), "results": items,
            "pagination": _pagination(page, FEED_PAGE_SIZE, count if count is not None else 0)}


def ideas_search(**data):
    return cached_call("tradingview.ideas_search", data, _ideas_search, ttl.IDEAS_CACHE)


def _idea_details(idea):
    detail = fetch.idea_detail(idea)
    record = parsers.parse_idea_detail(detail)
    comments, _more = parsers.parse_comments({"results": detail.get("comments") or []})
    record["comments_preview"] = comments
    return record


def idea_details(**data):
    return cached_call("tradingview.idea_details", data, _idea_details, ttl.IDEA_CACHE)


def _idea_comments(idea, page):
    comments, has_next = parsers.parse_comments(fetch.idea_comments(idea, page))
    fetched = 0
    for comment in comments:
        if comment.get("replies_count") and fetched < MAX_REPLY_FETCHES:
            fetched += 1
            replies, _more = parsers.parse_comments(fetch.idea_comment_replies(idea, comment["id"]))
            comment["replies"] = replies
    return {"idea": idea, "results": comments,
            "pagination": _pagination(page, None, has_next=has_next)}


def idea_comments(**data):
    return cached_call("tradingview.idea_comments", data, _idea_comments, ttl.COMMENTS_CACHE)


# ---- scripts -----------------------------------------------------------------------------

def _scripts_search(query, user, tag, type, sort, page):
    public_type = _PUBLIC_SCRIPT_TYPE.get(type, type)
    if tag:
        items, block = _feed(f"/scripts/{tag.lower()}/", page, sort, "scripts", script_type=type)
        return {"tag": tag.lower(), "type": public_type, "sort": _feed_sort_served(sort, "scripts"), "results": items, "pagination": block}
    if query:
        items, block = _feed(f"/scripts/search/{quote(query, safe='')}/", page, sort, "scripts", script_type=type)
        return {"query": query, "type": public_type, "sort": _feed_sort_served(sort, "scripts"), "results": items, "pagination": block}
    if not user:
        items, block = _feed("/scripts/", page, sort, "scripts", script_type=type)
        return {"type": public_type, "sort": _feed_sort_served(sort, "scripts"), "results": items, "pagination": block}
    params = {"page": page, "per_page": FEED_PAGE_SIZE, "sort": _feed_sort(sort), "by": user}
    if type:
        params["script_type"] = type
    payload = fetch.scripts_api(params)
    items, count, _size, _pages = parsers.parse_api_list(payload) if payload else ([], None, None, None)
    return {"user": user, "type": public_type, "sort": _public_sort(sort), "results": items,
            "pagination": _pagination(page, FEED_PAGE_SIZE, count if count is not None else 0)}


def scripts_search(**data):
    return cached_call("tradingview.scripts_search", data, _scripts_search, ttl.SCRIPTS_CACHE)


def _script_details(script):
    record = parsers.parse_script_page(fetch.script_page(script))
    if record is None:
        raise TradingviewNotFound(f"script {script} not found")
    meta = record.get("script") or {}
    source = None
    if (meta.get("pine_id") or "").startswith("PUB;"):
        source = parsers.parse_pine(fetch.pine_source(meta["pine_id"]))
    record["source"] = source
    record["is_source_available"] = source is not None
    return record


def script_details(**data):
    return cached_call("tradingview.script_details", data, _script_details, ttl.SCRIPT_CACHE)


# ---- minds -------------------------------------------------------------------------------

def _minds_search(symbol, user, cursor):
    full = _full_symbol(symbol) if symbol else None
    if user:
        fetch.user_profile(user)          # NotFound for an unknown member (the feed is just empty)
    posts, next_cursor = parsers.parse_minds(fetch.minds(symbol=full, user=user, cursor=cursor))
    return {"symbol": full, "user": user, "count": len(posts), "results": posts, "next_cursor": next_cursor}


def minds_search(**data):
    return cached_call("tradingview.minds_search", data, _minds_search, ttl.MINDS_CACHE)


def _mind_details(mind):
    record = parsers.parse_mind(fetch.mind_detail(mind))
    comments = fetch.mind_comments(mind)
    record["comments"] = [parsers.parse_mind_comment(c) for c in (comments if isinstance(comments, list) else [])]
    return record


def mind_details(**data):
    return cached_call("tradingview.mind_details", data, _mind_details, ttl.MIND_CACHE)


# ---- users -------------------------------------------------------------------------------

def _user_details(user):
    return parsers.parse_user_profile(fetch.user_profile(user))


def user_details(**data):
    return cached_call("tradingview.user_details", data, _user_details, ttl.USER_CACHE)
