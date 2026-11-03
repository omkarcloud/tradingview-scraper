"""TradingView transport: plain curl_cffi with browser-impersonated TLS. No
browser, no cookies, no tokens — every surface below answers anonymous
clients. Egress: the pod's own IP (config.tradingview_proxy(), knob
TRADINGVIEW_EXIT; pod probe 2026-11-03: 200 on all 16 surfaces direct,
datacenter and residential); a 401 / 403 / 429 on the pod IP moves every
new session to a sticky datacenter proxy exit for
config.TRADINGVIEW_BLOCK_HOLD_S seconds, and any retryable failure drops
the session so the retry rides a fresh exit (tofler/fetch.py is the
reference).

Upstream surfaces (the site's own JSON unless noted):

  * SCANNER   POST scanner.tradingview.com/<market>/scan  {columns, filter,
              range, sort, symbols, markets} -> {totalCount, data:[{s, d}]}
              GET  scanner.tradingview.com/symbol?symbol=EX:SYM&fields=a,b
              (a "|<tf>" suffix selects the timeframe of a technical field,
              "_fy_h" / "_fq_h" are the per-period history arrays). An
              unknown field is null, never an error; an unknown symbol is a
              literal `null` body with no_404=true.
  * SEARCH    GET  symbol-search.tradingview.com/symbol_search/v3/ (50 per
              page via start=, `symbols_remaining`).
  * NEWS      GET  news-mediator.tradingview.com/news-flow/v2/news with
              filter= params that MUST be alphabetical (400 otherwise); up to
              200 items, no cursor paging ("cursor ... not allowed").
              GET  news-headlines.tradingview.com/v2/story?id= for the body
              (astDescription); paywalled providers (Reuters, Dow Jones,
              permission "headline") carry a preview only.
  * CALENDAR  GET  economic-calendar.tradingview.com/events?from&to&countries
              &minImportance (ISO datetimes).
  * IDEAS     GET  www.tradingview.com/api/v1/ideas/ and /api/v1/scripts/
              (symbol=, by=<username>, q=, type=, sort=, page=, per_page=);
              an unknown username is a 400 "wrong_parameter_request", an
              unknown symbol a 400 with errors.symbol — both NotFound here.
              GET  /api/v1/ideas/<uuid>/ , /comments/ , /comments/<id>/replies/
              GET  /ideas/<slug>/page-N/?component-data-only=1 (and
              /scripts/<slug>/) -> the feed page's own JSON (24 per page).
  * SCRIPTS   GET  /script/<uuid>-<slug>/ (any slug; the page embeds
              ssrIdeaData), pine-facade.tradingview.com/pine-facade/get/
              <PUB;id>/last for the source of open-source scripts.
  * MINDS     GET  /api/v1/minds/?f=symbol&symbol= | f=user&user=, cursor c=;
              /api/v1/minds/<uid>/ and /comments/.
  * USERS     GET  /u/<name>/?component-data-only=1 -> ssrData (404 JSON
              {"code": 404} for an unknown name).
  * PAGES     GET  /symbols/<EX-SYM>/ (ld+json FinancialProduct description),
              /symbols/<X>/markets/?component-data-only=1 (every listing).
  * CHART     wss://data.tradingview.com/socket.io/websocket with the
              anonymous "unauthorized_user_token": resolve_symbol +
              create_series -> one timescale_update of N bars.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  TradingviewUpstreamError  transport failure / 5xx            — retryable
  TradingviewBlocked        401 / 403 / 429 / challenge page   — retryable
  TradingviewBadRequest     upstream 400 / 422 on our params   — never retried
  TradingviewNotFound       unknown symbol / idea / user ...   — never retried
"""
import json
import os
import random
import string
import sys
import threading
import time
from urllib.parse import quote, urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from tradingview.refs import SITE

SCANNER = "https://scanner.tradingview.com"
SEARCH = "https://symbol-search.tradingview.com"
NEWS = "https://news-mediator.tradingview.com"
HEADLINES = "https://news-headlines.tradingview.com"
CALENDAR = "https://economic-calendar.tradingview.com"
PINE = "https://pine-facade.tradingview.com"
CHART_WS = "wss://data.tradingview.com/socket.io/websocket?from=chart%2F&type=chart"

IMPERSONATE = "chrome"
JSON_TIMEOUT = 25
PAGE_TIMEOUT = 40       # symbol / script pages are 400-600 KB
WS_TIMEOUT = 30         # connect; the frame loop has its own wall budget
WS_BUDGET = 40

_ACCEPT_LANGUAGE = egress.site_accept_language("tradingview")
API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": _ACCEPT_LANGUAGE,
    "origin": SITE,
    "referer": SITE + "/",
}
XHR_HEADERS = {**API_HEADERS, "x-requested-with": "XMLHttpRequest"}
SCAN_HEADERS = {**API_HEADERS, "content-type": "text/plain;charset=UTF-8"}
PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "accept-language": _ACCEPT_LANGUAGE,
    "upgrade-insecure-requests": "1",
}


class TradingviewUpstreamError(UpstreamError):
    """Transport failure or 5xx — retryable."""


class TradingviewBlocked(TradingviewUpstreamError, Blocked):
    """401 / 403 / 429 or a challenge page where JSON was expected — retryable."""


class TradingviewBadRequest(BadRequest):
    """Upstream rejected the params — never retried."""


class TradingviewNotFound(NotFound):
    """Symbol / idea / script / mind / story / user does not exist — never retried."""


# ---- sessions ------------------------------------------------------------------

_local = threading.local()
_block_lock = threading.Lock()
_blocked_until = 0.0     # monotonic time until which new sessions avoid the pod's own IP


def _note_block():
    global _blocked_until
    with _block_lock:
        _blocked_until = time.monotonic() + config.TRADINGVIEW_BLOCK_HOLD_S


def _proxies():
    proxy = config.tradingview_proxy(blocked=time.monotonic() < _blocked_until)
    return {"http": proxy, "https": proxy} if proxy else None


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxies = _proxies()
        if proxies:
            sess.proxies = proxies
        _local.session = sess
    return sess


def _drop_session():
    """Close the thread's session so the retry rides a fresh exit."""
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _retrying(fn):
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except TradingviewUpstreamError as e:
            last = e
            if isinstance(e, TradingviewBlocked):
                _note_block()
            _drop_session()
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _upstream_message(resp):
    """The site's own error text out of a 4xx JSON body (several shapes)."""
    try:
        body = resp.json()
    except Exception:
        return resp.text[:200]
    if not isinstance(body, dict):
        return str(body)[:200]
    errors = body.get("errors")
    if isinstance(errors, dict):
        parts = []
        for field, messages in errors.items():
            text = " ".join(messages) if isinstance(messages, list) else str(messages)
            parts.append(f"{field}: {text}")
        return "; ".join(parts)[:300]
    for key in ("message", "detail", "errmsg", "error"):
        if body.get(key):
            return str(body[key])[:300]
    return resp.text[:200]


def _classify(resp, label):
    """Map an HTTP response to the taxonomy; return the response."""
    code = resp.status_code
    if code == 404:
        raise TradingviewNotFound(f"{label} not found")
    if code in (400, 422):
        raise TradingviewBadRequest(_upstream_message(resp))
    if code in (401, 403, 429):
        raise TradingviewBlocked(f"HTTP {code} for {label}")
    if code != 200:
        raise TradingviewUpstreamError(f"HTTP {code} for {label}")
    return resp


def _request(method, url, label, headers, timeout=JSON_TIMEOUT, **kw):
    def once():
        try:
            resp = _session().request(method, url, headers=headers, timeout=timeout, **kw)
        except Exception as e:
            raise TradingviewUpstreamError(f"request failed: {type(e).__name__}: {e}")
        return _classify(resp, label)
    return _retrying(once)


def _json(resp, label):
    try:
        return resp.json()
    except Exception:
        text = (resp.text or "")[:120]
        if "<html" in text.lower():
            raise TradingviewBlocked(f"HTML where JSON was expected for {label}")
        raise TradingviewUpstreamError(f"non-JSON response for {label}: {text}")


def _get_json(url, label, headers=API_HEADERS):
    return _json(_request("GET", url, label, headers), label)


# ---- scanner -------------------------------------------------------------------

def scan(market, body, label="screener"):
    """POST /<market>/scan -> {totalCount, data}. The scanner answers its own
    param errors as HTTP 200 {"error": ...} (an unknown filter operation) and
    an unknown market as a plain 404."""
    url = f"{SCANNER}/{market}/scan"
    resp = _request("POST", url, f"{label} ({market})", SCAN_HEADERS, data=json.dumps(body))
    payload = _json(resp, label)
    if not isinstance(payload, dict):
        raise TradingviewUpstreamError(f"unexpected scanner payload for {label}")
    if payload.get("error"):
        raise TradingviewBadRequest(str(payload["error"])[:300])
    return payload


def symbol_fields(symbol, fields):
    """GET /symbol?symbol=EX:SYM&fields=... -> {field: value}. A literal
    `null` body (no_404=true) is an unknown symbol."""
    query = urlencode({"symbol": symbol, "fields": ",".join(fields), "no_404": "true"})
    payload = _get_json(f"{SCANNER}/symbol?{query}", f"symbol {symbol}")
    if payload is None:
        raise TradingviewNotFound(f"symbol {symbol} not found")
    if not isinstance(payload, dict):
        raise TradingviewUpstreamError(f"unexpected symbol payload for {symbol}")
    return payload


# ---- symbol search -------------------------------------------------------------

def symbol_search(text, search_type=None, exchange=None, start=0):
    params = {"text": text, "hl": 0, "exchange": exchange or "", "lang": "en",
              "search_type": search_type or "undefined", "domain": "production",
              "sort_by_country": "US"}
    if start:
        params["start"] = start
    return _get_json(f"{SEARCH}/symbol_search/v3/?{urlencode(params)}", f"search {text!r}")


# ---- news ----------------------------------------------------------------------

def news_flow(filters):
    """GET /news-flow/v2/news with `filters` ("lang:en", "symbol:NASDAQ:AAPL",
    ...) sent in alphabetical order (the service 400s on any other order).
    An unknown symbol answers 422, mapped to NotFound."""
    query = "&".join("filter=" + quote(f, safe=":") for f in sorted(filters))
    url = f"{NEWS}/news-flow/v2/news?{query}&client=web&streaming=true"
    try:
        payload = _get_json(url, "news")
    except TradingviewBadRequest as e:
        if "unprocessable" in str(e).lower():
            raise TradingviewNotFound("no news feed for that symbol") from None
        raise
    return payload if isinstance(payload, dict) else {"items": []}


def news_story(story_id, lang="en"):
    """GET news-headlines /v2/story -> the story with its astDescription."""
    query = urlencode({"id": story_id, "lang": lang})
    return _get_json(f"{HEADLINES}/v2/story?{query}", f"story {story_id}")


# ---- economic calendar ---------------------------------------------------------

def economic_events(from_iso, to_iso, countries, min_importance=None):
    params = {"from": f"{from_iso}T00:00:00.000Z", "to": f"{to_iso}T23:59:59.000Z",
              "countries": ",".join(countries)}
    if min_importance is not None:
        params["minImportance"] = min_importance
    payload = _get_json(f"{CALENDAR}/events?{urlencode(params)}", "economic calendar")
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise TradingviewUpstreamError("unexpected economic calendar payload")
    return payload.get("result") or []


# ---- ideas / scripts (api/v1) ----------------------------------------------------

def _api_v1(kind, params, label):
    """GET /api/v1/<ideas|scripts>/ with the site's own filter params. A
    400 "wrong_parameter_request" is how it answers an unknown `by`
    username; a 400 naming the symbol is an unknown symbol."""
    url = f"{SITE}/api/v1/{kind}/?{urlencode(params)}"
    try:
        return _get_json(url, label)
    except TradingviewBadRequest as e:
        text = str(e)
        if "wrong_parameter_request" in text or "Bad request" in text:
            if params.get("by"):
                raise TradingviewNotFound(f"user {params['by']} not found") from None
            if params.get("page", 1) > 1 and "pagination" in text:
                return None          # past the last page
        if "symbol:" in text and "not valid" in text:
            raise TradingviewNotFound(f"symbol {params.get('symbol')} not found") from None
        raise


def ideas_api(params):
    return _api_v1("ideas", params, "ideas")


def scripts_api(params):
    return _api_v1("scripts", params, "scripts")


def feed_page(path, page=1, sort=None, **extra):
    """The JSON of an /ideas/<slug>/ or /scripts/... feed page
    (?component-data-only=1), 24 items per page. An unknown slug is a 404
    JSON {"code": 404}."""
    url = SITE + path.rstrip("/") + ("/" if page <= 1 else f"/page-{page}/")
    params = {"component-data-only": 1, **{k: v for k, v in extra.items() if v is not None}}
    if sort:
        params["sort"] = sort
    payload = _get_json(f"{url}?{urlencode(params)}", f"feed {path}", XHR_HEADERS)
    if isinstance(payload, dict) and payload.get("code") == 404:
        raise TradingviewNotFound(f"feed {path} not found")
    return payload


def idea_detail(uuid):
    return _get_json(f"{SITE}/api/v1/ideas/{uuid}/", f"idea {uuid}")


def idea_comments(uuid, page=1):
    query = f"?page={page}" if page > 1 else ""
    return _get_json(f"{SITE}/api/v1/ideas/{uuid}/comments/{query}", f"idea {uuid} comments")


def idea_comment_replies(uuid, comment_id):
    return _get_json(f"{SITE}/api/v1/ideas/{uuid}/comments/{comment_id}/replies/",
                     f"idea {uuid} replies")


def script_page(uuid):
    """GET /script/<uuid>/ -> HTML (the slug is optional; the page embeds
    ssrIdeaData). An unknown uuid is a real 404."""
    resp = _request("GET", f"{SITE}/script/{uuid}/", f"script {uuid}", PAGE_HEADERS, timeout=PAGE_TIMEOUT)
    return resp.text


def pine_source(script_id_part):
    """GET pine-facade get/<PUB;id>/last -> {source, ...} for an open-source
    script; {"success": false, "reason": ...} (returned as is) when the
    author protects the source."""
    url = f"{PINE}/pine-facade/get/{quote(script_id_part, safe='')}/last?no_4xx=true"
    return _get_json(url, f"pine {script_id_part}")


# ---- minds ---------------------------------------------------------------------

def minds(symbol=None, user=None, cursor=None):
    params = {"f": "symbol", "symbol": symbol} if symbol else {"f": "user", "user": user}
    if cursor:
        params["c"] = cursor
    return _get_json(f"{SITE}/api/v1/minds/?{urlencode(params)}", "minds")


def mind_detail(uid):
    return _get_json(f"{SITE}/api/v1/minds/{uid}/", f"mind {uid}")


def mind_comments(uid):
    return _get_json(f"{SITE}/api/v1/minds/{uid}/comments/", f"mind {uid} comments")


# ---- users ---------------------------------------------------------------------

def user_profile(username):
    url = f"{SITE}/u/{quote(username, safe='')}/?component-data-only=1"
    payload = _get_json(url, f"user {username}", XHR_HEADERS)
    if not isinstance(payload, dict) or payload.get("code") == 404 or "ssrData" not in payload:
        raise TradingviewNotFound(f"user {username} not found")
    return payload


# ---- pages ---------------------------------------------------------------------

def symbol_page(path):
    """GET a /symbols/... page -> HTML. Unknown symbols are a real 404."""
    resp = _request("GET", SITE + path, f"page {path}", PAGE_HEADERS, timeout=PAGE_TIMEOUT)
    return resp.text


def symbol_markets(path):
    """GET /symbols/<X>/markets/?component-data-only=1 -> JSON, or None when the
    site shows no Markets tab for the symbol (single-listing stocks: 404)."""
    try:
        payload = _get_json(f"{SITE}{path}markets/?component-data-only=1", f"markets {path}", XHR_HEADERS)
    except TradingviewNotFound:
        return None
    if isinstance(payload, dict) and payload.get("code") == 404:
        return None
    return payload


# ---- chart history (websocket) --------------------------------------------------

def _ws_message(name, params):
    body = json.dumps({"m": name, "p": params}, separators=(",", ":"))
    return f"~m~{len(body)}~m~{body}"


def _ws_session_id(prefix):
    return prefix + "_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))


def chart_history(symbol, resolution, bars):
    """One anonymous chart session: resolve the symbol, create a series of
    `bars` candles at `resolution` ("1", "60", "1D", "1W", ...) and return
    the raw frames received until series_completed (parsers.parse_ws_frames
    turns them into candles; a symbol_error frame is an unknown symbol)."""
    def once():
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxies = _proxies()
        if proxies:
            sess.proxies = proxies
        frames = []
        try:
            try:
                ws = sess.ws_connect(CHART_WS, headers={"origin": SITE}, timeout=WS_TIMEOUT)
            except Exception as e:
                raise TradingviewUpstreamError(f"websocket connect failed: {type(e).__name__}: {e}")
            chart = _ws_session_id("cs")
            symbol_spec = json.dumps({"adjustment": "splits", "symbol": symbol}, separators=(",", ":"))
            for message in (_ws_message("set_auth_token", ["unauthorized_user_token"]),
                            _ws_message("set_locale", ["en", "US"]),
                            _ws_message("chart_create_session", [chart, ""]),
                            _ws_message("resolve_symbol", [chart, "sds_sym_1", "=" + symbol_spec]),
                            _ws_message("create_series", [chart, "sds_1", "s1", "sds_sym_1", resolution, bars, ""])):
                ws.send(message)
            started = time.monotonic()
            done = False
            while not done and time.monotonic() - started < WS_BUDGET:
                try:
                    data, _flags = ws.recv()
                except Exception as e:
                    raise TradingviewUpstreamError(f"websocket read failed: {type(e).__name__}: {e}")
                text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
                frames.append(text)
                for chunk in text.split("~m~"):
                    if chunk.startswith("~h~"):          # heartbeat, echo it back
                        ws.send(f"~m~{len(chunk)}~m~{chunk}")
                    elif ('"series_completed"' in chunk or '"symbol_error"' in chunk
                          or '"critical_error"' in chunk or '"protocol_error"' in chunk):
                        done = True
            try:
                ws.close()
            except Exception:
                pass
            if not done:
                raise TradingviewUpstreamError(f"chart session for {symbol} did not complete in {WS_BUDGET}s")
            return frames
        finally:
            try:
                sess.close()
            except Exception:
                pass
    return _retrying(once)
