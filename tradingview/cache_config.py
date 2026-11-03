"""Cache TTL per /tradingview/* endpoint (cache.py, keyed on the validated
params). Market data moves by the second, so the quote-bearing endpoints
cache only long enough to absorb a client polling the same symbol; the
community and reference surfaces cache for hours.
"""
from datetime import timedelta

# Anonymous quotes are 15-min delayed (update_mode delayed_streaming_900) for
# most exchanges, so a minute of caching costs no freshness a client can see.
QUOTE_CACHE = timedelta(minutes=1)
# Technical ratings are recomputed per bar; 5 min covers the intraday timeframes.
TECHNICALS_CACHE = timedelta(minutes=5)
# One combined symbol record (scanner profile + the symbol page's description)
# behind symbols/details; the price fields inside are delayed anyway.
DETAILS_CACHE = timedelta(hours=1)
# Statements change once a quarter.
FINANCIALS_CACHE = timedelta(hours=24)
# Candles: a websocket session per fetch; 10 min keeps a polling client off it.
HISTORY_CACHE = timedelta(minutes=10)
# Where a symbol trades (exchange listings) rarely changes.
MARKETS_CACHE = timedelta(hours=6)
# Screens re-rank every tick; 5 min keeps paging through one screen consistent.
SCREENER_CACHE = timedelta(minutes=5)
# Calendars are published days ahead; actuals land once per release.
CALENDAR_CACHE = timedelta(hours=1)
# Headline feeds refresh every few minutes; a story never changes once published.
NEWS_CACHE = timedelta(minutes=10)
STORY_CACHE = timedelta(hours=24)
# Idea / script feeds: new posts land by the minute, counts drift slowly.
IDEAS_CACHE = timedelta(minutes=15)
IDEA_CACHE = timedelta(hours=1)
COMMENTS_CACHE = timedelta(minutes=15)
SCRIPTS_CACHE = timedelta(hours=1)
SCRIPT_CACHE = timedelta(hours=24)
# Minds are a chat-like feed.
MINDS_CACHE = timedelta(minutes=10)
MIND_CACHE = timedelta(hours=1)
# Profiles: follower counts drift.
USER_CACHE = timedelta(hours=6)
# Symbol search and the bare-ticker -> EXCHANGE:TICKER resolution: listings are stable.
SEARCH_CACHE = timedelta(hours=24)
RESOLVE_CACHE = timedelta(days=7)
