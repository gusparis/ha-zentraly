# Zentraly – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Control **Zentraly WiFi thermostats** from Home Assistant: temperature, humidity, on/off, and optional device reset.

## Installation

### HACS

1. **Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/gusparis/ha-zentraly` (category **Integration**)
3. Install **Zentraly** and restart Home Assistant

### Manual

Copy `custom_components/zentraly/` to `/config/custom_components/zentraly/` and restart.

## Setup

**Settings → Devices & integrations → Add integration → Zentraly**

Enter your Zentraly account email and password. All thermostats on the account are listed; choose which ones to add.

## Usage

- **Climate**: target temperature (5–30 °C, 0.5 °C steps) and **Heat** / **Off**
- **Sensor**: humidity
- **Switch**: boiler / heating output state (read-only where applicable)
- **Button**: restart thermostat (use if a device stays offline)

### Options (integration menu)

| Option | Default | Notes |
|--------|---------|--------|
| Poll interval | 10 min | Longer intervals reduce load on the thermostat WiFi |
| Proactive reset | Off | Periodic restart every 11 h; enable only if devices drop offline after many hours |

Avoid using the official Zentraly app on the same account at the same time if you see frequent disconnects.

## Languages

English, Spanish, Portuguese.

## License

MIT
