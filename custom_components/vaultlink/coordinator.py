"""Data update coordinators for VaultLink."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    Health,
    MonitoringShare,
    MonitoringSummary,
    VaultLinkApiClient,
    VaultLinkAuthenticationError,
    VaultLinkError,
)
from .const import SHARES_PAGE_SIZE, SHARES_POLL_LIMIT, SHARES_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VaultLinkData:
    """Data returned by the main coordinator."""

    live: Health
    ready: Health
    summary: MonitoringSummary
    last_success: datetime


@dataclass(frozen=True, slots=True)
class VaultLinkSharesData:
    """Redacted share data returned by the share coordinator."""

    shares: dict[int, MonitoringShare]
    truncated: bool
    last_success: datetime

    @property
    def loaded_count(self) -> int:
        """Return the number of loaded shares."""
        return len(self.shares)


class VaultLinkCoordinator(DataUpdateCoordinator[VaultLinkData]):
    """Coordinate health, readiness and summary polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: VaultLinkApiClient,
        config_entry: ConfigEntry[Any],
        *,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="VaultLink",
            update_interval=update_interval,
        )
        self.client = client

    async def _async_update_data(self) -> VaultLinkData:
        try:
            live = await self.client.async_get_live()
            ready = await self.client.async_get_ready()
            summary = await self.client.async_get_summary()
        except VaultLinkAuthenticationError as err:
            raise ConfigEntryAuthFailed("VaultLink authentication failed") from err
        except VaultLinkError as err:
            raise UpdateFailed("Unable to update VaultLink") from err
        return VaultLinkData(
            live=live,
            ready=ready,
            summary=summary,
            last_success=dt_util.utcnow(),
        )


class VaultLinkSharesCoordinator(DataUpdateCoordinator[VaultLinkSharesData]):
    """Coordinate bounded pagination of redacted shares."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: VaultLinkApiClient,
        config_entry: ConfigEntry[Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="VaultLink shares",
            update_interval=SHARES_UPDATE_INTERVAL,
        )
        self.client = client
        self._truncation_warned = False

    async def _async_update_data(self) -> VaultLinkSharesData:
        shares: dict[int, MonitoringShare] = {}
        cursor: str | None = None
        seen_cursors: set[str] = set()
        truncated = False
        pages_loaded = 0
        max_pages = (SHARES_POLL_LIMIT + SHARES_PAGE_SIZE - 1) // SHARES_PAGE_SIZE

        try:
            while len(shares) < SHARES_POLL_LIMIT and pages_loaded < max_pages:
                remaining = SHARES_POLL_LIMIT - len(shares)
                page = await self.client.async_get_shares_page(
                    limit=min(SHARES_PAGE_SIZE, remaining),
                    cursor=cursor,
                    status="all",
                )
                pages_loaded += 1
                for share in page.shares[:remaining]:
                    shares[share.share_id] = share
                if len(page.shares) > remaining:
                    truncated = True
                if page.next_cursor is None:
                    cursor = None
                    break
                if page.next_cursor in seen_cursors:
                    raise UpdateFailed("VaultLink returned a repeated share cursor")
                seen_cursors.add(page.next_cursor)
                cursor = page.next_cursor

            if cursor is not None and (
                len(shares) >= SHARES_POLL_LIMIT or pages_loaded >= max_pages
            ):
                truncated = True
        except VaultLinkAuthenticationError as err:
            raise ConfigEntryAuthFailed("VaultLink authentication failed") from err
        except UpdateFailed:
            raise
        except VaultLinkError as err:
            raise UpdateFailed("Unable to update VaultLink shares") from err

        if truncated and not self._truncation_warned:
            _LOGGER.warning(
                "VaultLink share polling was truncated at %s shares; aggregate "
                "summary values remain complete",
                SHARES_POLL_LIMIT,
            )
            self._truncation_warned = True

        return VaultLinkSharesData(
            shares=shares,
            truncated=truncated,
            last_success=dt_util.utcnow(),
        )
