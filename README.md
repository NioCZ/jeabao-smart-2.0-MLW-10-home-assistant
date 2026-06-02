# Jebao MLW Local for Home Assistant

Custom Home Assistant integration for local control of Jebao MLW wave pumps over the Gizwits LAN protocol. It is based on the verified communication from `jeabao-smart 2.0 MLW-10/test.py` and does not use the cloud.

## Features

- UDP discovery on port `12414`
- TCP communication on port `12416`
- device identity stored from the UDP discovery response, not from the IP address
- automatic IP resolution on Home Assistant startup and after reconnects
- automatic reconnect after connection loss
- multiple pumps in one integration entry
- entities for power, mode, flow, frequency, feed mode and diagnostics
- protocol code separated in `custom_components/jebao_mlw/api.py` so other Jebao device profiles can be added later

## Installation With HACS

1. Upload this repository to GitHub.
2. Open HACS and go to `Custom repositories`.
3. Add the repository URL as category `Integration`.
4. Install `Jebao MLW Local`.
5. Restart Home Assistant.
6. Go to `Settings > Devices & services` and add `Jebao MLW Local`.

## Adding Pumps

The recommended setup is to leave `Manual IP addresses` empty. The integration will scan the local network with UDP discovery, show the pumps it found, and store their discovered device IDs. The IP address is only kept as a last-known fallback value.

When Home Assistant starts, or when a pump reconnects after a network outage, the integration sends UDP discovery again and connects to the current IP address of the stored pump ID.

You can still add pumps manually by entering one or more IP addresses separated by commas:

```text
192.168.1.41, 192.168.1.42
```

Even during manual setup, the integration tries to enrich the device with UDP discovery metadata. If the pump answers the discovery request, later IP changes should not matter.

## Manual Installation

Copy this folder:

```text
custom_components/jebao_mlw
```

to your Home Assistant configuration directory:

```text
/config/custom_components/jebao_mlw
```

Restart Home Assistant and add the integration from the UI.

## Entities

Each pump becomes its own Home Assistant device with these entities:

- `switch` Pump
- `select` Mode
- `number` Flow
- `number` Frequency
- `number` Feed duration
- `button` Start feed mode
- `binary_sensor` Connected
- `sensor` Feed remaining
- `sensor` Last seen
- `sensor` Raw mode, disabled by default in the entity registry

## Supported Modes

- Classic Pulse
- Classic Cross-flow
- Sine
- Random
- Constant
- Feed mode

## Extending to Other Jebao Devices

Discovery, TCP handshake and login are separated from the MLW-specific payloads. For another Gizwits-based Jebao device, the most likely places to update are:

- `MODE_PROFILES`
- `MODE_FROM_RAW_BASE`
- `parse_mlw_state_from_frame`
- payload builders in `MlwPumpClient.async_set_mode`, `async_set_power` and `async_start_feed`

If another Jebao device uses the same Gizwits LAN base protocol, it should be possible to add it as a new device profile without rewriting the whole integration.
