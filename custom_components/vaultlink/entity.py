"""Shared VaultLink entity classes."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VaultLinkConfigEntry
from .const import CONF_BASE_URL, DOMAIN, NAME
from .coordinator import VaultLinkCoordinator, VaultLinkSharesCoordinator


class VaultLinkEntity(CoordinatorEntity[VaultLinkCoordinator]):
    """Base class for main VaultLink entities."""

    _attr_has_entity_name = True

    def __init__(self, entry: VaultLinkConfigEntry, key: str) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return information for the VaultLink service device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=NAME,
            manufacturer=NAME,
            model="VaultLink",
            sw_version=self.coordinator.data.live.version,
            configuration_url=self._entry.data[CONF_BASE_URL],
        )


class VaultLinkShareEntity(CoordinatorEntity[VaultLinkSharesCoordinator]):
    """Base class for entities belonging to one VaultLink share."""

    _attr_has_entity_name = True

    def __init__(self, entry: VaultLinkConfigEntry, share_id: int, key: str) -> None:
        super().__init__(entry.runtime_data.shares_coordinator)
        self._entry = entry
        self._share_id = share_id
        self._attr_unique_id = f"{entry.entry_id}_share_{share_id}_{key}"

    @property
    def available(self) -> bool:
        """Return false when a formerly known share disappears."""
        return super().available and self._share_id in self.coordinator.data.shares

    @property
    def device_info(self) -> DeviceInfo:
        """Return information for the redacted share device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_share_{self._share_id}")},
            name=f"VaultLink Share #{self._share_id}",
            manufacturer=NAME,
            model="VaultLink Share",
            via_device=(DOMAIN, self._entry.entry_id),
        )
