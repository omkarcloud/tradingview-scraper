"""Marshmallow request schemas for every /tradingview/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url` / `id` pair); every reference field accepts the bare id OR the
tradingview.com link of the same record (tradingview/refs.py):

    symbol   NASDAQ:AAPL, AAPL, BTCUSD or a /symbols/... or /chart/?symbol= link
    idea     the 8-char idea id or its /chart/<SYM>/<id>-<slug>/ link
    script   the 8-char script id or its /script/<id>-<slug>/ link
    mind     the Minds post id or its /symbols/<X>/minds/?mind=<id> link
    story    the news story id or its /news/<id>-<slug>/ link
    user     a username or its /u/<username>/ link

Choice params map to the site's own tokens through the tables in refs.py
(intervals, search types, news markets, feed sorts, script types,
calendar importance, screener presets / column presets / markets).
"""
import re

from marshmallow import ValidationError, fields, validates_schema

from schema_fields import (
    BaseSchema, ChoiceField, CommaListField, CountryCodeField, DateField, LanguageCodeField, LimitField,
    PageField, PositiveInt, QueryField, RefField, StrippedString, TrueOnlyFlag,
)
from tradingview import refs

SCREENER_PAGE_SIZE = 50
FEED_PAGE_SIZE = 24
MAX_HISTORY_BARS = 5000
MAX_QUOTE_SYMBOLS = 20

_FIELD_RE = re.compile(r"^[A-Za-z0-9_.|\[\]+\-]{1,64}$")
_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$")


# ---- reference fields ----------------------------------------------------------------

class SymbolField(RefField):
    resolver = staticmethod(refs.resolve_symbol)


class IdeaField(RefField):
    resolver = staticmethod(refs.resolve_idea)


class ScriptField(RefField):
    resolver = staticmethod(refs.resolve_script)


class MindField(RefField):
    resolver = staticmethod(refs.resolve_mind)


class StoryField(RefField):
    resolver = staticmethod(refs.resolve_story)


class UserField(RefField):
    resolver = staticmethod(refs.resolve_user)


class SymbolListField(StrippedString):
    """One or more symbols / symbol links, comma-separated (max 20)."""

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        symbols = []
        for raw in value.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                symbol = refs.resolve_symbol(raw)
            except ValueError as e:
                raise ValidationError(f"{raw!r}: {e}")
            if symbol not in symbols:
                symbols.append(symbol)
        if not symbols:
            raise ValidationError("Must not be empty.")
        if len(symbols) > MAX_QUOTE_SYMBOLS:
            raise ValidationError(f"At most {MAX_QUOTE_SYMBOLS} symbols.")
        return symbols


class ScannerFieldName(StrippedString):
    """A TradingView scanner field id (market_cap_basic, Perf.YTD, RSI|1W ...)."""

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        if not _FIELD_RE.match(value):
            raise ValidationError("Must be a TradingView field id such as market_cap_basic, Perf.YTD or RSI.")
        return value


def _coerce(value):
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    if _NUMBER_RE.match(value):
        number = float(value)
        return int(number) if number.is_integer() and "." not in value and "e" not in low else number
    return value


class FiltersField(StrippedString):
    """Screener filters as `field:operation:value` items separated by commas;
    a range or list value uses `|`: `market_cap_basic:greater:1000000000,
    RSI:in_range:30|70, sector:equal:Finance`. Operations: greater, less,
    egreater, eless, equal, nequal, in_range, not_in_range, match, nmatch,
    has, has_none_of (TradingView's own names). -> [{left, operation, right}]."""

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        parsed = []
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            parts = item.split(":", 2)
            if len(parts) != 3 or not parts[2].strip():
                raise ValidationError(f"{item!r}: use field:operation:value (e.g. RSI:less:30).")
            left, operation, right = (p.strip() for p in parts)
            if not _FIELD_RE.match(left):
                raise ValidationError(f"{left!r} is not a TradingView field id.")
            if operation not in refs.FILTER_OPERATIONS:
                raise ValidationError(f"{operation!r} is not one of: {', '.join(refs.FILTER_OPERATIONS)}.")
            values = [_coerce(v.strip()) for v in right.split("|") if v.strip()]
            if operation in ("in_range", "not_in_range", "has", "has_none_of"):
                parsed.append({"left": left, "operation": operation, "right": values})
            else:
                if len(values) != 1:
                    raise ValidationError(f"{item!r}: {operation} takes one value.")
                parsed.append({"left": left, "operation": operation, "right": values[0]})
        if len(parsed) > 15:
            raise ValidationError("At most 15 filters.")
        return parsed or None


class ColumnsField(StrippedString):
    """Comma list of TradingView field ids and/or column preset names
    (overview, performance, valuation, dividends, profitability, income,
    balance, cashflow, technicals) -> {"fields": [...], "custom": bool}."""

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        fields_, custom = [], False
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            preset = refs.COLUMN_PRESETS.get(item.lower())
            if preset:
                for f in preset:
                    if f not in fields_:
                        fields_.append(f)
                continue
            if not _FIELD_RE.match(item):
                raise ValidationError(f"{item!r} is neither a column preset ({', '.join(refs.COLUMN_PRESETS)}) "
                                      "nor a TradingView field id.")
            custom = True
            if item not in fields_:
                fields_.append(item)
        if not fields_:
            return None
        if len(fields_) > 80:
            raise ValidationError("At most 80 columns.")
        return {"fields": fields_, "custom": custom}


# ---- symbols ------------------------------------------------------------------------

class SymbolsSearchSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={"description": "ticker, company or instrument name, ISIN or CUSIP"})
    type = ChoiceField(refs.SEARCH_TYPES, metadata={
        "description": "asset class: stock, etf, futures, forex, crypto, index, bond, economy, cfd, option (default all)"})
    exchange = StrippedString(load_default=None, metadata={"description": "exchange code to search within (NASDAQ, NSE, BINANCE, ...)"})
    page = PageField(max_page=200, metadata={"description": "page of 50 results"})


class SymbolsQuoteSchema(BaseSchema):
    symbol = SymbolListField(required=True, metadata={
        "description": "one or more symbols (NASDAQ:AAPL, BTCUSD, FX:EURUSD) or symbol links, comma-separated, max 20"})


class SymbolSchema(BaseSchema):
    symbol = SymbolField(metadata={"description": "EXCHANGE:TICKER, a bare ticker, or a tradingview.com symbol link"})


class SymbolsTechnicalsSchema(SymbolSchema):
    interval = ChoiceField(list(refs.INTERVALS), load_default="1d", metadata={
        "description": "timeframe of the gauge: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 1d (default), 1w, 1mo"})


class SymbolsFinancialsSchema(SymbolSchema):
    statement = ChoiceField(list(refs.STATEMENTS), load_default="income", metadata={
        "description": "income (default), balance, cashflow or ratios"})
    period = ChoiceField(list(refs.PERIODS), load_default="annual", metadata={
        "description": "annual (default, up to 20 fiscal years) or quarterly (up to 32 quarters)"})


class SymbolsHistorySchema(SymbolSchema):
    interval = ChoiceField(list(refs.INTERVALS), load_default="1d", metadata={
        "description": "candle size: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 1d (default), 1w, 1mo"})
    bars = PositiveInt(max_value=MAX_HISTORY_BARS, load_default=300, metadata={
        "description": "number of most recent candles, 1-5000 (default 300)"})


# ---- screener ------------------------------------------------------------------------

class ScreenerScanSchema(BaseSchema):
    market = ChoiceField(list(refs.MARKETS), load_default="america", metadata={
        "description": "scanner market: a country (america, uk, india, japan, germany, ...) or an asset class "
                       "(crypto, coin, forex, futures, bond, cfd, economics2); default america"})
    preset = ChoiceField(list(refs.SCREENER_PRESETS), metadata={
        "description": "ready-made screen: " + ", ".join(refs.SCREENER_PRESETS)})
    filters = FiltersField(load_default=None, metadata={
        "description": "field:operation:value filters, comma-separated (RSI:less:30,market_cap_basic:greater:1e9); "
                       "ranges/lists with | (RSI:in_range:30|70)"})
    columns = ColumnsField(load_default=None, metadata={
        "description": "column presets (overview, performance, valuation, dividends, profitability, income, balance, "
                       "cashflow, technicals) and/or TradingView field ids, comma-separated; default overview"})
    sort = ScannerFieldName(load_default=None, metadata={"description": "field to sort by (default market_cap_basic, or the preset's own)"})
    order = ChoiceField(["desc", "asc"], metadata={"description": "sort direction (default desc, or the preset's own)"})
    page = PageField(max_page=400, metadata={"description": "page of 50 rows"})


class ScreenerCryptoSchema(BaseSchema):
    sort = ChoiceField(refs.COIN_SORTS, load_default=refs.COIN_SORTS["rank"], metadata={
        "description": "rank (default), market_cap, volume, change, price, name"})
    order = ChoiceField(["asc", "desc"], metadata={"description": "sort direction (default asc for rank/name, desc otherwise)"})
    page = PageField(max_page=100, metadata={"description": "page of 50 coins"})


class ScreenerEtfSchema(BaseSchema):
    market = ChoiceField(list(refs.COUNTRY_MARKETS), load_default="america", metadata={
        "description": "country market of the fund listing (default america)"})
    sort = ChoiceField(refs.ETF_SORTS, load_default=refs.ETF_SORTS["aum"], metadata={
        "description": "aum (default), volume, change, expense_ratio, return_1y, flows_1m, dividend_yield, name"})
    order = ChoiceField(["desc", "asc"], metadata={"description": "sort direction (default desc, asc for name)"})
    page = PageField(max_page=200, metadata={"description": "page of 50 funds"})


# ---- calendars -----------------------------------------------------------------------

class _DateRangeSchema(BaseSchema):
    from_date = DateField(data_key="from", metadata={"description": "first day, YYYY-MM-DD (default today)"})
    to_date = DateField(data_key="to", metadata={"description": "last day, YYYY-MM-DD (default from + 7 days)"})

    @validates_schema
    def _ordered(self, data, **kwargs):
        if data.get("from_date") and data.get("to_date") and data["to_date"] < data["from_date"]:
            raise ValidationError("Must not be earlier than from.", "to")


class CalendarEconomicSchema(_DateRangeSchema):
    countries = CommaListField(max_items=30, load_default=None, metadata={
        "description": "ISO country codes (US,GB,EU,JP,...), comma-separated; default US"})
    importance = ChoiceField(refs.IMPORTANCE, metadata={
        "description": "minimum importance: low (default, everything), medium or high"})


class CalendarEarningsSchema(_DateRangeSchema):
    market = ChoiceField(list(refs.COUNTRY_MARKETS), load_default="america", metadata={
        "description": "country market (default america)"})
    status = ChoiceField(["upcoming", "reported"], load_default="upcoming", metadata={
        "description": "upcoming (default, scheduled releases in the range) or reported (releases already made)"})
    page = PageField(max_page=200, metadata={"description": "page of 50 companies"})


class CalendarDividendsSchema(_DateRangeSchema):
    market = ChoiceField(list(refs.COUNTRY_MARKETS), load_default="america", metadata={
        "description": "country market (default america)"})
    page = PageField(max_page=200, metadata={"description": "page of 50 companies"})


# ---- news ------------------------------------------------------------------------------

class NewsSearchSchema(BaseSchema):
    symbol = SymbolField(required=False, load_default=None, metadata={
        "description": "news about one symbol (NASDAQ:AAPL or a symbol link)"})
    market = ChoiceField(list(refs.NEWS_MARKETS), metadata={
        "description": "a market feed: stock, crypto, forex, futures, index, bond, corp_bond, etf, economic"})
    provider = StrippedString(load_default=None, metadata={
        "description": "a provider slug (reuters, dow-jones, cointelegraph, tradingview, ...)"})
    top = TrueOnlyFlag(metadata={"description": "true = TradingView's top-stories feed"})
    lang = LanguageCodeField(allow_locale=False, load_default="en", metadata={"description": "feed language (default en)"})
    limit = LimitField(default=50, max_size=200, metadata={"description": "headlines to return, 1-200 (default 50)"})


class NewsDetailsSchema(BaseSchema):
    story = StoryField(metadata={"description": "news story id or its tradingview.com/news/ link"})
    lang = LanguageCodeField(allow_locale=False, load_default="en", metadata={"description": "story language (default en)"})


# ---- ideas / scripts -----------------------------------------------------------------

class IdeasSearchSchema(BaseSchema):
    symbol = SymbolField(required=False, load_default=None, metadata={"description": "ideas about one symbol"})
    user = UserField(required=False, load_default=None, metadata={"description": "ideas published by one member (username or profile link)"})
    query = StrippedString(load_default=None, metadata={
        "description": "free text, TradingView's own idea search (titles and descriptions); a feed of its own"})
    topic = StrippedString(load_default=None, metadata={
        "description": "a feed slug from tradingview.com/ideas/<slug>/: a market (stocks, crypto, forex, futures, "
                       "indices, bonds, economy), a tag (trend-analysis, fibonacci, ...) or editors-picks"})
    type = ChoiceField(refs.IDEA_TYPES, metadata={
        "description": "trade, education or all (default all); applies to the symbol / user feeds"})
    sort = ChoiceField(refs.FEED_SORTS, load_default=refs.FEED_SORTS["recent"], metadata={
        "description": "recent (default), popular (this week's most liked) or trending (symbol / user feeds only)"})
    page = PageField(max_page=42, metadata={"description": "page of 24 ideas (the site serves at most 1000 per feed)"})

    @validates_schema
    def _one_feed(self, data, **kwargs):
        if data.get("topic") and any(data.get(k) for k in ("symbol", "user", "query")):
            raise ValidationError("topic is a feed of its own; combine symbol, user and query without it.", "topic")
        if data.get("query") and any(data.get(k) for k in ("symbol", "user")):
            raise ValidationError("query searches every idea; use it without symbol and user.", "query")
        if data.get("type") and (data.get("topic") or data.get("query")):
            raise ValidationError("type applies to the symbol / user feeds, not to topic or query.", "type")
        if data.get("topic") and not re.match(r"^[a-z0-9][a-z0-9\-]{0,60}$", data["topic"].lower()):
            raise ValidationError("Must be a feed slug such as crypto or trend-analysis.", "topic")


class IdeaSchema(BaseSchema):
    idea = IdeaField(metadata={"description": "idea id (8 characters) or its tradingview.com chart link"})


class IdeaCommentsSchema(IdeaSchema):
    page = PageField(max_page=100, metadata={"description": "page of top-level comments"})


class ScriptsSearchSchema(BaseSchema):
    query = StrippedString(load_default=None, metadata={
        "description": "free text, TradingView's own script search (names and descriptions)"})
    user = UserField(required=False, load_default=None, metadata={"description": "scripts published by one member (username or profile link)"})
    tag = StrippedString(load_default=None, metadata={
        "description": "a tag slug from tradingview.com/scripts/<tag>/ (rsi, volume, supertrend, aapl, ...)"})
    type = ChoiceField(refs.SCRIPT_TYPES, metadata={"description": "indicator, strategy or library (default all)"})
    sort = ChoiceField(refs.FEED_SORTS, load_default=refs.FEED_SORTS["popular"], metadata={
        "description": "popular (default), recent or trending (user feed only)"})
    page = PageField(max_page=42, metadata={"description": "page of 24 scripts (the site serves at most 1000 per feed)"})

    @validates_schema
    def _tag_feed(self, data, **kwargs):
        if data.get("tag") and any(data.get(k) for k in ("query", "user")):
            raise ValidationError("tag is a feed of its own; combine query and user without it.", "tag")
        if data.get("query") and data.get("user"):
            raise ValidationError("query searches every script; use it without user.", "query")
        if data.get("tag") and not re.match(r"^[a-z0-9][a-z0-9\-]{0,60}$", data["tag"].lower()):
            raise ValidationError("Must be a tag slug such as rsi or supertrend.", "tag")


class ScriptSchema(BaseSchema):
    script = ScriptField(metadata={"description": "script id (8 characters) or its tradingview.com/script/ link"})


# ---- minds / users --------------------------------------------------------------------

class MindsSearchSchema(BaseSchema):
    symbol = SymbolField(required=False, load_default=None, metadata={"description": "the Minds feed of one symbol"})
    user = UserField(required=False, load_default=None, metadata={"description": "the Minds posts of one member"})
    cursor = StrippedString(load_default=None, metadata={
        "description": "the next_cursor of the previous page (the feed pages by cursor, not by number)"})

    @validates_schema
    def _one_of(self, data, **kwargs):
        if bool(data.get("symbol")) == bool(data.get("user")):
            raise ValidationError("Give exactly one of symbol or user.", "symbol")


class MindSchema(BaseSchema):
    mind = MindField(metadata={"description": "Minds post id or its tradingview.com minds link"})


class UserSchema(BaseSchema):
    user = UserField(metadata={"description": "username or tradingview.com/u/<username>/ link"})
