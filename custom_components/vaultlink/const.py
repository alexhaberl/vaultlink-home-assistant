"""Constants for the VaultLink integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "vaultlink"
NAME: Final = "VaultLink"

CONF_BASE_URL: Final = "base_url"
CONF_SERVICE_TOKEN: Final = "service_token"  # noqa: S105
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_SUMMARY_INTERVAL: Final = "summary_interval"

DEFAULT_VERIFY_SSL: Final = True
DEFAULT_SUMMARY_INTERVAL: Final = 60
MIN_SUMMARY_INTERVAL: Final = 30
MAX_SUMMARY_INTERVAL: Final = 3600
SHARES_UPDATE_INTERVAL: Final = timedelta(minutes=5)
SHARES_PAGE_SIZE: Final = 200
SHARES_POLL_LIMIT: Final = 1000
REQUEST_TIMEOUT: Final = 10

PLATFORMS: Final = (Platform.BINARY_SENSOR, Platform.SENSOR)

SHARE_STATUSES: Final = (
    "available",
    "inactive",
    "expired",
    "download_limit_reached",
)
