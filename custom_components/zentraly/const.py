"""Constants for the Zentraly integration."""

DOMAIN = "zentraly"

BASE_URL = "https://ztprdrestservicesv2.azurewebsites.net"
LOGIN_URL = f"{BASE_URL}/Login"
APP_URL = f"{BASE_URL}/App"
IOT_COMMAND_URL = f"{BASE_URL}/IOTCommand/Run"

ZENTRALY_APP_VERSION = "7.1.3"
ZENTRALY_USER_AGENT = "zentralyRN/439 CFNetwork/3860.400.51 Darwin/25.3.0"
ZENTRALY_ACCEPT_LANGUAGE = "en-GB,en-US;q=0.9,en;q=0.8"
ZENTRALY_MOBILE_OS = 2
ZENTRALY_FB_TOKEN_PLACEHOLDER = "ha_integration"

DEFAULT_SCAN_INTERVAL = 600
MIN_SCAN_INTERVAL = 180
MAX_SCAN_INTERVAL = 1800
SESSION_KEEPALIVE_MINUTES = 10
JWT_REFRESH_MINUTES = 10
COMMAND_TIMEOUT = 15000

CONF_SCAN_INTERVAL = "scan_interval"
CONF_PROACTIVE_RESET = "proactive_reset"
PROACTIVE_RESET_INTERVAL_HOURS = 11

OFFLINE_RESET_THRESHOLD_MINUTES = 30
MIN_RESET_INTERVAL_HOURS = 4

HVAC_MODE_OFF = 0
HVAC_MODE_HEAT = 1
HVAC_MODE_COOL = 2
HVAC_MODE_AUTO = 3
HVAC_MODE_MANUAL = 4
HVAC_MODE_ECO = 5

TEMP_SCALE = 100
MIN_TARGET_TEMP = 5.0
MAX_TARGET_TEMP = 30.0
OFF_TARGET_TEMP = 5.0
OFF_COMMAND_TEMP = 4.0
DEFAULT_ON_TARGET_TEMP = 20.0


def is_virtual_off(
    target_temp: float | None,
    thermostat_mode: int | None = None,
) -> bool:
    if thermostat_mode == HVAC_MODE_OFF:
        return True
    return target_temp is not None and target_temp <= OFF_TARGET_TEMP

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_IDS = "device_ids"
CONF_DEVICE_NAME = "device_name"

ATTR_HUMIDITY = "humidity"
ATTR_RSSI = "rssi"
ATTR_FIRMWARE = "firmware_version"
ATTR_CONNECTED = "connected"
ATTR_OUTPUT = "output"
ATTR_AWAY_TEMP = "away_temperature"
