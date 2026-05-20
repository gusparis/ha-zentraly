"""Zentraly switch entities."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    DEFAULT_ON_TARGET_TEMP,
    DOMAIN,
    HVAC_MODE_MANUAL,
    HVAC_MODE_OFF,
    MAX_TARGET_TEMP,
    OFF_TARGET_TEMP,
    is_virtual_off,
)
from .coordinator_util import apply_optimistic_state

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zentraly switch entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ZentralyPowerSwitch(
                api=data["api"],
                coordinator=data["coordinator"],
                device_id=data["device_id"],
                device_name=entry.data.get(CONF_DEVICE_NAME, entry.data[CONF_DEVICE_ID]),
            )
        ],
        update_before_add=True,
    )


class ZentralyPowerSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to turn the thermostat on or off like the Zentraly app."""

    _attr_has_entity_name = True
    _attr_translation_key = "power"
    _attr_icon = "mdi:power"

    def __init__(
        self,
        api,
        coordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._device_id = device_id
        self._attr_unique_id = f"zentraly_{device_id}_power"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "name": device_name,
            "manufacturer": "Zentraly",
            "model": "Termostato WiFi",
        }

    @property
    def is_on(self) -> bool:
        state = self.coordinator.data or {}
        return not is_virtual_off(
            state.get("target_temp"),
            state.get("thermostat_mode"),
        )

    async def _revert_after_api_error(self, action: str, error: Exception) -> None:
        _LOGGER.warning(
            "Zentraly %s switch %s failed, reverting UI state: %s",
            self._device_id,
            action,
            error,
        )
        await self.coordinator.async_request_refresh()

    async def _run_in_background(self, action: str, sync_callable) -> None:
        try:
            await self.hass.async_add_executor_job(sync_callable)
        except Exception as exc:
            await self._revert_after_api_error(action, exc)

    async def async_turn_on(self, **kwargs) -> None:
        restore = (self.coordinator.data or {}).get("target_temp")
        target = restore
        if target is None or target <= OFF_TARGET_TEMP or target > MAX_TARGET_TEMP:
            target = DEFAULT_ON_TARGET_TEMP

        apply_optimistic_state(
            self.coordinator,
            target_temp=target,
            thermostat_mode=HVAC_MODE_MANUAL,
        )

        def _turn_on() -> None:
            self._api.set_power(self._device_id, True, restore_target_temp=restore)

        self.hass.async_create_task(
            self._run_in_background("turn_on", _turn_on),
            name=f"zentraly_switch_on_{self._device_id}",
        )

    async def async_turn_off(self, **kwargs) -> None:
        apply_optimistic_state(
            self.coordinator,
            target_temp=OFF_TARGET_TEMP,
            thermostat_mode=HVAC_MODE_OFF,
        )

        def _turn_off() -> None:
            self._api.set_power(self._device_id, False)

        self.hass.async_create_task(
            self._run_in_background("turn_off", _turn_off),
            name=f"zentraly_switch_off_{self._device_id}",
        )
