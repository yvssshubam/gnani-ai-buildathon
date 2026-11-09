"""Put an area that isn't on our map list on the map, with OpenStreetMap's free address search.

Our own list (gazetteer.py) knows a few dozen localities. A caller who says "Sainikpuri, pin code
500094" used to get a ticket with no pin on the map ("find it by hand"). Now that area name and/or
PIN code is looked up with Nominatim (OpenStreetMap): free, no key. Its rules: at most one request
a second, and a User-Agent that names the app. Results are cached, so each area is asked for once.

The lookup runs in the background, so the caller never waits for it. It places the AREA (or the
PIN code's area), not the door: the ticket says so, and an officer still checks the exact spot.
Map data (c) OpenStreetMap contributors.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import httpx

from .config import settings
from .models import Location, Ticket

log = logging.getLogger("geocode")

FOUND_REASON = "area placed by OpenStreetMap address search: check the exact spot"

_cache: dict[str, Optional[tuple[float, float, str]]] = {}
_lock = threading.Lock()          # one request at a time, at most one a second
_last_request = 0.0


def area_key(loc: Location) -> Optional[str]:
    """What we would look up for this location, or None if there's nothing to look up."""
    if not (loc.locality or loc.pincode):
        return None
    return f"{(loc.locality or '').strip().lower()}|{loc.pincode or ''}"


def _queries(loc: Location) -> list[dict]:
    """Most specific first: the area with its PIN code, then the PIN code alone, then the area alone."""
    out = []
    if loc.locality and loc.pincode:
        out.append({"q": f"{loc.locality}, {loc.pincode}, India"})
    if loc.pincode:
        out.append({"postalcode": loc.pincode, "country": "India"})
    if loc.locality:
        out.append({"q": f"{loc.locality}, India"})
    return out


def _get(params: dict, http: Callable) -> Optional[tuple[float, float, str]]:
    global _last_request
    wait = 1.1 - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()
    r = http(settings.geocode_url, params={**params, "format": "jsonv2", "limit": 1, "countrycodes": "in"},
             headers={"User-Agent": settings.geocode_user_agent}, timeout=settings.geocode_timeout)
    r.raise_for_status()
    hits = r.json()
    if not hits:
        return None
    hit = hits[0]
    return float(hit["lat"]), float(hit["lon"]), hit.get("display_name", "")


def lookup(loc: Location, http: Callable = httpx.get) -> Optional[tuple[float, float, str]]:
    """(lat, lon, place name) for the location's area, or None. Never raises."""
    key = area_key(loc)
    if key is None:
        return None
    with _lock:
        if key in _cache:
            return _cache[key]
        found = None
        try:
            for params in _queries(loc):
                found = _get(params, http)
                if found:
                    break
        except Exception as e:   # no internet, timeout, rate limited: the ticket just stays off the map
            log.warning("address search failed for %r: %s", key, e)
            return None          # not cached: try again on the next turn
        _cache[key] = found
        return found


def place(ticket: Ticket, store, off_map_reason: str, http: Callable = httpx.get) -> bool:
    """Look the area up and, if found and the caller hasn't changed it meanwhile, pin the ticket."""
    loc = ticket.location
    key = area_key(loc)
    found = lookup(loc, http)
    if not found or area_key(loc) != key or loc.lat is not None:
        return False
    loc.lat, loc.lon = round(found[0], 6), round(found[1], 6)
    if off_map_reason in ticket.followup_reasons:
        ticket.followup_reasons.remove(off_map_reason)
    if FOUND_REASON not in ticket.followup_reasons:
        ticket.followup_reasons.append(FOUND_REASON)
    log.info("ticket %s placed at %s (%s)", ticket.id, (loc.lat, loc.lon), found[2])
    store.save(ticket)
    return True


def place_in_background(ticket: Ticket, store, off_map_reason: str) -> None:
    threading.Thread(target=place, args=(ticket, store, off_map_reason), daemon=True).start()