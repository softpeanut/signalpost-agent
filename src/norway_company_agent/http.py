from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class FetchResult:
    url: str
    status: int
    elapsed_ms: int
    bytes_received: int
    body: Any = None
    error: str | None = None
    content_sha256: str | None = None
    retrieved_at: str | None = None
    effective_at: str | None = None
    attempts: int = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_json(url: str, *, timeout: float = 20.0, attempts: int = 3) -> FetchResult:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    last_error = "request failed"
    last_status = 0
    last_elapsed = 0
    last_raw = b""
    for attempt in range(attempts):
        started = time.monotonic()
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "builderr-signalpost-poc/0.1 (+https://builderr.ai)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                elapsed = int((time.monotonic() - started) * 1000)
                return FetchResult(url, response.status, elapsed, len(raw), json.loads(raw), content_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=_utc_now(), attempts=attempt + 1)
        except urllib.error.HTTPError as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            raw = exc.read()
            if exc.code in {404, 410}:
                return FetchResult(url, exc.code, elapsed, len(raw), error=f"HTTP {exc.code}", content_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=_utc_now(), attempts=attempt + 1)
            last_error = f"HTTP {exc.code}"
            last_status = exc.code
            last_elapsed = elapsed
            last_raw = raw
            retryable = exc.code in {408, 425, 429} or 500 <= exc.code < 600
            if not retryable:
                return FetchResult(url, exc.code, elapsed, len(raw), error=last_error, content_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=_utc_now(), attempts=attempt + 1)
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = type(exc).__name__
            last_status = 0
            last_elapsed = int((time.monotonic() - started) * 1000)
            last_raw = b""
            retry_after = None
        if attempt + 1 < attempts:
            delay = 0.4 * (2**attempt)
            try:
                delay = max(delay, min(float(retry_after), 30.0)) if retry_after is not None else delay
            except (TypeError, ValueError):
                pass
            time.sleep(delay)
    return FetchResult(
        url,
        last_status,
        last_elapsed,
        len(last_raw),
        error=last_error,
        content_sha256=hashlib.sha256(last_raw).hexdigest() if last_raw else None,
        retrieved_at=_utc_now(),
        attempts=attempts,
    )
