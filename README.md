# TControl LT16 — Home Assistant Integration

A HACS-compatible Home Assistant custom integration for the **TControl LT16** relay controller. Communicates over Serial USB or a TCP-to-Serial bridge using the reverse-engineered ASCII protocol.

## Features

- 1–16 individually controllable relay channels exposed as HA switches.
- Serial (USB) **and** TCP connection support.
- Two-way state sync: the controller is polled (`S00QLE`) at a configurable interval so
  switches reflect the real relay state, even when relays are changed outside HA.
- UI-based configuration (Config Flow) — no YAML editing required.
- All channels grouped under a single Device in the HA Device Registry.
- HACS-ready for one-click installation.

Requires Home Assistant 2025.3 or newer.

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
4. Set the number of relay channels (1–16) and the polling interval in milliseconds
   (default 2000, minimum 200 — faster polling would saturate the 9600 baud line).
5. Click **Submit**. The integration queries the controller (`S00QLE`) before saving, so
   the port/host must be reachable and the controller must answer.

## How it works

The port is never held open. Every operation is a short *open → send → close* cycle
that runs in an executor thread, and a lock guarantees that the state poll and relay
commands never open the port (or the TCP bridge) at the same time. Serial-to-TCP
bridges usually accept a single client, so overlapping connections would otherwise
make commands fail or be misread.

When you toggle a switch the new state is shown immediately and confirmed by the next
poll. If a command cannot be delivered, the service call fails with an error that is
visible in the UI and in automation traces. If the controller stops answering, the
switches become **unavailable** until it responds again.

## Troubleshooting

- **Switches are `unavailable`** — the controller did not answer the last poll. Check
  the cable / bridge, and that nothing else has the serial port open. Details are in
  **Settings → System → Logs** (filter on `tcontrol`).
- **A toggle fails with "Failed to turn on TControl channel N"** — the command could
  not be sent; the error text contains the underlying serial/socket error.
- **Setup keeps retrying** — the port/host opened but no `A00…E` status frame came back.
  Verify the controller answers `S00QLE` in a serial terminal.
- Enable debug logging to see every frame on the wire:

  ```yaml
  logger:
    logs:
      custom_components.tcontrol: debug
  ```

## Development

```bash
pip install -r requirements_test.txt
pytest
```

The tests load the integration into a real Home Assistant core against a simulated
controller (`tests/fake_device.py`).

## Protocol Reference

| Action              | Command String | Response           |
|---------------------|----------------|--------------------|
| Turn ON channel 1   | `S001ONE`      | —                  |
| Turn OFF channel 1  | `S001OFE`      | —                  |
| Turn ON channel 10  | `S00AONE`      | —                  |
| Turn OFF channel 16 | `S0010OFE`     | —                  |
| Query all relays    | `S00QLE`       | `A00<bits>E` — one `0`/`1` per channel, e.g. `A0000111111E` |

- **Baud rate:** 9600
- **Encoding:** ASCII

## License

MIT
