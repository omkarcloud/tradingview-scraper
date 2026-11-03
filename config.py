"""Configuration for the TradingView Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT                port the API listens on (default 8000)
    TRADINGVIEW_PROXY   proxy URL for every request, e.g. http://user:pass@host:port
                        (default: none — direct). TradingView served every
                        surface to a direct connection, a cloud server and
                        datacenter proxies alike, so you very likely don't
                        need this. Set it only if you start seeing 502
                        "blocked" errors at high volume.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request). A block
# drops the session, so the retry starts on a fresh connection.
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# How long the module remembers a block before it opens new sessions
# normally again (it has no second exit to move to here).
TRADINGVIEW_BLOCK_HOLD_S = 300

TRADINGVIEW_PROXY = os.environ.get("TRADINGVIEW_PROXY") or None


def tradingview_proxy(blocked=False):
    """The proxy for one session or one chart websocket (None = direct)."""
    return os.environ.get("TRADINGVIEW_PROXY") or None
