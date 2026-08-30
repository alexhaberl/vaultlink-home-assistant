"""Binary sensors for VaultLink."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VaultLinkConfigEntry
from .entity import VaultLinkEntity

READY_DESCRIPTION = BinarySensorEntityDescription(
    key="ready",
    translation_key="ready",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VaultLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the VaultLink readiness sensor."""
    async_add_entities([VaultLinkReadyBinarySensor(entry)])


class VaultLinkReadyBinarySensor(VaultLinkEntity, BinarySensorEntity):
    """Represent VaultLink readiness without failing the coordinator on 503."""

    entity_description = READY_DESCRIPTION

    def __init__(self, entry: VaultLinkConfigEntry) -> None:
        super().__init__(entry, READY_DESCRIPTION.key)

    @property
    def is_on(self) -> bool:
        """Return whether all VaultLink readiness dependencies are available."""
        return self.coordinator.data.ready.ok
