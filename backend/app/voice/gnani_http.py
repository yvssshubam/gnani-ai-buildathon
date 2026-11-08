"""Shared HTTP bits for Gnani: auth header, error parsing, retry with backoff."""
import asyncio
import json
import time

import httpx

# Statuses worth retrying. 429 = rate limited (some accounts allow one active request; no
# Retry-After header is sent), 500/502/503/504 = server or upstream timeout.
RETRYABLE = {429, 500, 502, 503, 504}
BACKOFF_SECONDS = (0.5, 1.0, 2.0)  # short: a caller is waiting on the line

HINTS = {
    401: "API key missing or invalid. Use the Speech API key (header X-API-Key-ID), not an Agent Builder key.",
    402: "Out of credits on this Gnani account.",
    403: "This key isn't allowed to use this API or model.",
}


class GnaniError(Exception):
    def __init__(self, service: str, status: int, code: str, message: str):
        self.service, self.status, self.code = service, status, code
        self.retryable = status in RETRYABLE
        hint = HINTS.get(status, "")
        super().__init__(f"{service} HTTP {status} {code}: {message} {hint}".strip())


def parse_error(service: str, r: httpx.Response) -> GnaniError:
    """Gnani uses several error shapes: {"error": {"type"...}}, {"detail": {"error_code"...}},
    {"detail": [...]} (422), and {"code": ...} (504)."""
    code, message = "", ""
    try:
        body = r.json()
    except (ValueError, json.JSONDecodeError):
        return GnaniError(service, r.status_code, "", r.text[:200])
    if isinstance(body, dict):
        err, detail = body.get("error"), body.get("detail")
        if isinstance(err, dict):
            code, message = err.get("type", ""), err.get("message", "")
        elif isinstance(detail, dict):
            code, message = detail.get("error_code", ""), detail.get("message", "")
        elif isinstance(detail, list):
            code, message = "VALIDATION", json.dumps(detail, ensure_ascii=False)[:200]
        else:
            code, message = str(body.get("code", "")), str(body.get("message", ""))[:200]
    return GnaniError(service, r.status_code, code, message)


async def post(client: httpx.AsyncClient, service: str, url: str, api_key: str,
               **kwargs) -> tuple[httpx.Response, float]:
    """POST with retries on RETRYABLE statuses and network errors. Returns (response, seconds of
    the successful attempt). Raises GnaniError on a non-200 that isn't retryable or keeps failing."""
    headers = {"X-API-Key-ID": api_key, **kwargs.pop("headers", {})}
    last: Exception | None = None
    for attempt in range(len(BACKOFF_SECONDS) + 1):
        if attempt:
            await asyncio.sleep(BACKOFF_SECONDS[attempt - 1])
        start = time.perf_counter()
        try:
            r = await client.post(url, headers=headers, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last = GnaniError(service, 0, type(e).__name__, str(e))
            continue
        secs = time.perf_counter() - start
        if r.status_code == 200:
            return r, secs
        last = parse_error(service, r)
        if not last.retryable:
            raise last
    raise last  # type: ignore[misc]
