"""Tests for VaultLink config-entry setup and unloading."""

from __future__ import annotations

import logging
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vaultlink import async_setup_entry, async_unload_entry
from custom_components.vaultlink.const import (
    CONF_BASE_URL,
    CONF_SERVICE_TOKEN,
    CONF_SUMMARY_INTERVAL,
    CONF_VERIFY_SSL,
    DOMAIN,
    PLATFORMS,
)
from custom_components.vaultlink.coordinator import (
    VaultLinkCoordinator,
    VaultLinkSharesCoordinator,
)


def make_entry(*, verify_ssl: bool = True) -> MockConfigEntry:
    """Return a representative VaultLink entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BASE_URL: "https://vaultlink.example",
            CONF_SERVICE_TOKEN: "secret-token",
            CONF_VERIFY_SSL: verify_ssl,
        },
        options={CONF_SUMMARY_INTERVAL: 120},
        unique_id="https://vaultlink.example",
    )


async def test_setup_entry(hass, caplog) -> None:
    """Build both coordinators, honor options, and forward platforms."""
    entry = make_entry(verify_ssl=False)
    entry.add_to_hass(hass)
    session = object()
    with (
        caplog.at_level(logging.WARNING),
        patch(
            "custom_components.vaultlink.async_get_clientsession",
            return_value=session,
        ) as get_session,
        patch.object(
            VaultLinkCoordinator,
            "async_config_entry_first_refresh",
            AsyncMock(),
        ) as refresh_main,
        patch.object(
            VaultLinkSharesCoordinator,
            "async_config_entry_first_refresh",
            AsyncMock(),
        ) as refresh_shares,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            AsyncMock(),
        ) as forward,
    ):
        assert await async_setup_entry(hass, entry) is True

    get_session.assert_called_once_with(hass, verify_ssl=False)
    refresh_main.assert_awaited_once()
    refresh_shares.assert_awaited_once()
    forward.assert_awaited_once_with(entry, PLATFORMS)
    assert entry.runtime_data.client._session is session
    assert entry.runtime_data.coordinator.update_interval == timedelta(seconds=120)
    assert "TLS certificate verification is disabled" in caplog.text
    await entry.runtime_data.coordinator.async_shutdown()
    await entry.runtime_data.shares_coordinator.async_shutdown()


async def test_unload_entry(hass) -> None:
    """Unload all forwarded platforms."""
    entry = make_entry()
    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ) as unload:
        assert await async_unload_entry(hass, entry) is True
    unload.assert_awaited_once_with(entry, PLATFORMS)
