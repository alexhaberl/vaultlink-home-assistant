"""Tests for the VaultLink API client without opening network sockets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientConnectionError, ClientSession

from custom_components.vaultlink.api import (
    VaultLinkApiClient,
    VaultLinkAuthenticationError,
    VaultLinkAuthorizationError,
    VaultLinkConnectionError,
    VaultLinkRateLimitError,
    VaultLinkResponseError,
)

SUMMARY = {
    "shares": {
        "total": 6,
        "available": 2,
        "protected": 1,
        "inactive": 1,
        "expired": 1,
        "download_limit_reached": 1,
    },
    "activity_this_month": {
        "downloads": 21,
        "zip_downloads": 3,
        "previews": 8,
    },
    "storage": {"free_bytes": 1024, "total_bytes": 4096},
}


class FakeResponse:
    """Minimal aiohttp response double."""

    def __init__(
        self,
        status: int,
        payload: Any,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.status = status
        self.payload = payload
        self.headers = headers or {}
        self.read_count = 0

    async def read(self) -> bytes:
        """Record body draining."""
        self.read_count += 1
        return b""

    async def json(self, *, content_type: None = None) -> Any:
        """Return or raise the configured JSON result."""
        del content_type
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeRequestContext:
    """Asynchronous request context double."""

    def __init__(self, result: FakeResponse | Exception) -> None:
        self.result = result

    async def __aenter__(self) -> FakeResponse:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeSession:
    """Ordered aiohttp session double."""

    def __init__(self, *results: FakeResponse | Exception) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> FakeRequestContext:
        self.calls.append((url, kwargs))
        return FakeRequestContext(self.results.pop(0))


def make_client(
    *results: FakeResponse | Exception,
) -> tuple[VaultLinkApiClient, FakeSession]:
    """Return a client backed by ordered fake responses."""
    session = FakeSession(*results)
    client = VaultLinkApiClient(
        cast(ClientSession, session), "https://vaultlink.example", "secret-token"
    )
    return client, session


@pytest.mark.parametrize(
    ("status", "exception"),
    [(401, VaultLinkAuthenticationError), (403, VaultLinkAuthorizationError)],
)
async def test_auth_statuses(status: int, exception: type[Exception]) -> None:
    """Map auth responses and never surface their bodies."""
    response = FakeResponse(status, {"message": "must never surface"})
    client, _session = make_client(response)
    with pytest.raises(exception) as caught:
        await client.async_get_summary()
    assert response.read_count == 1
    assert "must never surface" not in str(caught.value)


async def test_ready_503_is_data() -> None:
    """Treat the documented readiness 503 as a successful false value."""
    client, _session = make_client(FakeResponse(503, {"ok": False, "version": "1.2.3"}))
    ready = await client.async_get_ready()
    assert ready.ok is False
    assert ready.version == "1.2.3"


async def test_ready_503_must_have_false_ok() -> None:
    """Reject an unrelated 503 payload on the readiness endpoint."""
    client, _session = make_client(FakeResponse(503, {"ok": True}))
    with pytest.raises(VaultLinkResponseError):
        await client.async_get_ready()


async def test_authorization_header_and_pagination() -> None:
    """Use header authentication and parse only redacted share fields."""
    client, session = make_client(
        FakeResponse(
            200,
            {
                "shares": [
                    {
                        "id": 7,
                        "status": "available",
                        "expires_at": "2027-01-02T03:04:05Z",
                        "download_count": 2,
                        "uploaded_bytes": 10,
                        "uploaded_files": 1,
                        "max_downloads": 5,
                        "max_upload_total_size": 20,
                        "max_upload_files": 3,
                    }
                ],
                "next_cursor": "next",
            },
        )
    )
    page = await client.async_get_shares_page(limit=200, cursor="cursor")

    url, kwargs = session.calls[0]
    assert url.endswith("/api/v2/monitoring/shares")
    assert kwargs["headers"] == {"Authorization": "Bearer secret-token"}
    assert kwargs["params"] == {"limit": 200, "status": "all", "cursor": "cursor"}
    assert page.next_cursor == "next"
    assert page.shares[0].share_id == 7
    assert page.shares[0].max_upload_bytes == 20
    assert page.shares[0].expires_at is not None


async def test_health_is_public() -> None:
    """Never send the service token to a public health endpoint."""
    client, session = make_client(FakeResponse(200, {"ok": True, "version": "1.2.3"}))
    health = await client.async_get_live()
    assert health.ok is True
    assert session.calls[0][1]["headers"] is None


async def test_429_honors_retry_after(monkeypatch) -> None:
    """Wait for Retry-After before retrying once."""
    first = FakeResponse(429, {}, headers={"Retry-After": "7"})
    client, session = make_client(first, FakeResponse(200, SUMMARY))
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.vaultlink.api.asyncio.sleep", sleep)

    result = await client.async_get_summary()

    sleep.assert_awaited_once_with(7.0)
    assert first.read_count == 1
    assert len(session.calls) == 2
    assert result.monthly_downloads == 21


async def test_second_429_raises(monkeypatch) -> None:
    """Avoid an unbounded retry loop when rate limiting persists."""
    client, _session = make_client(
        FakeResponse(429, {}, headers={"Retry-After": "invalid"}),
        FakeResponse(429, {}),
    )
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.vaultlink.api.asyncio.sleep", sleep)
    with pytest.raises(VaultLinkRateLimitError):
        await client.async_get_summary()
    sleep.assert_awaited_once_with(1.0)


@pytest.mark.parametrize("error", [TimeoutError(), ClientConnectionError()])
async def test_connection_errors_are_sanitized(error: Exception) -> None:
    """Translate transport errors to a stable, secret-free exception."""
    client, _session = make_client(error)
    with pytest.raises(VaultLinkConnectionError) as caught:
        await client.async_get_summary()
    assert "secret-token" not in str(caught.value)


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(500, {}),
        FakeResponse(503, {}),
        FakeResponse(200, ValueError("bad json")),
        FakeResponse(200, []),
    ],
)
async def test_invalid_responses(response: FakeResponse) -> None:
    """Reject server errors, invalid JSON, and non-object JSON."""
    client, _session = make_client(response)
    with pytest.raises(VaultLinkResponseError):
        await client.async_get_summary()


async def test_flat_summary_is_supported() -> None:
    """Parse the monitoring endpoint's flat field representation."""
    flat = {
        "shares_total": 6,
        "shares_available": 2,
        "shares_protected": 1,
        "shares_inactive": 1,
        "shares_expired": 1,
        "shares_download_limit_reached": 1,
        "monthly_downloads": 21,
        "monthly_zip_downloads": 3,
        "monthly_previews": 8,
        "storage_free_bytes": 1024,
        "storage_total_bytes": 4096,
    }
    client, _session = make_client(FakeResponse(200, flat))
    assert (await client.async_get_summary()).storage_total_bytes == 4096


@pytest.mark.parametrize("bad_value", [-1, True, "6", None])
async def test_invalid_summary_values(bad_value: object) -> None:
    """Reject negative and non-integer monitoring counters."""
    payload = {**SUMMARY, "shares": {**SUMMARY["shares"], "total": bad_value}}
    client, _session = make_client(FakeResponse(200, payload))
    with pytest.raises(VaultLinkResponseError):
        await client.async_get_summary()


@pytest.mark.parametrize("limit", [0, 201])
async def test_invalid_page_limit(limit: int) -> None:
    """Enforce the documented server page size."""
    client, _session = make_client()
    with pytest.raises(ValueError, match="limit"):
        await client.async_get_shares_page(limit=limit)


async def test_invalid_status() -> None:
    """Enforce the documented monitoring status values."""
    client, _session = make_client()
    with pytest.raises(ValueError, match="status"):
        await client.async_get_shares_page(limit=1, status="secret")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"shares": [{"id": -1, "status": "available"}]},
        {"shares": [{"id": 1, "status": "unknown"}]},
        {"shares": [{"id": 1, "status": "available", "download_count": -1}]},
        {"shares": [{"id": 1, "status": "available", "expires_at": []}]},
        {"shares": [], "next_cursor": ""},
    ],
)
async def test_invalid_share_data(payload: dict[str, Any]) -> None:
    """Reject malformed redacted-share responses."""
    client, _session = make_client(FakeResponse(200, payload))
    with pytest.raises(VaultLinkResponseError):
        await client.async_get_shares_page(limit=1)


async def test_share_aliases_and_nested_cursor() -> None:
    """Support endpoint aliases while retaining only safe fields."""
    client, _session = make_client(
        FakeResponse(
            200,
            {
                "items": [
                    {
                        "share_id": 9,
                        "status": "available",
                        "expires_at": "2027-01-02T03:04:05",
                        "upload_bytes": 10,
                        "upload_files": 2,
                        "download_limit": None,
                    }
                ],
                "pagination": {"next_cursor": "next"},
            },
        )
    )
    page = await client.async_get_shares_page(limit=1, status="available")
    assert page.next_cursor == "next"
    assert page.shares[0].uploaded_bytes == 10
    assert page.shares[0].expires_at is not None
    assert page.shares[0].expires_at.utcoffset() is not None
