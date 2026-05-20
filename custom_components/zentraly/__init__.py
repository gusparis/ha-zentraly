"""Zentraly integration for Home Assistant."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity  # noqa: F401 – re-exported for climate.py
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZentralyAPI, ZentralyAuthError, ZentralyConnectionError, ZentralyDeviceOfflineError
from .const import (
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PROACTIVE_RESET,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    PROACTIVE_RESET_INTERVAL_HOURS,
    SESSION_KEEPALIVE_MINUTES,
    MIN_RESET_INTERVAL_HOURS,
    OFFLINE_RESET_THRESHOLD_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]
_STORAGE_VERSION = 1

_PROACTIVE_RESET_INTERVAL = timedelta(hours=PROACTIVE_RESET_INTERVAL_HOURS)
_OFFLINE_RESET_THRESHOLD = timedelta(minutes=OFFLINE_RESET_THRESHOLD_MINUTES)
_MIN_RESET_INTERVAL = timedelta(hours=MIN_RESET_INTERVAL_HOURS)


def _scan_interval_seconds(entry: ConfigEntry) -> int:
    raw = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    return max(MIN_SCAN_INTERVAL, min(MAX_SCAN_INTERVAL, int(raw)))


def _proactive_reset_enabled(entry: ConfigEntry) -> bool:
    return bool(entry.options.get(CONF_PROACTIVE_RESET, False))


def _start_account_session(hass: HomeAssistant, email: str, api: ZentralyAPI) -> None:
    domain_data = hass.data.setdefault(DOMAIN, {})
    keepalive_unsubs = domain_data.setdefault("_keepalive_unsubs", {})

    if email in keepalive_unsubs:
        return

    async def _session_keepalive(_now: datetime) -> None:
        try:
            await hass.async_add_executor_job(api.login)
            _LOGGER.debug("Zentraly session keepalive OK for %s", email)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Zentraly session keepalive failed for %s: %s", email, exc)

    keepalive_unsubs[email] = async_track_time_interval(
        hass,
        _session_keepalive,
        timedelta(minutes=SESSION_KEEPALIVE_MINUTES),
    )


def _release_account_ref(hass: HomeAssistant, email: str) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    refcounts = domain_data.get("_account_refcounts", {})
    keepalive_unsubs = domain_data.get("_keepalive_unsubs", {})
    shared_apis = domain_data.get("_shared_apis", {})

    if email not in refcounts:
        return

    refcounts[email] -= 1
    if refcounts[email] > 0:
        return

    if unsub := keepalive_unsubs.pop(email, None):
        unsub()
    shared_apis.pop(email, None)
    refcounts.pop(email, None)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Zentraly from a config entry."""
    email = entry.data[CONF_EMAIL]
    device_id = entry.data[CONF_DEVICE_ID]

    domain_data = hass.data.setdefault(DOMAIN, {})
    shared_apis = domain_data.setdefault("_shared_apis", {})
    refcounts = domain_data.setdefault("_account_refcounts", {})

    if email not in shared_apis:
        shared_apis[email] = ZentralyAPI(
            email=email,
            password=entry.data[CONF_PASSWORD],
        )
        refcounts[email] = 0
        _start_account_session(hass, email, shared_apis[email])

    refcounts[email] = refcounts.get(email, 0) + 1
    api = shared_apis[email]

    store = Store(hass, _STORAGE_VERSION, f"{DOMAIN}_{device_id}_state")
    stored = await store.async_load() or {}
    _last_good_state: dict = dict(stored)

    _offline_since: datetime | None = None
    _last_reset_at: datetime = datetime.now()
    proactive_reset = _proactive_reset_enabled(entry)

    async def async_update_data() -> dict:
        nonlocal _last_good_state, _offline_since, _last_reset_at
        try:
            state = await hass.async_add_executor_job(api.get_state, device_id)
            now = datetime.now()

            if _offline_since is not None:
                _LOGGER.warning(
                    "Zentraly %s: back online after %s",
                    device_id,
                    now - _offline_since,
                )
                _offline_since = None

            _last_good_state = {**state, "is_connected": True, "offline_since": None}
            await store.async_save(state)

            if proactive_reset:
                since_last_reset = now - _last_reset_at
                if since_last_reset >= _PROACTIVE_RESET_INTERVAL:
                    _LOGGER.warning(
                        "Zentraly %s: proactive reset after %s (opt-in; prevents 12 h SAS token expiry)",
                        device_id,
                        since_last_reset,
                    )
                    try:
                        accepted = await hass.async_add_executor_job(
                            api.reset_device, device_id
                        )
                        _last_reset_at = now
                        _LOGGER.warning(
                            "Zentraly %s: proactive reset %s",
                            device_id,
                            "accepted" if accepted else "not confirmed",
                        )
                    except Exception as reset_exc:  # noqa: BLE001
                        _LOGGER.warning(
                            "Zentraly %s: proactive reset failed: %s",
                            device_id,
                            reset_exc,
                        )

            return _last_good_state

        except ZentralyAuthError as exc:
            _LOGGER.warning(
                "Zentraly %s: auth error (%s) — will re-login next cycle",
                device_id,
                exc,
            )
            api.invalidate_token()
            if _last_good_state:
                return {**_last_good_state, "is_connected": None}
            raise UpdateFailed(str(exc)) from exc

        except ZentralyDeviceOfflineError as exc:
            now = datetime.now()

            if _offline_since is None:
                _offline_since = now
                _LOGGER.warning(
                    "Zentraly %s: device offline (not connected to Azure IoT Hub). "
                    "If this persists ~12 h, enable proactive reset in integration options "
                    "or use the restart button.",
                    device_id,
                )

            offline_duration = now - _offline_since
            since_last_reset = now - _last_reset_at
            if (
                offline_duration >= _OFFLINE_RESET_THRESHOLD
                and since_last_reset >= _MIN_RESET_INTERVAL
            ):
                _LOGGER.warning(
                    "Zentraly %s: offline for %s — attempting reactive reset",
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
                        "accepted" if accepted else "not confirmed — manual restart may be needed",
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
        update_interval=timedelta(seconds=_scan_interval_seconds(entry)),
    )

    try:
        await hass.async_add_executor_job(api.login)
    except ZentralyAuthError as exc:
        raise ConfigEntryAuthFailed(str(exc)) from exc
    except ZentralyConnectionError as exc:
        raise ConfigEntryNotReady(str(exc)) from exc

    await coordinator.async_config_entry_first_refresh()

    domain_data[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "device_id": device_id,
        "email": email,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data and (email := data.get("email")):
            _release_account_ref(hass, email)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
