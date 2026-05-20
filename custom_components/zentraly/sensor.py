"""Zentraly sensor entities."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zentraly sensor entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ZentralyHumiditySensor(
                coordinator=data["coordinator"],
                device_id=data["device_id"],
                device_name=entry.data.get(CONF_DEVICE_NAME, entry.data[CONF_DEVICE_ID]),
            )
        ],
        update_before_add=True,
    )


class ZentralyHumiditySensor(CoordinatorEntity, SensorEntity):
    """Relative humidity reported by the thermostat."""

    _attr_has_entity_name = True
    _attr_translation_key = "humidity"
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"zentraly_{device_id}_humidity"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "name": device_name,
            "manufacturer": "Zentraly",
            "model": "Termostato WiFi",
        }

    @property
    def native_value(self) -> int | float | None:
        return (self.coordinator.data or {}).get("humidity")
