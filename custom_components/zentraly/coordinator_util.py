"""Helpers for optimistic coordinator updates."""
from __future__ import annotations

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator


def apply_optimistic_state(
    coordinator: DataUpdateCoordinator,
    **fields: float | int | bool | str | None,
) -> None:
    data = dict(coordinator.data or {})
    data.update(fields)
    coordinator.async_set_updated_data(data)
