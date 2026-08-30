"""Config and options flows for VaultLink."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    VaultLinkApiClient,
    VaultLinkAuthenticationError,
    VaultLinkAuthorizationError,
    VaultLinkConnectionError,
    VaultLinkError,
)
from .const import (
    CONF_BASE_URL,
    CONF_SERVICE_TOKEN,
    CONF_SUMMARY_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_SUMMARY_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MAX_SUMMARY_INTERVAL,
    MIN_SUMMARY_INTERVAL,
    NAME,
)


class VaultLinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a VaultLink config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create an entry from user input."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                base_url = canonicalize_base_url(user_input[CONF_BASE_URL])
            except ValueError:
                errors[CONF_BASE_URL] = "invalid_url"
            else:
                await self.async_set_unique_id(base_url)
                self._abort_if_unique_id_configured()
                error = await self._async_validate(
                    base_url,
                    user_input[CONF_SERVICE_TOKEN],
                    user_input[CONF_VERIFY_SSL],
                )
                if error is None:
                    return self.async_create_entry(
                        title=_entry_title(base_url),
                        data={
                            CONF_BASE_URL: base_url,
                            CONF_SERVICE_TOKEN: user_input[CONF_SERVICE_TOKEN],
                            CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                        },
                    )
                errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication for an existing entry."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace an invalid or expired service token."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._async_validate(
                entry.data[CONF_BASE_URL],
                user_input[CONF_SERVICE_TOKEN],
                entry.data[CONF_VERIFY_SSL],
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        **entry.data,
                        CONF_SERVICE_TOKEN: user_input[CONF_SERVICE_TOKEN],
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SERVICE_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the base URL or TLS verification setting."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                base_url = canonicalize_base_url(user_input[CONF_BASE_URL])
            except ValueError:
                errors[CONF_BASE_URL] = "invalid_url"
            else:
                if any(
                    other.entry_id != entry.entry_id and other.unique_id == base_url
                    for other in self._async_current_entries()
                ):
                    return self.async_abort(reason="already_configured")
                error = await self._async_validate(
                    base_url,
                    entry.data[CONF_SERVICE_TOKEN],
                    user_input[CONF_VERIFY_SSL],
                )
                if error is None:
                    self.hass.config_entries.async_update_entry(
                        entry, unique_id=base_url
                    )
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            **entry.data,
                            CONF_BASE_URL: base_url,
                            CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                        },
                    )
                errors["base"] = error

        defaults = user_input or {
            CONF_BASE_URL: entry.data[CONF_BASE_URL],
            CONF_VERIFY_SSL: entry.data[CONF_VERIFY_SSL],
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_reconfigure_schema(defaults),
            errors=errors,
        )

    async def _async_validate(
        self, base_url: str, service_token: str, verify_ssl: bool
    ) -> str | None:
        session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
        client = VaultLinkApiClient(session, base_url, service_token)
        try:
            live = await client.async_get_live()
            if not live.ok:
                return "not_live"
            await client.async_get_summary()
        except VaultLinkAuthenticationError:
            return "invalid_auth"
        except VaultLinkAuthorizationError:
            return "insufficient_scope"
        except (VaultLinkConnectionError, VaultLinkError, TimeoutError):
            return "cannot_connect"
        return None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> VaultLinkOptionsFlow:
        """Return the VaultLink options flow."""
        return VaultLinkOptionsFlow(config_entry)


class VaultLinkOptionsFlow(config_entries.OptionsFlow):
    """Manage the summary polling interval."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage VaultLink options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options.get(
            CONF_SUMMARY_INTERVAL, DEFAULT_SUMMARY_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SUMMARY_INTERVAL, default=current
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SUMMARY_INTERVAL,
                            max=MAX_SUMMARY_INTERVAL,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )


def canonicalize_base_url(value: str) -> str:
    """Validate and canonicalize an absolute HTTP(S) root URL."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("invalid URL")
    if "?" in value or "#" in value:
        raise ValueError("query and fragment are not allowed")
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("unsupported scheme")
    if not parsed.netloc or parsed.hostname is None:
        raise ValueError("missing host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("credentials are not allowed")
    if parsed.path not in {"", "/"}:
        raise ValueError("subpaths are not allowed")
    try:
        port = parsed.port
    except ValueError as err:
        raise ValueError("invalid port") from err

    host = parsed.hostname.rstrip(".").lower()
    if not host:
        raise ValueError("missing host")
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as err:
        raise ValueError("invalid host") from err
    if ":" in ascii_host:
        ascii_host = f"[{ascii_host}]"
    default_port = 80 if scheme == "http" else 443
    netloc = ascii_host if port in {None, default_port} else f"{ascii_host}:{port}"
    return urlunsplit((scheme, netloc, "", "", ""))


def _entry_title(base_url: str) -> str:
    return urlsplit(base_url).hostname or NAME


def _user_schema(defaults: Mapping[str, Any] | None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_BASE_URL, default=defaults.get(CONF_BASE_URL, "https://")
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            vol.Required(CONF_SERVICE_TOKEN): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_VERIFY_SSL,
                default=defaults.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            ): BooleanSelector(),
        }
    )


def _reconfigure_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_BASE_URL, default=defaults[CONF_BASE_URL]): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
            vol.Required(
                CONF_VERIFY_SSL, default=defaults[CONF_VERIFY_SSL]
            ): BooleanSelector(),
        }
    )
