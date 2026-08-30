"""Tests for VaultLink diagnostics and secret-leak prevention."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from homeassistant.components.diagnostics import REDACTED
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vaultlink import VaultLinkRuntimeData
from custom_components.vaultlink.api import Health, MonitoringShare
from custom_components.vaultlink.const import (
    CONF_BASE_URL,
    CONF_SERVICE_TOKEN,
    CONF_SUMMARY_INTERVAL,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.vaultlink.coordinator import (
    VaultLinkCoordinator,
    VaultLinkData,
    VaultLinkSharesCoordinator,
    VaultLinkSharesData,
)
from custom_components.vaultlink.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_are_strictly_redacted(hass, summary) -> None:
    """Exclude credentials, full URLs, headers, and individual share data."""
    token = "ULTRA_SECRET_TOKEN_4b729"
    url = "https://private-vaultlink-host.example:8443"
    private_share_value = 987654321
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BASE_URL: url,
            CONF_SERVICE_TOKEN: token,
            CONF_VERIFY_SSL: False,
        },
        options={CONF_SUMMARY_INTERVAL: 120},
    )
    main = VaultLinkCoordinator(
        hass, AsyncMock(), entry, update_interval=timedelta(seconds=120)
    )
    shares = VaultLinkSharesCoordinator(hass, AsyncMock(), entry)
    now = datetime.now(UTC)
    main.async_set_updated_data(
        VaultLinkData(
            live=Health(ok=True, version="1.2.3"),
            ready=Health(ok=True, version="1.2.3"),
            summary=summary,
            last_success=now,
        )
    )
    shares.async_set_updated_data(
        VaultLinkSharesData(
            shares={
                private_share_value: MonitoringShare(
                    share_id=private_share_value,
                    status="available",
                    expires_at=None,
                    download_count=0,
                    uploaded_bytes=0,
                    uploaded_files=0,
                    max_downloads=None,
                    max_upload_bytes=None,
                    max_upload_files=None,
                )
            },
            truncated=True,
            last_success=now,
        )
    )
    entry.runtime_data = VaultLinkRuntimeData(
        client=AsyncMock(), coordinator=main, shares_coordinator=shares
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    serialized = repr(diagnostics)
    assert diagnostics["config_entry"][CONF_BASE_URL] == REDACTED
    assert diagnostics["config_entry"][CONF_SERVICE_TOKEN] == REDACTED
    assert diagnostics["shares"] == {
        "loaded_count": 1,
        "truncated": True,
        "last_successful_update": now.isoformat(),
    }
    for forbidden in (
        token,
        url,
        "private-vaultlink-host",
        "Authorization",
        "Bearer",
        str(private_share_value),
    ):
        assert forbidden not in serialized
