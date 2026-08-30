"""Shared pytest fixtures for VaultLink."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.vaultlink.api import Health, MonitoringSummary

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable loading integrations from custom_components."""
    return


@pytest.fixture
def summary() -> MonitoringSummary:
    """Return representative aggregate monitoring data."""
    return MonitoringSummary(
        shares_total=6,
        shares_available=2,
        shares_protected=1,
        shares_inactive=1,
        shares_expired=1,
        shares_download_limit_reached=1,
        monthly_downloads=21,
        monthly_zip_downloads=3,
        monthly_previews=8,
        storage_free_bytes=1024,
        storage_total_bytes=4096,
    )


@pytest.fixture
def mock_flow_api(summary: MonitoringSummary) -> Generator[None]:
    """Mock successful config-flow validation calls."""
    with (
        patch(
            "custom_components.vaultlink.config_flow.VaultLinkApiClient.async_get_live",
            AsyncMock(return_value=Health(ok=True, version="1.2.3")),
        ),
        patch(
            "custom_components.vaultlink.config_flow.VaultLinkApiClient.async_get_summary",
            AsyncMock(return_value=summary),
        ),
    ):
        yield
