"""Tests for VaultLink coordinators."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vaultlink.api import (
    Health,
    MonitoringShare,
    SharesPage,
    VaultLinkAuthenticationError,
    VaultLinkResponseError,
)
from custom_components.vaultlink.coordinator import (
    VaultLinkCoordinator,
    VaultLinkSharesCoordinator,
)


def share(share_id: int) -> MonitoringShare:
    """Return one redacted share model."""
    return MonitoringShare(
        share_id=share_id,
        status="available",
        expires_at=None,
        download_count=0,
        uploaded_bytes=0,
        uploaded_files=0,
        max_downloads=None,
        max_upload_bytes=None,
        max_upload_files=None,
    )


async def test_readiness_false_is_success(hass, summary) -> None:
    """Keep the main coordinator successful when readiness is false."""
    client = AsyncMock()
    client.async_get_live.return_value = Health(ok=True, version="1.2.3")
    client.async_get_ready.return_value = Health(ok=False, version="1.2.3")
    client.async_get_summary.return_value = summary
    coordinator = VaultLinkCoordinator(
        hass,
        client,
        MockConfigEntry(domain="vaultlink"),
        update_interval=timedelta(seconds=60),
    )
    data = await coordinator._async_update_data()
    assert data.ready.ok is False
    assert data.summary == summary


async def test_401_becomes_config_entry_auth_failed(hass) -> None:
    """Trigger Home Assistant reauthentication on HTTP 401."""
    client = AsyncMock()
    client.async_get_live.side_effect = VaultLinkAuthenticationError("safe")
    coordinator = VaultLinkCoordinator(
        hass,
        client,
        MockConfigEntry(domain="vaultlink"),
        update_interval=timedelta(seconds=60),
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_server_error_becomes_update_failed(hass) -> None:
    """Map server failures to coordinator UpdateFailed."""
    client = AsyncMock()
    client.async_get_live.side_effect = VaultLinkResponseError("safe")
    coordinator = VaultLinkCoordinator(
        hass,
        client,
        MockConfigEntry(domain="vaultlink"),
        update_interval=timedelta(seconds=60),
    )
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_share_pagination(hass) -> None:
    """Follow cursors and merge redacted pages by stable share ID."""
    client = AsyncMock()
    client.async_get_shares_page.side_effect = [
        SharesPage(shares=(share(1), share(2)), next_cursor="next"),
        SharesPage(shares=(share(3),), next_cursor=None),
    ]
    coordinator = VaultLinkSharesCoordinator(
        hass, client, MockConfigEntry(domain="vaultlink")
    )
    data = await coordinator._async_update_data()
    assert set(data.shares) == {1, 2, 3}
    assert data.truncated is False
    assert client.async_get_shares_page.await_count == 2
    assert client.async_get_shares_page.await_args_list[1].kwargs["cursor"] == "next"


async def test_share_poll_is_bounded_and_warns_once(hass, caplog) -> None:
    """Stop at 1,000 shares while preserving the separate summary contract."""
    client = AsyncMock()

    async def page(*, limit: int, cursor: str | None, status: str) -> SharesPage:
        start = int(cursor or 0)
        return SharesPage(
            shares=tuple(share(item) for item in range(start, start + limit)),
            next_cursor=str(start + limit),
        )

    client.async_get_shares_page.side_effect = page
    coordinator = VaultLinkSharesCoordinator(
        hass, client, MockConfigEntry(domain="vaultlink")
    )
    first = await coordinator._async_update_data()
    second = await coordinator._async_update_data()
    assert first.loaded_count == 1000
    assert first.truncated is True
    assert second.truncated is True
    assert caplog.text.count("truncated at 1000 shares") == 1


async def test_repeated_cursor_fails(hass) -> None:
    """Defend against a malformed pagination loop."""
    client = AsyncMock()
    client.async_get_shares_page.side_effect = [
        SharesPage(shares=(share(1),), next_cursor="same"),
        SharesPage(shares=(share(2),), next_cursor="same"),
    ]
    coordinator = VaultLinkSharesCoordinator(
        hass, client, MockConfigEntry(domain="vaultlink")
    )
    with pytest.raises(UpdateFailed, match="repeated"):
        await coordinator._async_update_data()


async def test_duplicate_pages_are_bounded(hass) -> None:
    """Bound malformed pagination even when pages repeat the same share IDs."""
    client = AsyncMock()

    async def page(*, limit: int, cursor: str | None, status: str) -> SharesPage:
        current = int(cursor or 0)
        return SharesPage(
            shares=(share(1),),
            next_cursor=str(current + 1),
        )

    client.async_get_shares_page.side_effect = page
    coordinator = VaultLinkSharesCoordinator(
        hass, client, MockConfigEntry(domain="vaultlink")
    )
    data = await coordinator._async_update_data()
    assert data.loaded_count == 1
    assert data.truncated is True
    assert client.async_get_shares_page.await_count == 5
