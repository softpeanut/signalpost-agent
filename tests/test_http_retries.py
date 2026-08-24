from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.http import FetchResult, fetch_json  # noqa: E402
from norway_company_agent.official import _classified  # noqa: E402


class _Response:
    status = 200

    def __init__(self, body: dict):
        self.raw = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.raw


def _http_error(status: int, body: bytes = b"error", retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return urllib.error.HTTPError("https://example.test", status, "error", headers, io.BytesIO(body))


def test_retry_after_is_bounded_and_actual_attempts_are_reported() -> None:
    with (
        patch("norway_company_agent.http.urllib.request.urlopen", side_effect=[_http_error(429, retry_after="2"), _Response({"ok": True})]),
        patch("norway_company_agent.http.time.sleep") as sleep,
    ):
        result = fetch_json("https://example.test", attempts=2)

    assert result.status == 200
    assert result.body == {"ok": True}
    assert result.attempts == 2
    sleep.assert_called_once_with(2.0)
    assert _classified("registry_live", "official", result)["retry_count"] == 1


def test_permanent_http_error_is_not_retried() -> None:
    with (
        patch("norway_company_agent.http.urllib.request.urlopen", side_effect=_http_error(403, b"forbidden")) as request,
        patch("norway_company_agent.http.time.sleep") as sleep,
    ):
        result = fetch_json("https://example.test", attempts=3)

    assert result.status == 403
    assert result.attempts == 1
    assert result.bytes_received == len(b"forbidden")
    assert request.call_count == 1
    sleep.assert_not_called()
    assert "retry_count" not in _classified("registry_live", "official", result)


def test_exhausted_transient_error_preserves_final_http_status_and_retries() -> None:
    with (
        patch("norway_company_agent.http.urllib.request.urlopen", side_effect=[_http_error(503), _http_error(503)]) as request,
        patch("norway_company_agent.http.time.sleep") as sleep,
    ):
        result = fetch_json("https://example.test", attempts=2)

    assert result.status == 503
    assert result.attempts == 2
    assert result.error == "HTTP 503"
    assert request.call_count == 2
    sleep.assert_called_once_with(0.4)
    assert _classified("registry_live", "official", result)["retry_count"] == 1


def test_attempt_count_must_be_positive() -> None:
    try:
        fetch_json("https://example.test", attempts=0)
    except ValueError as exc:
        assert str(exc) == "attempts must be at least 1"
    else:
        raise AssertionError("expected ValueError")


def test_snapshot_fetch_result_keeps_single_attempt_default() -> None:
    result = FetchResult("https://example.test", 200, 1, 2)
    assert result.attempts == 1
