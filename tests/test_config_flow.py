"""Tests for VaultLink config and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vaultlink.api import (
    VaultLinkAuthenticationError,
    VaultLinkAuthorizationError,
)
from custom_components.vaultlink.config_flow import canonicalize_base_url
from custom_components.vaultlink.const import (
    CONF_BASE_URL,
    CONF_SERVICE_TOKEN,
    CONF_SUMMARY_INTERVAL,
    CONF_VERIFY_SSL,
    DOMAIN,
)

INPUT = {
    CONF_BASE_URL: "HTTPS://Example.COM:443/",
    CONF_SERVICE_TOKEN: "test-token",
    CONF_VERIFY_SSL: True,
}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("HTTPS://Example.COM:443/", "https://example.com"),
        ("http://example.com:80", "http://example.com"),
        ("https://example.com:8443", "https://example.com:8443"),
        ("https://[2001:db8::1]/", "https://[2001:db8::1]"),
    ],
)
def test_canonicalize_url(value: str, expected: str) -> None:
    """Canonicalize equivalent root URLs."""
    assert canonicalize_base_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "example.com",
        "ftp://example.com",
        "https://user:pass@example.com",
        "https://example.com/path",
        "https://example.com?query=value",
        "https://example.com#fragment",
        " https://example.com",
    ],
)
def test_reject_invalid_url(value: str) -> None:
    """Reject anything other than an absolute HTTP(S) root URL."""
    with pytest.raises(ValueError, match=r".+"):
        canonicalize_base_url(value)


async def test_user_flow(hass, mock_flow_api) -> None:
    """Create an entry with canonical URL and token only in data."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_BASE_URL: "https://example.com",
        CONF_SERVICE_TOKEN: "test-token",
        CONF_VERIFY_SSL: True,
    }
    assert result["options"] == {}


async def test_duplicate_prevention(hass, mock_flow_api) -> None:
    """Prevent a second entry for an equivalent canonical URL."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="https://example.com",
        data={
            CONF_BASE_URL: "https://example.com",
            CONF_SERVICE_TOKEN: "old",
            CONF_VERIFY_SSL: True,
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=INPUT,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("error", "flow_error"),
    [
        (VaultLinkAuthenticationError("safe"), "invalid_auth"),
        (VaultLinkAuthorizationError("safe"), "insufficient_scope"),
    ],
)
async def test_flow_api_errors(
    hass, summary, error: Exception, flow_error: str
) -> None:
    """Show specific authentication and scope failures."""
    with (
        patch(
            "custom_components.vaultlink.config_flow.VaultLinkApiClient.async_get_live",
            AsyncMock(side_effect=error),
        ),
        patch(
            "custom_components.vaultlink.config_flow.VaultLinkApiClient.async_get_summary",
            AsyncMock(return_value=summary),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=INPUT,
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": flow_error}


async def test_reauth(hass, mock_flow_api) -> None:
    """Replace only the service token and reload the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="https://example.com",
        data={
            CONF_BASE_URL: "https://example.com",
            CONF_SERVICE_TOKEN: "expired",
            CONF_VERIFY_SSL: True,
        },
    )
    entry.add_to_hass(hass)
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload_entry:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SERVICE_TOKEN: "replacement"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_SERVICE_TOKEN] == "replacement"
    reload_entry.assert_awaited_once()


async def test_reconfigure_and_tls_option(hass, mock_flow_api) -> None:
    """Update URL, unique ID, and TLS verification without moving the token."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="https://old.example",
        data={
            CONF_BASE_URL: "https://old.example",
            CONF_SERVICE_TOKEN: "secret",
            CONF_VERIFY_SSL: True,
        },
    )
    entry.add_to_hass(hass)
    with (
        patch.object(hass.config_entries, "async_reload", AsyncMock()),
        patch(
            "custom_components.vaultlink.config_flow.async_get_clientsession"
        ) as get_session,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_BASE_URL: "https://NEW.example/", CONF_VERIFY_SSL: False},
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "https://new.example"
    assert entry.data[CONF_BASE_URL] == "https://new.example"
    assert entry.data[CONF_SERVICE_TOKEN] == "secret"
    assert entry.data[CONF_VERIFY_SSL] is False
    get_session.assert_called_with(hass, verify_ssl=False)


async def test_options_flow(hass) -> None:
    """Store a valid custom summary interval in options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BASE_URL: "https://example.com",
            CONF_SERVICE_TOKEN: "token",
            CONF_VERIFY_SSL: True,
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SUMMARY_INTERVAL: 120}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SUMMARY_INTERVAL] == 120
