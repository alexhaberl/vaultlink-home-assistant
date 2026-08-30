"""Diagnostics support for VaultLink."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant

from . import VaultLinkConfigEntry
from .const import (
    CONF_BASE_URL,
    CONF_SERVICE_TOKEN,
    CONF_SUMMARY_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_SUMMARY_INTERVAL,
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VaultLinkConfigEntry
) -> dict[str, Any]:
    """Return a strictly redacted diagnostic snapshot."""
    runtime = entry.runtime_data
    main_data = runtime.coordinator.data
    shares_data = runtime.shares_coordinator.data
    return {
        "config_entry": {
            CONF_BASE_URL: REDACTED,
            CONF_SERVICE_TOKEN: REDACTED,
            CONF_VERIFY_SSL: entry.data[CONF_VERIFY_SSL],
            CONF_SUMMARY_INTERVAL: entry.options.get(
                CONF_SUMMARY_INTERVAL, DEFAULT_SUMMARY_INTERVAL
            ),
        },
        "api_version": main_data.live.version,
        "last_successful_update": main_data.last_success.isoformat(),
        "summary": asdict(main_data.summary),
        "shares": {
            "loaded_count": shares_data.loaded_count,
            "truncated": shares_data.truncated,
            "last_successful_update": shares_data.last_success.isoformat(),
        },
    }
