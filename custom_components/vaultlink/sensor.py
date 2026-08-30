"""Sensors for VaultLink aggregate and redacted share data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VaultLinkConfigEntry
from .api import MonitoringShare, MonitoringSummary
from .const import SHARE_STATUSES
from .entity import VaultLinkEntity, VaultLinkShareEntity

type ShareSensorValue = int | str | datetime | None


@dataclass(frozen=True, kw_only=True)
class VaultLinkSummaryDescription(SensorEntityDescription):
    """Describe a VaultLink summary sensor."""

    value_fn: Callable[[MonitoringSummary], int]


SUMMARY_DESCRIPTIONS = (
    VaultLinkSummaryDescription(
        key="shares_total",
        translation_key="shares_total",
        native_unit_of_measurement="shares",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.shares_total,
    ),
    VaultLinkSummaryDescription(
        key="shares_available",
        translation_key="shares_available",
        native_unit_of_measurement="shares",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.shares_available,
    ),
    VaultLinkSummaryDescription(
        key="shares_protected",
        translation_key="shares_protected",
        native_unit_of_measurement="shares",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.shares_protected,
    ),
    VaultLinkSummaryDescription(
        key="shares_inactive",
        translation_key="shares_inactive",
        native_unit_of_measurement="shares",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.shares_inactive,
    ),
    VaultLinkSummaryDescription(
        key="shares_expired",
        translation_key="shares_expired",
        native_unit_of_measurement="shares",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.shares_expired,
    ),
    VaultLinkSummaryDescription(
        key="shares_download_limit_reached",
        translation_key="shares_download_limit_reached",
        native_unit_of_measurement="shares",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.shares_download_limit_reached,
    ),
    VaultLinkSummaryDescription(
        key="monthly_downloads",
        translation_key="monthly_downloads",
        native_unit_of_measurement="downloads",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.monthly_downloads,
    ),
    VaultLinkSummaryDescription(
        key="monthly_zip_downloads",
        translation_key="monthly_zip_downloads",
        native_unit_of_measurement="downloads",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.monthly_zip_downloads,
    ),
    VaultLinkSummaryDescription(
        key="monthly_previews",
        translation_key="monthly_previews",
        native_unit_of_measurement="previews",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.monthly_previews,
    ),
    VaultLinkSummaryDescription(
        key="storage_free_bytes",
        translation_key="storage_free_bytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.storage_free_bytes,
    ),
    VaultLinkSummaryDescription(
        key="storage_total_bytes",
        translation_key="storage_total_bytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.storage_total_bytes,
    ),
)


@dataclass(frozen=True, kw_only=True)
class VaultLinkShareDescription(SensorEntityDescription):
    """Describe a redacted share sensor."""

    value_fn: Callable[[MonitoringShare], ShareSensorValue]


SHARE_STATUS_DESCRIPTION = VaultLinkShareDescription(
    key="status",
    translation_key="share_status",
    device_class=SensorDeviceClass.ENUM,
    options=list(SHARE_STATUSES),
    value_fn=lambda share: share.status,
)
SHARE_EXPIRES_DESCRIPTION = VaultLinkShareDescription(
    key="expires_at",
    translation_key="share_expires_at",
    device_class=SensorDeviceClass.TIMESTAMP,
    value_fn=lambda share: share.expires_at,
)
SHARE_DIAGNOSTIC_DESCRIPTIONS = (
    VaultLinkShareDescription(
        key="download_count",
        translation_key="share_download_count",
        native_unit_of_measurement="downloads",
        state_class=SensorStateClass.TOTAL,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda share: share.download_count,
    ),
    VaultLinkShareDescription(
        key="uploaded_bytes",
        translation_key="share_uploaded_bytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda share: share.uploaded_bytes,
    ),
    VaultLinkShareDescription(
        key="uploaded_files",
        translation_key="share_uploaded_files",
        native_unit_of_measurement="files",
        state_class=SensorStateClass.TOTAL,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda share: share.uploaded_files,
    ),
    VaultLinkShareDescription(
        key="max_downloads",
        translation_key="share_max_downloads",
        native_unit_of_measurement="downloads",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda share: share.max_downloads,
    ),
    VaultLinkShareDescription(
        key="max_upload_bytes",
        translation_key="share_max_upload_bytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda share: share.max_upload_bytes,
    ),
    VaultLinkShareDescription(
        key="max_upload_files",
        translation_key="share_max_upload_files",
        native_unit_of_measurement="files",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda share: share.max_upload_files,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VaultLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up VaultLink sensors and subscribe for newly observed shares."""
    coordinator = entry.runtime_data.shares_coordinator
    known: set[tuple[int, str]] = set()

    @callback
    def async_add_new_share_entities() -> None:
        entities: list[SensorEntity] = []
        for share_id, share in coordinator.data.shares.items():
            descriptions = [SHARE_STATUS_DESCRIPTION, *SHARE_DIAGNOSTIC_DESCRIPTIONS]
            if share.expires_at is not None:
                descriptions.append(SHARE_EXPIRES_DESCRIPTION)
            for description in descriptions:
                identity = (share_id, description.key)
                if identity in known:
                    continue
                known.add(identity)
                entities.append(VaultLinkShareSensor(entry, share_id, description))
        if entities:
            async_add_entities(entities)

    async_add_entities(
        [
            VaultLinkSummarySensor(entry, description)
            for description in SUMMARY_DESCRIPTIONS
        ]
    )
    async_add_new_share_entities()
    entry.async_on_unload(coordinator.async_add_listener(async_add_new_share_entities))


class VaultLinkSummarySensor(VaultLinkEntity, SensorEntity):
    """Represent one aggregate monitoring value."""

    entity_description: VaultLinkSummaryDescription

    def __init__(
        self,
        entry: VaultLinkConfigEntry,
        description: VaultLinkSummaryDescription,
    ) -> None:
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int:
        """Return the latest aggregate value."""
        return self.entity_description.value_fn(self.coordinator.data.summary)


class VaultLinkShareSensor(VaultLinkShareEntity, SensorEntity):
    """Represent one non-secret field of a redacted share."""

    entity_description: VaultLinkShareDescription

    def __init__(
        self,
        entry: VaultLinkConfigEntry,
        share_id: int,
        description: VaultLinkShareDescription,
    ) -> None:
        super().__init__(entry, share_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | str | datetime | None:
        """Return the latest value without performing I/O."""
        share = self.coordinator.data.shares.get(self._share_id)
        if share is None:
            return None
        return self.entity_description.value_fn(share)
