"""Asynchronous client and typed models for the VaultLink monitoring API."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Final

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .const import REQUEST_TIMEOUT, SHARE_STATUSES

API_PREFIX: Final = "/api/v2"


class VaultLinkError(Exception):
    """Base class for safe-to-display VaultLink client errors."""


class VaultLinkConnectionError(VaultLinkError):
    """The VaultLink service could not be reached."""


class VaultLinkAuthenticationError(VaultLinkError):
    """The service token is invalid or expired."""


class VaultLinkAuthorizationError(VaultLinkError):
    """The service token does not have the required scope."""


class VaultLinkRateLimitError(VaultLinkError):
    """The request remained rate limited after one compliant retry."""


class VaultLinkResponseError(VaultLinkError):
    """VaultLink returned an unexpected response."""


@dataclass(frozen=True, slots=True)
class Health:
    """VaultLink health response."""

    ok: bool
    version: str


@dataclass(frozen=True, slots=True)
class MonitoringSummary:
    """Aggregate, non-secret VaultLink monitoring values."""

    shares_total: int
    shares_available: int
    shares_protected: int
    shares_inactive: int
    shares_expired: int
    shares_download_limit_reached: int
    monthly_downloads: int
    monthly_zip_downloads: int
    monthly_previews: int
    storage_free_bytes: int
    storage_total_bytes: int


@dataclass(frozen=True, slots=True)
class MonitoringShare:
    """A redacted share returned by the monitoring endpoint."""

    share_id: int
    status: str
    expires_at: datetime | None
    download_count: int
    uploaded_bytes: int
    uploaded_files: int
    max_downloads: int | None
    max_upload_bytes: int | None
    max_upload_files: int | None


@dataclass(frozen=True, slots=True)
class SharesPage:
    """One monitoring shares page."""

    shares: tuple[MonitoringShare, ...]
    next_cursor: str | None


class VaultLinkApiClient:
    """Small aiohttp client for VaultLink's read-only monitoring surface."""

    def __init__(
        self,
        session: ClientSession,
        base_url: str,
        service_token: str,
        *,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        self._session = session
        self._base_url = base_url
        self._service_token = service_token
        self._timeout = ClientTimeout(total=timeout)

    async def async_get_live(self) -> Health:
        """Return the public liveness response."""
        payload = await self._async_get("/health/live", authenticated=False)
        return _parse_health(payload)

    async def async_get_ready(self) -> Health:
        """Return readiness, treating its documented 503 as valid data."""
        payload = await self._async_get(
            "/health/ready", authenticated=False, allow_ready_503=True
        )
        return _parse_health(payload)

    async def async_get_summary(self) -> MonitoringSummary:
        """Return aggregate monitoring data."""
        payload = await self._async_get("/monitoring/summary", authenticated=True)
        return _parse_summary(payload)

    async def async_get_shares_page(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        status: str = "all",
    ) -> SharesPage:
        """Return one redacted share page."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if status not in ("all", *SHARE_STATUSES):
            raise ValueError("invalid share status")
        params: dict[str, str | int] = {"limit": limit, "status": status}
        if cursor is not None:
            params["cursor"] = cursor
        payload = await self._async_get(
            "/monitoring/shares", authenticated=True, params=params
        )
        return _parse_shares_page(payload)

    async def _async_get(
        self,
        path: str,
        *,
        authenticated: bool,
        params: Mapping[str, str | int] | None = None,
        allow_ready_503: bool = False,
    ) -> Mapping[str, Any]:
        headers = (
            {"Authorization": f"Bearer {self._service_token}"}
            if authenticated
            else None
        )
        url = f"{self._base_url}{API_PREFIX}{path}"

        for attempt in range(2):
            try:
                async with self._session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=self._timeout,
                ) as response:
                    if response.status == 429 and attempt == 0:
                        delay = _retry_after_seconds(response)
                        await response.read()
                        await asyncio.sleep(delay)
                        continue
                    return await self._handle_response(
                        response, allow_ready_503=allow_ready_503
                    )
            except (TimeoutError, ClientError) as err:
                raise VaultLinkConnectionError("Unable to reach VaultLink") from err

        raise VaultLinkRateLimitError("VaultLink rate limit was reached")

    async def _handle_response(
        self, response: ClientResponse, *, allow_ready_503: bool
    ) -> Mapping[str, Any]:
        if response.status == 401:
            await response.read()
            raise VaultLinkAuthenticationError("Service token is invalid or expired")
        if response.status == 403:
            await response.read()
            raise VaultLinkAuthorizationError(
                "Service token is missing the monitoring scope"
            )
        if response.status == 429:
            await response.read()
            raise VaultLinkRateLimitError("VaultLink rate limit was reached")
        if response.status == 503 and not allow_ready_503:
            await response.read()
            raise VaultLinkResponseError("VaultLink service is unavailable")
        if response.status == 503 and allow_ready_503:
            payload = await _json_mapping(response)
            if payload.get("ok") is False:
                return payload
            raise VaultLinkResponseError("VaultLink returned invalid readiness data")
        if not 200 <= response.status < 300:
            await response.read()
            raise VaultLinkResponseError("VaultLink returned an unexpected status")
        return await _json_mapping(response)


async def _json_mapping(response: ClientResponse) -> Mapping[str, Any]:
    try:
        payload = await response.json(content_type=None)
    except (ValueError, ClientError) as err:
        raise VaultLinkResponseError("VaultLink returned invalid JSON") from err
    if not isinstance(payload, dict):
        raise VaultLinkResponseError("VaultLink returned an invalid response")
    return payload


def _parse_health(payload: Mapping[str, Any]) -> Health:
    ok = payload.get("ok")
    version = payload.get("version")
    if not isinstance(ok, bool) or not isinstance(version, str) or not version:
        raise VaultLinkResponseError("VaultLink returned invalid health data")
    return Health(ok=ok, version=version)


def _parse_summary(payload: Mapping[str, Any]) -> MonitoringSummary:
    shares = _mapping(payload.get("shares"))
    monthly = _mapping(
        payload.get("monthly")
        or payload.get("activity_this_month")
        or payload.get("month")
    )
    storage = _mapping(payload.get("storage"))
    return MonitoringSummary(
        shares_total=_required_int(payload, shares, "shares_total", "total"),
        shares_available=_required_int(
            payload, shares, "shares_available", "available"
        ),
        shares_protected=_required_int(
            payload, shares, "shares_protected", "protected"
        ),
        shares_inactive=_required_int(payload, shares, "shares_inactive", "inactive"),
        shares_expired=_required_int(payload, shares, "shares_expired", "expired"),
        shares_download_limit_reached=_required_int(
            payload,
            shares,
            "shares_download_limit_reached",
            "download_limit_reached",
        ),
        monthly_downloads=_required_int(
            payload, monthly, "monthly_downloads", "downloads"
        ),
        monthly_zip_downloads=_required_int(
            payload, monthly, "monthly_zip_downloads", "zip_downloads"
        ),
        monthly_previews=_required_int(
            payload, monthly, "monthly_previews", "previews"
        ),
        storage_free_bytes=_required_int(
            payload, storage, "storage_free_bytes", "free_bytes"
        ),
        storage_total_bytes=_required_int(
            payload, storage, "storage_total_bytes", "total_bytes"
        ),
    )


def _parse_shares_page(payload: Mapping[str, Any]) -> SharesPage:
    raw_shares = payload.get("shares", payload.get("items"))
    if not isinstance(raw_shares, list):
        raise VaultLinkResponseError("VaultLink returned invalid share data")
    shares = tuple(_parse_share(_mapping(item)) for item in raw_shares)
    cursor = payload.get("next_cursor")
    if cursor is None:
        pagination = _mapping(payload.get("pagination"))
        cursor = pagination.get("next_cursor")
    if cursor is not None and (not isinstance(cursor, str) or not cursor):
        raise VaultLinkResponseError("VaultLink returned an invalid cursor")
    return SharesPage(shares=shares, next_cursor=cursor)


def _parse_share(payload: Mapping[str, Any]) -> MonitoringShare:
    share_id = payload.get("id", payload.get("share_id"))
    status = payload.get("status")
    if not _is_int(share_id) or int(share_id) < 0:
        raise VaultLinkResponseError("VaultLink returned an invalid share id")
    if status not in SHARE_STATUSES:
        raise VaultLinkResponseError("VaultLink returned an invalid share status")
    return MonitoringShare(
        share_id=int(share_id),
        status=str(status),
        expires_at=_optional_datetime(payload.get("expires_at")),
        download_count=int(_optional_int(payload, "download_count", default=0) or 0),
        uploaded_bytes=int(
            _optional_int(payload, "uploaded_bytes", "upload_bytes", default=0) or 0
        ),
        uploaded_files=int(
            _optional_int(payload, "uploaded_files", "upload_files", default=0) or 0
        ),
        max_downloads=_optional_int(
            payload, "max_downloads", "download_limit", default=None
        ),
        max_upload_bytes=_optional_int(
            payload,
            "max_upload_bytes",
            "max_upload_total_size",
            default=None,
        ),
        max_upload_files=_optional_int(payload, "max_upload_files", default=None),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def _required_int(
    root: Mapping[str, Any], nested: Mapping[str, Any], flat_key: str, nested_key: str
) -> int:
    value = root.get(flat_key, nested.get(nested_key))
    if not _is_int(value) or int(value) < 0:
        raise VaultLinkResponseError("VaultLink returned invalid monitoring data")
    return int(value)


def _optional_int(
    payload: Mapping[str, Any], *keys: str, default: int | None
) -> int | None:
    value: Any = default
    for key in keys:
        if key in payload:
            value = payload[key]
            break
    if value is None:
        return None
    if not _is_int(value) or int(value) < 0:
        raise VaultLinkResponseError("VaultLink returned invalid share data")
    return int(value)


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise VaultLinkResponseError("VaultLink returned invalid share data")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise VaultLinkResponseError("VaultLink returned invalid share data") from err
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _retry_after_seconds(response: ClientResponse) -> float:
    value = response.headers.get("Retry-After")
    if value is None:
        return 1.0
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 1.0
