"""Zentraly integration for Home Assistant."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.restore_state import RestoreEntity  # noqa: F401 – re-exported for climate.py
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZentralyAPI, ZentralyAuthError, ZentralyConnectionError, ZentralyDeviceOfflineError
from .const import CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.BUTTON]
_STORAGE_VERSION = 1

# Proactive reset: send a reset command while the device is still ONLINE,
# before the SAS token expires. Reset every 1 h for maximum reliability.
_PROACTIVE_RESET_INTERVAL = timedelta(hours=1)

# Reactive watchdog: last resort when the device already went offline.
# Only works if the device can still receive commands (e.g. brief glitch, not
# full SAS-token expiry). Don't spam resets if the device is truly unreachable.
_OFFLINE_RESET_THRESHOLD = timedelta(minutes=15)
_MIN_RESET_INTERVAL = timedelta(hours=2)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Zentraly from a config entry."""
    api = ZentralyAPI(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
    )
    device_id = entry.data[CONF_DEVICE_ID]

    # Persist last known state across restarts
    store = Store(hass, _STORAGE_VERSION, f"{DOMAIN}_{device_id}_state")
    stored = await store.async_load() or {}
    _last_good_state: dict = dict(stored)

    # In-memory timers. _last_reset_at starts at "10 hours ago" so the first
    # proactive reset fires within the first polling cycle after HA restarts,
    # regardless of how long the device has already been online.
    _offline_since: datetime | None = None
    _last_reset_at: datetime = datetime.now() - _PROACTIVE_RESET_INTERVAL

    async def async_update_data() -> dict:
        nonlocal _last_good_state, _offline_since, _last_reset_at
        try:
            state = await hass.async_add_executor_job(api.get_state, device_id)
            now = datetime.now()

            # ----------------------------------------------------------------
            # Device is online — clear offline marker and log recovery
            # ----------------------------------------------------------------
            if _offline_since is not None:
                _LOGGER.warning(
                    "Zentraly %s: back online after %s",
                    device_id,
                    now - _offline_since,
                )
                _offline_since = None

            _last_good_state = {**state, "is_connected": True, "offline_since": None}
            await store.async_save(state)
            return _last_good_state

        except ZentralyAuthError as exc:
            # Transient auth failure (e.g. server-side session invalidation or
            # rate-limit). Invalidate the token so the next cycle re-logins,
            # and return the last known state rather than blocking the coordinator.
            _LOGGER.warning("Zentraly %s: auth error (%s) — will re-login next cycle", device_id, exc)
            api.invalidate_token()
            if _last_good_state:
                return {**_last_good_state, "is_connected": None}
            raise UpdateFailed(str(exc)) from exc

        except ZentralyDeviceOfflineError as exc:
            now = datetime.now()

            if _offline_since is None:
                _offline_since = now
                _LOGGER.warning(
                    "Zentraly %s: device offline (Azure IoT Hub disconnected). "
                    "Root cause: 12-hour SAS token expired, firmware did not renew it. "
                    "The proactive reset (every 11 h) should prevent this in future cycles.",
                    device_id,
                )

            # ----------------------------------------------------------------
            # Reactive watchdog — best-effort only.
            # If the SAS token has truly expired, the device cannot connect to
            # IoT Hub to receive this command. It may still work for brief
            # glitches where the device is temporarily unreachable but not
            # fully offline (e.g. WiFi interruption, heavy load).
            # ----------------------------------------------------------------
            offline_duration = now - _offline_since
            since_last_reset = now - _last_reset_at
            if (
                offline_duration >= _OFFLINE_RESET_THRESHOLD
                and since_last_reset >= _MIN_RESET_INTERVAL
            ):
                _LOGGER.warning(
                    "Zentraly %s: offline for %s — attempting reactive reset "
                    "(may not work if SAS token has expired; a power cycle may be needed)",
                    device_id,
                    offline_duration,
                )
                try:
                    accepted = await hass.async_add_executor_job(
                        api.reset_device, device_id
                    )
                    _last_reset_at = now
                    _LOGGER.warning(
                        "Zentraly %s: reactive reset %s",
                        device_id,
                        "accepted" if accepted else "not confirmed — manual restart required",
                    )
                except Exception as reset_exc:  # noqa: BLE001
                    _LOGGER.debug(
                        "Zentraly %s: reactive reset failed: %s", device_id, reset_exc
                    )

            if _last_good_state:
                return {
                    **_last_good_state,
                    "is_connected": False,
                    "offline_since": _offline_since.isoformat(),
                }
            raise UpdateFailed(str(exc)) from exc

        except ZentralyConnectionError as exc:
            _LOGGER.warning(
                "Zentraly %s: thermostat unreachable (%s), using persisted state",
                device_id,
                exc,
            )
            if _last_good_state:
                return {**_last_good_state, "is_connected": None}
            raise UpdateFailed(str(exc)) from exc

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"zentraly_{device_id}",
        update_method=async_update_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    try:
        await hass.async_add_executor_job(api.login)
    except ZentralyAuthError as exc:
        raise ConfigEntryAuthFailed(str(exc)) from exc
    except ZentralyConnectionError as exc:
        raise ConfigEntryNotReady(str(exc)) from exc

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "device_id": device_id,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
