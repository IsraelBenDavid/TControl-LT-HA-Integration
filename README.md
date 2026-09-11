# TControl LT16 — Home Assistant Integration

A HACS-compatible Home Assistant custom integration for the **TControl LT16** relay controller. Communicates over Serial USB or a TCP-to-Serial bridge using the reverse-engineered ASCII protocol.

## Features

- 1–16 individually controllable relay channels exposed as HA switches.
- Serial (USB) **and** TCP connection support.
- UI-based configuration (Config Flow) — no YAML editing required.
- All channels grouped under a single Device in the HA Device Registry.
- HACS-ready for one-click installation.

## Installation

### HACS (Recommended)

1. Open **HACS → Integrations → ⋮ (top-right) → Custom repositories**.
2. Add the repository URL: `https://github.com/israelbendavid/tcontrol-lt-ha-integration`
3. Category: **Integration**.
4. Click **Download** and restart Home Assistant.

### Manual

1. Copy the `custom_components/tcontrol/` directory into your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **TControl LT16**.
3. Choose your connection type:
   - **Serial** — enter the serial port path (e.g., `/dev/ttyUSB0`).
   - **TCP** — enter the host address and port of your TCP-to-Serial bridge.
4. Set the number of relay channels (1–16).
5. Click **Submit**. The integration will test the connection before saving.

## Protocol Reference

| Action              | Command String |
|---------------------|---------------|
| Turn ON channel 1   | `S001ONE`     |
| Turn OFF channel 1  | `S001OFE`     |
| Turn ON channel 10  | `S00AONE`     |
| Turn OFF channel 16 | `S0010OFE`    |

- **Baud rate:** 9600
- **Encoding:** ASCII

## License

MIT
