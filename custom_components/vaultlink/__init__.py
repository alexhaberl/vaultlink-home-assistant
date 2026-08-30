"""VaultLink integration setup."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VaultLinkApiClient
from .const import (
    CONF_BASE_URL,
    CONF_SERVICE_TOKEN,
    CONF_SUMMARY_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_SUMMARY_INTERVAL,
    PLATFORMS,
)
from .coordinator import VaultLinkCoordinator, VaultLinkSharesCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class VaultLinkRuntimeData:
    """Runtime objects owned by one config entry."""

    client: VaultLinkApiClient
    coordinator: VaultLinkCoordinator
    shares_coordinator: VaultLinkSharesCoordinator


type VaultLinkConfigEntry = ConfigEntry[VaultLinkRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: VaultLinkConfigEntry) -> bool:
    """Set up VaultLink from a config entry."""
    verify_ssl = entry.data[CONF_VERIFY_SSL]
    if not verify_ssl:
        _LOGGER.warning(
            "TLS certificate verification is disabled for a VaultLink config entry"
        )

    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = VaultLinkApiClient(
        session,
        entry.data[CONF_BASE_URL],
        entry.data[CONF_SERVICE_TOKEN],
    )
    interval = int(entry.options.get(CONF_SUMMARY_INTERVAL, DEFAULT_SUMMARY_INTERVAL))
    coordinator = VaultLinkCoordinator(
        hass,
        client,
        entry,
        update_interval=timedelta(seconds=interval),
    )
    shares_coordinator = VaultLinkSharesCoordinator(hass, client, entry)

    await asyncio.gather(
        coordinator.async_config_entry_first_refresh(),
        shares_coordinator.async_config_entry_first_refresh(),
    )
    entry.runtime_data = VaultLinkRuntimeData(
        client=client,
        coordinator=coordinator,
        shares_coordinator=shares_coordinator,
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VaultLinkConfigEntry) -> bool:
    """Unload a VaultLink config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: VaultLinkConfigEntry) -> None:
    """Reload after options or data change."""
    await hass.config_entries.async_reload(entry.entry_id)
