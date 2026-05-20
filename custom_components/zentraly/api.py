"""Zentraly cloud API client."""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta
from typing import Optional

from .const import (
    COMMAND_TIMEOUT,
    DEFAULT_ON_TARGET_TEMP,
    HVAC_MODE_MANUAL,
    HVAC_MODE_OFF,
    IOT_COMMAND_URL,
    JWT_REFRESH_MINUTES,
    LOGIN_URL,
    MAX_TARGET_TEMP,
    MIN_TARGET_TEMP,
    OFF_COMMAND_TEMP,
    OFF_TARGET_TEMP,
    TEMP_SCALE,
    ZENTRALY_ACCEPT_LANGUAGE,
    ZENTRALY_APP_VERSION,
    ZENTRALY_FB_TOKEN_PLACEHOLDER,
    ZENTRALY_MOBILE_OS,
    ZENTRALY_USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


def _device_guid(email: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"zentraly-home-assistant:{email}"))


def _make_firebase_header(email: str) -> str:
    payload = {
        "ivstrUserFBToken": ZENTRALY_FB_TOKEN_PLACEHOLDER,
        "ivstrUserGuid": _device_guid(email),
        "ivstrUserZtVersion": ZENTRALY_APP_VERSION,
        "ivnroUserMobileOS": ZENTRALY_MOBILE_OS,
        "ivstrUserMobileTrade": "Apple",
        "ivstrUserMobileModel": "iOS",
        "ivstrUserMobileOSVersion": "26.3.1",
        "ivstrUserLanguage": "en",
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _request(url: str, *, method: str = "GET", headers: dict, body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="ignore")[:200]
        if exc.code == 401:
            raise ZentralyAuthError(f"HTTP {exc.code}: {body_text}") from exc
        raise ZentralyConnectionError(f"HTTP {exc.code}: {body_text}") from exc
    except Exception as exc:
        raise ZentralyConnectionError(str(exc)) from exc


class ZentralyAuthError(Exception):
    """Authentication or authorization error."""


class ZentralyConnectionError(Exception):
    """Network or connection error."""


class ZentralyDeviceOfflineError(ZentralyConnectionError):
    """Device is offline in the cloud (numStatus=6).

    Distinct from generic connection errors so the coordinator can apply
    specific watchdog logic (auto-reset) without reacting the same way to
    transient network blips.
    """


class ZentralyAPI:
    """Client for the Zentraly REST API."""

    def __init__(self, email: str, password: str) -> None:
        self._email = email
        self._password = password
        self._token: Optional[str] = None
        self._token_expires: datetime = datetime.min
        self._firebase_header = _make_firebase_header(email)
        self._login_data: dict = {}

    def update_credentials(self, email: str, password: str) -> None:
        if self._email == email and self._password == password:
            return
        self._email = email
        self._password = password
        self._firebase_header = _make_firebase_header(email)
        self.invalidate_token()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _common_headers(self, *, auth_token: str | None = None) -> dict:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Language": ZENTRALY_ACCEPT_LANGUAGE,
            "Connection": "keep-alive",
            "firebase": self._firebase_header,
            "Authorization": auth_token or f"ztv2Auth{self._email}:{self._password}",
            "User-Agent": ZENTRALY_USER_AGENT,
        }

    def login(self) -> dict:
        """Authenticate with stored email/password and cache JWT."""
        _LOGGER.debug("Logging in to Zentraly as %s", self._email)
        self._token = None
        result = self._request_with_relogin(
            LOGIN_URL,
            method="GET",
            body=None,
            use_password_auth=True,
        )
        if result.get("numStatus") != 0:
            raise ZentralyAuthError(f"Login failed: numStatus={result.get('numStatus')}")

        io_data = result.get("ioData", {})
        token_raw = io_data.get("ivstrToken")
        if not token_raw:
            _LOGGER.error("Could not find ivstrToken in login response: %s", json.dumps(result)[:500])
            raise ZentralyAuthError("Login succeeded but token not found in response")

        self._token = token_raw
        self._login_data = io_data
        self._token_expires = datetime.now() + timedelta(minutes=JWT_REFRESH_MINUTES)
        return result

    def _request_with_relogin(
        self,
        url: str,
        *,
        method: str = "GET",
        body: Optional[dict] = None,
        use_password_auth: bool = False,
    ) -> dict:
        try:
            return _request(
                url,
                method=method,
                headers=self._common_headers(
                    auth_token=None if use_password_auth else self._auth_token_header()
                ),
                body=body,
            )
        except ZentralyAuthError:
            if use_password_auth:
                raise
            _LOGGER.debug("Zentraly token rejected for %s, re-logging in", self._email)
            self.login()
            return _request(
                url,
                method=method,
                headers=self._common_headers(auth_token=self._auth_token_header()),
                body=body,
            )

    def _iot_run(self, device_id: str, data_cmd: dict) -> dict:
        self.ensure_authenticated()
        body = {
            "deviceId": device_id,
            "timeOut": COMMAND_TIMEOUT,
            "data": data_cmd,
        }
        result = self._request_with_relogin(
            IOT_COMMAND_URL,
            method="POST",
            body=body,
        )
        num_status = result.get("numStatus")
        if num_status in (1, 2):
            _LOGGER.debug(
                "Zentraly token numStatus=%s for %s, re-logging in and retrying",
                num_status,
                device_id,
            )
            self.login()
            result = _request(
                IOT_COMMAND_URL,
                method="POST",
                headers=self._common_headers(auth_token=self._auth_token_header()),
                body=body,
            )
            num_status = result.get("numStatus")
            if num_status in (1, 2):
                raise ZentralyConnectionError(
                    f"IOT command token rejected after re-login (numStatus={num_status})"
                )
        return result

    def _auth_token_header(self) -> str:
        if self._token:
            return f"ztv2Token{self._token}"
        return f"ztv2Auth{self._email}:{self._password}"

    def invalidate_token(self) -> None:
        """Force re-login on the next request."""
        self._token = None
        self._token_expires = datetime.min

    def ensure_authenticated(self) -> None:
        """Re-login if token is missing or expired."""
        if not self._token or datetime.now() >= self._token_expires:
            self.login()

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    def get_devices(self) -> list[dict]:
        """Return list of thermostat devices for this account.

        Parses the device list from the login response (already cached),
        so no extra network call is needed.
        """
        self.ensure_authenticated()
        ubications = (
            self._login_data
            .get("ioUser", {})
            .get("coUbications", [])
        )
        devices = []
        for ubication in ubications:
            ub_name = ubication.get("ioDCModel", {}).get("ivstrUbicationName", "")
            for zone in ubication.get("coZones", []):
                zone_name = zone.get("ioDCModel", {}).get("ivstrZoneName", "")
                for device in zone.get("coDevices", []):
                    model = device.get("ioDCModel", {})
                    sub = device.get("ioSubTypeObj", {}).get("ioDCModel", {})
                    dev_name = model.get("ivstrDeviceName", model.get("ivstrDeviceSerial", ""))
                    devices.append({
                        "device_id": model.get("ivstrDeviceSerial"),
                        "name": f"{ub_name} – {zone_name} – {dev_name}",
                        "connected": model.get("ivblnDeviceConnected", False),
                        "firmware": model.get("ivstrDeviceFWVersion"),
                        "ubication": ub_name,
                        "zone": zone_name,
                        "sub": sub,
                    })
        return devices

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self, device_id: str) -> dict:
        """Read current thermostat state. Returns parsed values."""
        result = self._iot_run(
            device_id,
            {
                "cmd": "getConfig",
                "rid": 1,
                "ids": [
                    "targetTemp",
                    "temperature",
                    "thermostatMode",
                    "humidity",
                    "rssi",
                    "vs",
                    "output",
                    "tAway",
                    "lock",
                    "service",
                ],
            },
        )
        num_status = result.get("numStatus")
        if num_status == 6:
            # Device offline in cloud.
            # Raised as a specific subclass so the coordinator can apply watchdog logic.
            raise ZentralyDeviceOfflineError(f"Device {device_id} is offline (numStatus=6)")
        if num_status != 0:
            raise ZentralyConnectionError(f"getConfig failed: {result}")

        raw_io = result.get("ioData", "{}")
        if isinstance(raw_io, str):
            raw_io = json.loads(raw_io)

        state: dict = {}
        for item in raw_io.get("ids", []):
            state.update(item)

        return {
            "target_temp": state.get("targetTemp", 0) / TEMP_SCALE,
            "current_temp": state.get("temperature", 0) / TEMP_SCALE,
            "thermostat_mode": state.get("thermostatMode", 0),
            "humidity": state.get("humidity"),
            "rssi": state.get("rssi"),
            "output": state.get("output"),  # 1 = heating active
            "away_temp": state.get("tAway", 0) / TEMP_SCALE,
            "locked": bool(state.get("lock")),
            "firmware": state.get("vs"),
        }

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def _set_config(self, device_id: str, fields: dict | list[dict]) -> None:
        """Send a setConfig command with one or more id fields."""
        config_ids = fields if isinstance(fields, list) else [fields]
        result = self._iot_run(
            device_id,
            {
                "cmd": "setConfig",
                "rid": 0,
                "ids": config_ids,
            },
        )
        num_status = result.get("numStatus")
        if num_status == 6:
            raise ZentralyDeviceOfflineError(
                f"Device {device_id} is offline (numStatus=6), command not delivered"
            )
        if num_status != 0:
            raise ZentralyConnectionError(f"setConfig failed: numStatus={num_status}")
        inner = result.get("ioData", "{}")
        if isinstance(inner, str):
            inner = json.loads(inner)
        device_status = inner.get("status")
        if device_status != 200:
            message = f"setConfig failed: device status={device_status}"
            if device_status == 403:
                message += " (setpoint must be below 5 °C before off, or device is locked)"
            raise ZentralyConnectionError(message)

    def set_temperature(self, device_id: str, temperature: float) -> None:
        """Set target temperature (in °C)."""
        centidegrees = round(temperature * TEMP_SCALE)
        _LOGGER.debug("set_temperature %s → %d centidegrees", device_id, centidegrees)
        self._set_config(device_id, {"targetTemp": centidegrees})

    def set_hvac_mode(self, device_id: str, mode: int) -> None:
        """Set thermostatMode (0=off, 4=manual/heat, etc.)."""
        if mode == HVAC_MODE_OFF:
            self.set_power(device_id, False)
            return
        _LOGGER.debug("set_hvac_mode %s → mode %d", device_id, mode)
        self._set_config(device_id, {"thermostatMode": mode})

    def set_power(self, device_id: str, on: bool, *, restore_target_temp: float | None = None) -> None:
        """Turn the thermostat on or off.

        Off (matches app cloud state): target 5 °C then thermostatMode 0. The device
        rejects mode 0 until setpoint is below 5 °C, so we lower to 4 °C first if needed.
        On: manual mode (4) with target restored or 20 °C default.
        """
        if on:
            target = restore_target_temp
            if (
                target is None
                or target <= OFF_TARGET_TEMP
                or target > MAX_TARGET_TEMP
            ):
                target = DEFAULT_ON_TARGET_TEMP
            centidegrees = round(target * TEMP_SCALE)
            _LOGGER.debug("set_power on %s → %d centidegrees, mode %d", device_id, centidegrees, HVAC_MODE_MANUAL)
            self._set_config(
                device_id,
                [
                    {"targetTemp": centidegrees},
                    {"thermostatMode": HVAC_MODE_MANUAL},
                ],
            )
            return

        off_centidegrees = round(OFF_TARGET_TEMP * TEMP_SCALE)
        pre_off_centidegrees = round(OFF_COMMAND_TEMP * TEMP_SCALE)
        _LOGGER.debug(
            "set_power off %s → target %d then mode %d",
            device_id,
            off_centidegrees,
            HVAC_MODE_OFF,
        )
        try:
            self._set_config(
                device_id,
                [
                    {"targetTemp": off_centidegrees},
                    {"thermostatMode": HVAC_MODE_OFF},
                ],
            )
            return
        except ZentralyConnectionError as exc:
            if "status=403" not in str(exc):
                raise
            _LOGGER.debug(
                "set_power off %s: mode 0 rejected at 5 °C, lowering to %d first",
                device_id,
                pre_off_centidegrees,
            )

        self._set_config(device_id, {"targetTemp": pre_off_centidegrees})
        try:
            self._set_config(device_id, {"thermostatMode": HVAC_MODE_OFF})
        except ZentralyConnectionError as exc:
            if "status=403" not in str(exc):
                raise
            _LOGGER.warning(
                "set_power off %s: thermostatMode 0 still rejected; setpoint is at %s °C",
                device_id,
                OFF_COMMAND_TEMP,
            )
            return

        try:
            self._set_config(device_id, {"targetTemp": off_centidegrees})
        except ZentralyConnectionError:
            _LOGGER.debug(
                "set_power off %s: could not restore 5 °C setpoint after mode off",
                device_id,
            )

    def reset_device(self, device_id: str) -> bool:
        """Send a reset command to the device.

        Returns True if the cloud accepted the command.
        """
        try:
            result = self._iot_run(
                device_id,
                {
                    "cmd": "reset",
                    "rid": 0,
                    "ids": [{}],
                },
            )
        except ZentralyConnectionError:
            return False

        num_status = result.get("numStatus")
        inner = result.get("ioData", "{}")
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except (ValueError, TypeError):
                inner = {}
        accepted = num_status == 0 and isinstance(inner, dict) and inner.get("status") == 200
        _LOGGER.debug("reset_device %s → accepted=%s result=%s", device_id, accepted, result)
        return accepted
