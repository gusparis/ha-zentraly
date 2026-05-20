"""Zentraly switch entities."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN, is_virtual_off


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

    async def async_turn_on(self, **kwargs) -> None:
        restore = (self.coordinator.data or {}).get("target_temp")

        def _turn_on() -> None:
            self._api.set_power(self._device_id, True, restore_target_temp=restore)

        await self.hass.async_add_executor_job(_turn_on)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(
            self._api.set_power, self._device_id, False
        )
        await self.coordinator.async_request_refresh()
