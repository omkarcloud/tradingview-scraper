"""tradingview/fetch.py exit ladder (no network). HTTP: the server's own IP
-> the gateway exit after a block (TRADINGVIEW_FALLBACK_EXIT) -> a datacenter
exit only when the gateway fails or is refused too (TRADINGVIEW_LAST_EXIT).
The chart websocket never rides the gateway: own IP, and a datacenter exit
while a block hold runs."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import egress  # noqa: E402
from tradingview import fetch  # noqa: E402
from scraper_utils.testing import hosted_only

DC = "http://dc-exit"
DC_PROXIES = {"http": DC, "https": DC}


class _Sess:
    def __init__(self, exit):
        self.exit, self.headers, self.closed = exit, {}, False

    def close(self):
        self.closed = True


@pytest.fixture
def built(monkeypatch):
    """Every HTTP session the fetch layer builds, in order (its exit on .exit)."""
    sessions = []
    monkeypatch.setattr(config, "datacenter_proxy", lambda *a, **k: DC)
    monkeypatch.setattr(egress, "new_session",
                        lambda exit=None, impersonate="chrome", **kw: sessions.append(_Sess(exit)) or sessions[-1])
    monkeypatch.setattr(config, "TRADINGVIEW_EXIT", "direct")
    monkeypatch.setattr(config, "TRADINGVIEW_FALLBACK_EXIT", "gateway")
    monkeypatch.setattr(config, "TRADINGVIEW_LAST_EXIT", "datacenter")
    monkeypatch.setattr(config, "MAX_RETRIES", 3)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    monkeypatch.setattr(fetch, "_blocked_until", 0.0)
    monkeypatch.setattr(fetch, "_last_until", 0.0)
    fetch._drop_session()
    fetch._local.last_try = False
    yield sessions
    fetch._drop_session()


def _call(outcomes):
    """One HTTP call: each attempt rides fetch._session() and ends as the
    next outcome says ("ok", "blocked", "error"). Returns the exits tried."""
    outcomes, tried = list(outcomes), []

    def once():
        tried.append(fetch._session().exit)
        outcome = outcomes.pop(0)
        if outcome == "blocked":
            raise fetch.TradingviewBlocked("HTTP 403")
        if outcome == "error":
            raise fetch.TradingviewUpstreamError("HTTP 502")
        return "ok"
    try:
        fetch._retrying(once)
    except fetch.TradingviewUpstreamError:
        pass
    return tried


@hosted_only
def test_the_own_ip_carries_the_traffic_and_a_transport_error_stays_on_it(built):
    assert _call(["ok"]) == [None]
    assert _call(["error", "error", "ok"]) == [None, None, None]
    assert _call(["ok"]) == [None]
    assert fetch._ws_proxies() is None


@hosted_only
def test_a_block_on_the_own_ip_moves_new_http_sessions_to_the_gateway(built):
    assert _call(["blocked", "ok"]) == [None, "gateway"]
    assert _call(["ok"]) == ["gateway"]                 # the same gateway session, for the hold
    assert [s.exit for s in built] == [None, "gateway"]
    assert built[0].closed and not built[1].closed


@hosted_only
def test_the_hold_ends_on_the_own_ip_again(built, monkeypatch):
    assert _call(["blocked", "ok"]) == [None, "gateway"]
    monkeypatch.setattr(fetch, "_blocked_until", 0.0)
    fetch._drop_session()
    assert _call(["ok"]) == [None]
    assert fetch._ws_proxies() is None


@hosted_only
def test_a_gateway_failure_makes_the_last_retry_on_the_datacenter_exit_for_that_call_only(built):
    assert _call(["blocked", "error", "ok"]) == [None, "gateway", DC]
    assert _call(["ok"]) == ["gateway"]                 # the next call is back on the gateway
    assert _call(["error", "error", "ok"]) == ["gateway", "gateway", DC]
    assert _call(["ok"]) == ["gateway"]
    assert fetch._last_until == 0.0                 # the gateway's own errors never park threads on the proxy


@hosted_only
def test_a_gateway_refusal_moves_new_http_sessions_to_the_datacenter_exit(built):
    assert _call(["blocked", "blocked", "ok"]) == [None, "gateway", DC]
    assert _call(["ok"]) == [DC]
    assert _call(["blocked", "ok"]) == [DC, DC]     # refused there too: a fresh datacenter exit, as before the gateway
    assert fetch._last_until > 0.0


@hosted_only
def test_the_chart_websocket_never_rides_the_gateway(built, monkeypatch):
    assert fetch._ws_proxies() is None                              # the own IP
    assert _call(["blocked", "ok"]) == [None, "gateway"]                # HTTP moves to the gateway ...
    assert fetch._ws_proxies() == DC_PROXIES                        # ... the websocket to a datacenter exit, as before
    assert _call(["blocked", "ok"]) == ["gateway", DC]                  # the gateway refused too
    monkeypatch.setattr(fetch, "_blocked_until", 0.0)
    assert fetch._ws_proxies() == DC_PROXIES                        # still off the own IP while the last hold runs
    monkeypatch.setattr(fetch, "_last_until", 0.0)
    assert fetch._ws_proxies() is None
    monkeypatch.setattr(config, "TRADINGVIEW_EXIT", "gateway")          # HTTP forced through the gateway
    assert fetch._ws_proxies() is None
    assert config.tradingview_ws_proxy(blocked=True) == DC
    monkeypatch.setattr(config, "TRADINGVIEW_LAST_EXIT", None)
    monkeypatch.setattr(config, "TRADINGVIEW_FALLBACK_EXIT", "gateway")
    assert config.tradingview_ws_proxy(blocked=True) is None        # no proxy tier configured at all
    monkeypatch.setattr(config, "TRADINGVIEW_EXIT", "datacenter")   # a proxy knob carries the websocket too
    assert fetch._ws_proxies() == DC_PROXIES


@hosted_only
def test_a_websocket_failure_starts_no_http_fallback(built):
    assert _call(["blocked", "ok"]) == [None, "gateway"]                # this thread's HTTP session is on the gateway
    attempts = []

    def chart():
        attempts.append(fetch._ws_proxies())
        raise fetch.TradingviewUpstreamError("websocket connect failed")
    with pytest.raises(fetch.TradingviewUpstreamError):
        fetch._retrying(chart, http=False)
    assert attempts == [DC_PROXIES] * 3
    assert not getattr(fetch._local, "last_try", False) and fetch._last_until == 0.0
    assert _call(["ok"]) == ["gateway"]


@hosted_only
def test_no_last_exit_keeps_every_retry_on_the_gateway(built, monkeypatch):
    monkeypatch.setattr(config, "TRADINGVIEW_LAST_EXIT", None)
    assert _call(["blocked", "blocked", "error"]) == [None, "gateway", "gateway"]
    assert _call(["error", "error", "error"]) == ["gateway", "gateway", "gateway"]


@hosted_only
def test_the_old_tiers_behave_as_before(built, monkeypatch):
    monkeypatch.setattr(config, "TRADINGVIEW_FALLBACK_EXIT", "datacenter")
    monkeypatch.setattr(config, "TRADINGVIEW_LAST_EXIT", None)
    assert _call(["blocked", "blocked", "ok"]) == [None, DC, DC]
    assert _call(["ok"]) == [DC]
    assert fetch._ws_proxies() == DC_PROXIES
    monkeypatch.setattr(config, "TRADINGVIEW_EXIT", "us")
    monkeypatch.setattr(config, "residential_proxy", lambda country, **k: f"http://res-{country}")
    fetch._drop_session()
    assert _call(["blocked", "ok"]) == ["http://res-us", "http://res-us"]       # a residential knob keeps its own tier
    assert fetch._ws_proxies() == {"http": "http://res-us", "https": "http://res-us"}


@hosted_only
def test_the_gateway_as_the_main_exit_keeps_the_datacenter_exit_for_the_last_retry(built, monkeypatch):
    monkeypatch.setattr(config, "TRADINGVIEW_EXIT", "gateway")
    assert _call(["ok"]) == ["gateway"]
    assert _call(["blocked", "error", "ok"]) == ["gateway", "gateway", DC]
    assert _call(["ok"]) == ["gateway"]
    assert fetch._blocked_until == 0.0 and fetch._last_until == 0.0     # a refused gateway address says nothing about the own IP
    assert fetch._ws_proxies() is None
