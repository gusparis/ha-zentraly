"""Config flow for Zentraly integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .api import ZentralyAPI, ZentralyAuthError, ZentralyConnectionError
from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_IDS,
    CONF_DEVICE_NAME,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PROACTIVE_RESET,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_and_get_devices(hass: HomeAssistant, data: dict) -> list[dict]:
    """Validate credentials and return list of devices."""
    api = ZentralyAPI(data[CONF_EMAIL], data[CONF_PASSWORD])
    try:
        await hass.async_add_executor_job(api.login)
        devices = await hass.async_add_executor_job(api.get_devices)
    except ZentralyAuthError as exc:
        raise InvalidAuth(str(exc)) from exc
    except ZentralyConnectionError as exc:
        raise CannotConnect(str(exc)) from exc
    return devices


class ZentralyOptionsFlow(config_entries.OptionsFlow):
    """Handle Zentraly integration options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage polling and optional proactive device reset."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        entry = self.config_entry
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
                    vol.Optional(
                        CONF_PROACTIVE_RESET,
                        default=entry.options.get(CONF_PROACTIVE_RESET, False),
                    ): bool,
                }
            ),
        )


class ZentralyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Zentraly."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ZentralyOptionsFlow:
        """Return the options flow handler."""
        return ZentralyOptionsFlow()

    def __init__(self) -> None:
        self._devices: list[dict] = []
        self._credentials: dict = {}

    def _configured_device_ids(self) -> set[str]:
        return {
            entry.data[CONF_DEVICE_ID]
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if CONF_DEVICE_ID in entry.data
        }

    def _available_devices(self) -> list[dict]:
        configured = self._configured_device_ids()
        return [d for d in self._devices if d["device_id"] not in configured]

    def _entry_data(self, device: dict) -> dict[str, Any]:
        return {
            **self._credentials,
            CONF_DEVICE_ID: device["device_id"],
            CONF_DEVICE_NAME: device["name"],
        }

    def _device_selector_schema(self, devices: list[dict]) -> vol.Schema:
        device_ids = [d["device_id"] for d in devices]
        return vol.Schema(
            {
                vol.Required(
                    CONF_DEVICE_IDS,
                    default=device_ids,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=d["device_id"],
                                label=d["name"],
                            )
                            for d in devices
                        ],
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step: ask for credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                self._devices = await validate_and_get_devices(self.hass, user_input)
                self._credentials = user_input
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception during Zentraly config flow")
                errors["base"] = "unknown"
            else:
                available = self._available_devices()
                if not available:
                    return self.async_abort(reason="already_configured")
                if len(available) == 1:
                    device = available[0]
                    await self.async_set_unique_id(device["device_id"])
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=device["name"],
                        data=self._entry_data(device),
                    )
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user select one or more thermostats to add."""
        available = self._available_devices()
        if not available:
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            selected_ids = user_input.get(CONF_DEVICE_IDS) or []
            if isinstance(selected_ids, str):
                selected_ids = [selected_ids]

            if not selected_ids:
                return self.async_show_form(
                    step_id="device",
                    data_schema=self._device_selector_schema(available),
                    errors={"base": "no_devices_selected"},
                )

            devices_by_id = {d["device_id"]: d for d in available}
            to_add = [devices_by_id[device_id] for device_id in selected_ids if device_id in devices_by_id]

            if not to_add:
                return self.async_show_form(
                    step_id="device",
                    data_schema=self._device_selector_schema(available),
                    errors={"base": "no_devices_selected"},
                )

            for device in to_add[:-1]:
                entry = config_entries.ConfigEntry(
                    version=self.VERSION,
                    domain=DOMAIN,
                    title=device["name"],
                    data=self._entry_data(device),
                    source=config_entries.SOURCE_USER,
                    unique_id=device["device_id"],
                    options={},
                )
                self.hass.config_entries.async_add(entry)

            last_device = to_add[-1]
            await self.async_set_unique_id(last_device["device_id"])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=last_device["name"],
                data=self._entry_data(last_device),
            )

        return self.async_show_form(
            step_id="device",
            data_schema=self._device_selector_schema(available),
        )

    async def async_step_reauth(self, entry_data: dict) -> FlowResult:
        """Handle re-authentication when credentials are invalid."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm re-authentication with new credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_and_get_devices(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "unknown"
            else:
                entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, **user_input},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
