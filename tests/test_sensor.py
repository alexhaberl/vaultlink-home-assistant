"""Tests for VaultLink entities and dynamic shares."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vaultlink import VaultLinkRuntimeData
from custom_components.vaultlink.api import Health, MonitoringShare, MonitoringSummary
from custom_components.vaultlink.binary_sensor import VaultLinkReadyBinarySensor
from custom_components.vaultlink.const import (
    CONF_BASE_URL,
    CONF_SERVICE_TOKEN,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.vaultlink.coordinator import (
    VaultLinkCoordinator,
    VaultLinkData,
    VaultLinkSharesCoordinator,
    VaultLinkSharesData,
)
from custom_components.vaultlink.sensor import (
    SUMMARY_DESCRIPTIONS,
    VaultLinkSummarySensor,
    async_setup_entry,
)


def make_share(share_id: int, *, expires: bool = False) -> MonitoringShare:
    """Return one redacted share."""
    return MonitoringShare(
        share_id=share_id,
        status="available",
        expires_at=datetime(2027, 1, 1, tzinfo=UTC) if expires else None,
        download_count=2,
        uploaded_bytes=10,
        uploaded_files=1,
        max_downloads=5,
        max_upload_bytes=20,
        max_upload_files=3,
    )


def setup_runtime(hass, summary: MonitoringSummary):
    """Create an entry with populated real coordinators and no network I/O."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BASE_URL: "https://secret-host.example",
            CONF_SERVICE_TOKEN: "secret-token",
            CONF_VERIFY_SSL: True,
        },
        unique_id="https://secret-host.example",
    )
    main = VaultLinkCoordinator(
        hass, AsyncMock(), entry, update_interval=timedelta(seconds=60)
    )
    shares = VaultLinkSharesCoordinator(hass, AsyncMock(), entry)
    now = datetime.now(UTC)
    main.async_set_updated_data(
        VaultLinkData(
            live=Health(ok=True, version="1.2.3"),
            ready=Health(ok=False, version="1.2.3"),
            summary=summary,
            last_success=now,
        )
    )
    shares.async_set_updated_data(
        VaultLinkSharesData(
            shares={1: make_share(1)}, truncated=False, last_success=now
        )
    )
    entry.runtime_data = VaultLinkRuntimeData(
        client=AsyncMock(), coordinator=main, shares_coordinator=shares
    )
    return entry, main, shares


async def test_main_entities(hass, summary) -> None:
    """Expose readiness, summary values, device metadata, and stable IDs."""
    entry, main, _shares = setup_runtime(hass, summary)
    ready = VaultLinkReadyBinarySensor(entry)
    total = VaultLinkSummarySensor(entry, SUMMARY_DESCRIPTIONS[0])
    assert ready.is_on is False
    assert ready.device_info["sw_version"] == "1.2.3"
    assert ready.device_info["configuration_url"] == "https://secret-host.example"
    assert total.native_value == 6
    assert total.unique_id == f"{entry.entry_id}_shares_total"
    assert total.available is True
    main.last_update_success = False
    assert total.available is False


async def test_dynamic_and_disappearing_shares(hass, summary) -> None:
    """Add newly seen share entities and keep missing shares unavailable."""
    entry, _main, coordinator = setup_runtime(hass, summary)
    added: list[object] = []

    def add_entities(entities) -> None:
        added.extend(entities)

    await async_setup_entry(hass, entry, add_entities)
    initial = len(added)
    assert initial == len(SUMMARY_DESCRIPTIONS) + 7
    first_status = next(
        entity for entity in added if entity.entity_description.key == "status"
    )

    coordinator.async_set_updated_data(
        VaultLinkSharesData(
            shares={1: make_share(1, expires=True), 2: make_share(2, expires=True)},
            truncated=False,
            last_success=datetime.now(UTC),
        )
    )
    await hass.async_block_till_done()
    assert len(added) == initial + 9  # expiry for #1 and eight entities for #2

    coordinator.async_set_updated_data(
        VaultLinkSharesData(
            shares={2: make_share(2)},
            truncated=False,
            last_success=datetime.now(UTC),
        )
    )
    assert first_status.available is False
    assert first_status.native_value is None
    await coordinator.async_shutdown()


def test_entity_properties_do_not_call_api(hass, summary) -> None:
    """Read entity state entirely from coordinator memory."""
    entry, _main, shares = setup_runtime(hass, summary)
    api = entry.runtime_data.client
    from custom_components.vaultlink.sensor import (
        SHARE_STATUS_DESCRIPTION,
        VaultLinkShareSensor,
    )

    status_entity = VaultLinkShareSensor(entry, 1, SHARE_STATUS_DESCRIPTION)
    assert status_entity.native_value == "available"
    assert status_entity.available is True
    assert status_entity.device_info["via_device"] == (DOMAIN, entry.entry_id)
    assert not api.mock_calls
    assert not shares.client.mock_calls
