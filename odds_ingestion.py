"""Bounded market acquisition and coherent bookmaker-market validation.

No model or settlement rules live here. A market is atomic: never assemble
opposite sides from different bookmakers or different handicap lines.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Callable

try:
    import requests
except ModuleNotFoundError:  # Deployment normally installs requests; tests stay portable.
    from types import SimpleNamespace
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    class _Response:
        def __init__(self, raw, status):
            self.content, self.status_code = raw, status
        def json(self):
            import json
            return json.loads(self.content.decode("utf-8"))
        def raise_for_status(self):
            if self.status_code >= 400:
                raise URLError("HTTP failure")

    def _get(url, params=None, timeout=12):
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params)
        try:
            with urlopen(Request(url), timeout=timeout) as response:
                return _Response(response.read(), response.status)
        except HTTPError as exc:
            return _Response(exc.read(), exc.code)

    requests = SimpleNamespace(get=_get, Timeout=TimeoutError, ConnectionError=URLError, RequestException=URLError)

MARKETS = ("h2h", "spreads", "totals")


def timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, TypeError):
        return None


def complete_market(market, home, away, team_key, *, football):
    """Return normalised sides only for a genuine complete, finite market."""
    key = market.get("key")
    if key not in MARKETS or not home or not away or team_key(home) == team_key(away):
        return None
    sides = {}
    for outcome in market.get("outcomes") or []:
        if not isinstance(outcome, dict):
            return None
        name = str(outcome.get("name", "")).strip()
        if key == "totals":
            side = {"over": "over", "under": "under"}.get(name.casefold())
        else:
            side = ("home" if team_key(name) == team_key(home) else
                    "away" if team_key(name) == team_key(away) else
                    "draw" if key == "h2h" and football and name.casefold() == "draw" else None)
        if side is None or side in sides:
            return None
        try:
            price = float(outcome["price"])
            line = None if key == "h2h" else float(outcome["point"])
            if not math.isfinite(price) or price <= 1:
                return None
            if line is not None and (not math.isfinite(line) or not math.isclose(line * 4, round(line * 4))):
                return None
        except (KeyError, ValueError, TypeError, OverflowError):
            return None
        sides[side] = {"price": price, "line": line}
    required = ({"home", "away", "draw"} if football else {"home", "away"}) if key == "h2h" else (
        {"home", "away"} if key == "spreads" else {"over", "under"})
    if set(sides) != required:
        return None
    if key == "spreads" and not math.isclose(sides["home"]["line"] + sides["away"]["line"], 0, abs_tol=1e-8):
        return None
    if key == "totals" and (sides["over"]["line"] < 0 or not math.isclose(sides["over"]["line"], sides["under"]["line"])):
        return None
    return sides


def select_markets(event, team_key, *, football):
    candidates = {}
    for book in event.get("bookmakers") or []:
        if not isinstance(book, dict):
            continue
        for market in book.get("markets") or []:
            if not isinstance(market, dict):
                continue
            observed = market.get("last_update") or book.get("last_update")
            dt = timestamp(observed)
            if dt is None or dt > datetime.now(timezone.utc):
                continue
            sides = complete_market(market, event.get("home_team"), event.get("away_team"), team_key, football=football)
            if sides is not None:
                candidates.setdefault(market["key"], []).append({
                    "sides": sides, "observed_at": dt.isoformat(), "bookmaker": str(book.get("key") or book.get("title") or "unknown"),
                })
    # Freshest complete actual market; deterministic tie break, never synthetic median.
    return {key: max(items, key=lambda item: (item["observed_at"], item["bookmaker"])) for key, items in candidates.items()}


class FeedError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)  # Never includes a URL, response payload, or key.


def request_json(url, params):
    """At most two attempts on transient failures; never retry auth/quota."""
    for attempt in range(2):
        try:
            response = requests.get(url, params=params, timeout=12)
            status = response.status_code
            if status in (401, 403):
                raise FeedError("auth_failed")
            if status == 429:
                raise FeedError("quota_failed")
            if status >= 500:
                if attempt == 0:
                    time.sleep(.25)
                    continue
                raise FeedError("provider_failed")
            response.raise_for_status()
            return response.json()
        except FeedError:
            raise
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 0:
                time.sleep(.25)
                continue
            raise FeedError("connection_failed") from None
        except (requests.RequestException, ValueError):
            raise FeedError("response_failed") from None


def fetch_feed(url, api_key, regions, team_key, *, football, fallback_region="", accept=None, loader: Callable = request_json):
    """One primary batch, optionally ONE targeted missing-market batch.

    Fallback costs provider credits and is an explicit deployment setting.
    eventIds refer only to provider IDs, not API-Football/MLB schedule IDs.
    """
    params = {"apiKey": api_key, "regions": regions, "markets": ",".join(MARKETS), "oddsFormat": "decimal", "dateFormat": "iso"}
    raw = loader(url, params)
    if not isinstance(raw, list):
        raise FeedError("format_failed")
    events, diagnostics = [], []
    for event in raw:
        if not isinstance(event, dict) or not timestamp(event.get("commence_time")):
            continue
        if accept and not accept(event):
            continue
        events.append(dict(event))
    deficient = [e for e in events if len(select_markets(e, team_key, football=football)) < 3 and e.get("id")
                 and timestamp(e["commence_time"]) > datetime.now(timezone.utc)]
    if fallback_region and deficient:
        wanted = sorted(set(MARKETS) - set.intersection(*(set(select_markets(e, team_key, football=football)) for e in deficient)))
        supplement_params = {**params, "regions": fallback_region, "markets": ",".join(wanted),
                             "eventIds": ",".join(str(e["id"]) for e in deficient[:20])}
        try:
            supplement = loader(url, supplement_params)
            by_id = {str(e.get("id")): e for e in deficient[:20]}
            for extra in supplement if isinstance(supplement, list) else []:
                old = by_id.get(str(extra.get("id"))) if isinstance(extra, dict) else None
                if old and all(extra.get(k) == old.get(k) for k in ("home_team", "away_team", "commence_time")):
                    old["bookmakers"] = list(old.get("bookmakers") or []) + list(extra.get("bookmakers") or [])
        except Exception as exc:
            diagnostics.append({"code": exc.code if isinstance(exc, FeedError) else "supplement_failed"})
    for event in events:
        present = select_markets(event, team_key, football=football)
        diagnostics.append({"event_id": str(event.get("id") or ""), "code": "complete" if len(present) == 3 else "market_missing_or_invalid",
                            "markets": sorted(present), "missing": sorted(set(MARKETS) - set(present))})
    return events, diagnostics
