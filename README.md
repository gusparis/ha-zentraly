# Zentraly – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/rgg-spagano/ha-zentraly.svg)](https://github.com/rgg-spagano/ha-zentraly/releases)

Custom integration for [Home Assistant](https://www.home-assistant.io/) to control **Zentraly WiFi thermostats** (boiler controllers).

Supports reading temperature, humidity, and boiler state, as well as setting the target temperature and switching modes on/off.

---

## Features

- Current room temperature and humidity
- Target temperature control (5 °C – 30 °C, 0.5 °C steps, same as the app)
- Humidity sensor entity
- Power switch and HVAC modes: **Heat** / **Off** (matches app on/off behaviour)
- Zentraly branding in Home Assistant UI
- Extra attributes: WiFi signal (RSSI), firmware version, boiler output state
- Auto-discovers all thermostats linked to your account
- Token-based auth with automatic re-login

---

## Installation

### Via HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations → ⋮ → Custom repositories**
3. Add `https://github.com/rgg-spagano/ha-zentraly` — category **Integration**
4. Search for **Zentraly** and install
5. Restart Home Assistant

### Manual

1. Copy `custom_components/zentraly/` into your HA config folder:
   ```
   /config/custom_components/zentraly/
   ```
2. Restart Home Assistant

---

## Configuration

Go to **Settings → Devices & Integrations → Add Integration → Zentraly**.

Enter your Zentraly account email and password. The integration will discover all thermostats linked to your account.

### WiFi stability (important)

The thermostat firmware (ESP32 + Azure IoT Hub) is sensitive to how often it is contacted from the cloud. This integration defaults to **gentle** behaviour:

- Poll every **10 minutes** (configurable under integration **Options**)
- Keep the Zentraly cloud session alive with a background login every 10 minutes (no device reboot)
- **No automatic device reset** unless you enable it in Options

If a thermostat still drops off Azure IoT Hub after about **12 hours** (WiFi LED blinking, `connected: false` in HA), enable **Proactive device reset** in Options — that reboots the unit every 11 hours to refresh the IoT SAS token. Only use that if you need it; frequent reboots can make WiFi look unstable.

Avoid running the official Zentraly app on the same account at the same time as Home Assistant if you see disconnects.

---

## API research

See [docs/zentraly-api-research.md](docs/zentraly-api-research.md) for auth fields (email, password, user number, security code) and how to capture app traffic with mitmproxy.

Inspect your account login structure (redacted):

```bash
python3 test_api.py --inspect-login
```

## API (reverse-engineered via MITM)

| Endpoint | Method | Description |
|---|---|---|
| `/Login` | GET | Auth with `Authorization: ztv2Auth{email}:{password}` → returns JWT |
| `/App` | POST | Lists locations, zones and devices |
| `/IOTCommand/Run` | POST | `getConfig` / `setConfig` commands to the thermostat |

### Read state
```json
POST /IOTCommand/Run
{
  "deviceId": "ZTTWF0100009124",
  "timeOut": 15000,
  "data": {
    "cmd": "getConfig",
    "rid": 1,
    "ids": ["targetTemp", "temperature", "thermostatMode", "humidity", "rssi", "output"]
  }
}
```
Response (temperature in centidegrees, e.g. `2310` = 23.1 °C):
```json
{"ids":[{"targetTemp":2550},{"temperature":2310},{"thermostatMode":4},{"humidity":64},{"output":1}],"status":200}
```

### Set temperature
```json
{"deviceId":"ZTTWF0100009124","timeOut":15000,"data":{"cmd":"setConfig","rid":0,"ids":[{"targetTemp":2200}]}}
```

### Set mode
```json
{"deviceId":"ZTTWF0100009124","timeOut":15000,"data":{"cmd":"setConfig","rid":0,"ids":[{"thermostatMode":0}]}}
```

| `thermostatMode` | HA mode | Notes |
|---|---|---|
| `0` | `off` | Confirmed via MITM |
| `4` | `heat` | "Modo manual" – confirmed via MITM |

---

## Supported languages

- English (`en`)
- Spanish (`es`)
- Portuguese (`pt`)

---

## License

MIT
