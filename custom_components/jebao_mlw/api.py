"""Local Gizwits/Jebao protocol helpers for MLW wave pumps."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import socket
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import partial
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_SERVER,
    CONF_DEVICE_ID,
    CONF_DISCOVERY_FINGERPRINT,
    CONF_DISCOVERY_ID,
    CONF_HOST,
    CONF_MODEL,
    CONF_NAME,
    CONF_PORT,
    CONF_VERSION,
    DEFAULT_DISCOVERY_TIMEOUT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DISCOVERY_PORT,
    MODEL_MLW_10,
)

_LOGGER = logging.getLogger(__name__)

PREFIX = b"\x00\x00\x00\x03"
DISCOVERY_REQUEST = bytes.fromhex("0000000303000003")
PASSCODE_REQUEST = bytes.fromhex("0000000303000006")
SERIAL_DATA_REQUEST = bytes.fromhex("000000030400009002")
PING_REQUEST = bytes.fromhex("0000000303000015")
COMMAND_HEADER = bytes.fromhex("00000003a003000093000000")
COMMAND_PADDING = bytes.fromhex("01000000000000")

MODE_PULSE = "pulse"
MODE_CROSS = "cross"
MODE_SINE = "sine"
MODE_RANDOM = "random"
MODE_CONSTANT = "constant"
MODE_FEED = "feed"

MIN_FLOW = 30
MAX_FLOW = 100
DEFAULT_FLOW = 50

MIN_FREQUENCY = 5
MAX_FREQUENCY = 100
DEFAULT_FREQUENCY = 50

MIN_FEED_DURATION = 1
MAX_FEED_DURATION = 60


@dataclass(frozen=True, slots=True)
class ModeProfile:
    """Command profile for a supported MLW mode."""

    key: str
    label: str
    code: int
    supports_frequency: bool
    default_frequency: int


MODE_PROFILES: dict[str, ModeProfile] = {
    MODE_PULSE: ModeProfile(MODE_PULSE, "Classic Pulse", 0x00, True, DEFAULT_FREQUENCY),
    MODE_CROSS: ModeProfile(
        MODE_CROSS, "Classic Cross-flow", 0x02, True, DEFAULT_FREQUENCY
    ),
    MODE_SINE: ModeProfile(MODE_SINE, "Sine", 0x20, True, DEFAULT_FREQUENCY),
    MODE_RANDOM: ModeProfile(MODE_RANDOM, "Random", 0x40, False, 0x00),
    MODE_CONSTANT: ModeProfile(MODE_CONSTANT, "Constant", 0x60, False, 0x32),
}

MODE_LABELS = [profile.label for profile in MODE_PROFILES.values()]
MODE_BY_LABEL = {profile.label: profile.key for profile in MODE_PROFILES.values()}
MODE_LABEL_BY_KEY = {profile.key: profile.label for profile in MODE_PROFILES.values()}
FREQUENCY_MODES = {
    key for key, profile in MODE_PROFILES.items() if profile.supports_frequency
}

MODE_FROM_RAW_BASE = {
    0x00: MODE_PULSE,
    0x02: MODE_CROSS,
    0x20: MODE_SINE,
    0x40: MODE_RANDOM,
    0x60: MODE_CONSTANT,
    0x04: MODE_FEED,
    0x64: MODE_FEED,
}


class JebaoMlwError(Exception):
    """Base error for Jebao MLW communication."""


class JebaoMlwConnectionError(JebaoMlwError):
    """Raised when the local device connection fails."""


class JebaoMlwCommandError(JebaoMlwError):
    """Raised when a command cannot be sent to the device."""


@dataclass(frozen=True, slots=True)
class DiscoveredJebaoDevice:
    """Device discovered by UDP broadcast."""

    host: str
    device_id: str = ""
    fingerprint: str = ""
    version: str = ""
    api_server: str = ""
    model: str = MODEL_MLW_10

    @property
    def stable_id(self) -> str:
        """Return the best available stable identifier."""

        return self.device_id or self.fingerprint or self.host

    @property
    def short_id(self) -> str:
        """Return a compact identifier for generated names."""

        return (self.device_id or self.fingerprint or self.host)[-6:]

    def as_config(self, *, name: str | None = None, port: int = DEFAULT_PORT) -> dict[str, Any]:
        """Return a Home Assistant config-entry device dict."""

        return {
            CONF_DEVICE_ID: self.stable_id,
            CONF_DISCOVERY_ID: self.device_id,
            CONF_DISCOVERY_FINGERPRINT: self.fingerprint,
            CONF_HOST: self.host,
            CONF_PORT: port,
            CONF_NAME: name or f"{DEFAULT_NAME} {self.host}",
            CONF_MODEL: self.model,
            CONF_VERSION: self.version,
            CONF_API_SERVER: self.api_server,
        }


@dataclass(frozen=True, slots=True)
class JebaoMlwDeviceConfig:
    """Configured Jebao MLW device."""

    id: str
    host: str
    port: int = DEFAULT_PORT
    name: str = DEFAULT_NAME
    model: str = MODEL_MLW_10
    discovery_id: str | None = None
    discovery_fingerprint: str | None = None
    version: str | None = None
    api_server: str | None = None


@dataclass(frozen=True, slots=True)
class PumpState:
    """Current pump state parsed from MLW status frames."""

    connected: bool = False
    is_on: bool | None = None
    mode: str | None = None
    raw_mode: int | None = None
    flow: int | None = None
    frequency: int | None = None
    feed_time_left: int | None = None
    last_seen: datetime | None = None

    @property
    def mode_label(self) -> str | None:
        """Return a user-facing mode label."""

        if self.mode == MODE_FEED:
            return "Feed"
        if self.mode is None:
            return None
        return MODE_LABEL_BY_KEY.get(self.mode, self.mode)


def build_devices_from_config(raw_devices: list[dict[str, Any]]) -> dict[str, JebaoMlwDeviceConfig]:
    """Normalize configured devices from a config entry."""

    devices: dict[str, JebaoMlwDeviceConfig] = {}
    for index, raw_device in enumerate(raw_devices, start=1):
        host = str(raw_device.get(CONF_HOST, "")).strip()
        discovery_id = str(raw_device.get(CONF_DISCOVERY_ID) or "").strip()
        discovery_fingerprint = str(
            raw_device.get(CONF_DISCOVERY_FINGERPRINT) or ""
        ).strip()
        device_id = str(
            raw_device.get(CONF_DEVICE_ID)
            or discovery_id
            or discovery_fingerprint
            or host
        ).strip()
        if device_id in devices:
            device_id = f"{device_id}_{index}"

        devices[device_id] = JebaoMlwDeviceConfig(
            id=device_id,
            host=host,
            port=int(raw_device.get(CONF_PORT, DEFAULT_PORT)),
            name=str(raw_device.get(CONF_NAME) or f"{DEFAULT_NAME} {host}"),
            model=str(raw_device.get(CONF_MODEL) or MODEL_MLW_10),
            discovery_id=discovery_id or None,
            discovery_fingerprint=discovery_fingerprint or None,
            version=raw_device.get(CONF_VERSION) or None,
            api_server=raw_device.get(CONF_API_SERVER) or None,
        )

    return devices


def parse_hosts(value: str) -> list[str]:
    """Parse a comma/semicolon/space separated host list."""

    hosts = [
        host.strip()
        for part in value.replace(";", ",").split(",")
        for host in part.split()
        if host.strip()
    ]
    return list(dict.fromkeys(hosts))


def _decode_ascii(value: bytes) -> str:
    return value.split(b"\x00", 1)[0].decode("ascii", "ignore").strip()


def _ascii_strings(data: bytes) -> list[str]:
    text = "".join(chr(byte) if 32 <= byte <= 126 else "\x00" for byte in data)
    return [part for part in text.split("\x00") if len(part) >= 3]


def parse_discovery_response(data: bytes, host: str) -> DiscoveredJebaoDevice | None:
    """Parse a Gizwits discovery response."""

    if len(data) < 8 or data[:4] != PREFIX or data[7] != 0x04:
        return None

    fingerprint = hashlib.sha1(data).hexdigest()[:16]
    device_id = ""
    if len(data) > 10:
        declared_length = data[9]
        if 0 < declared_length <= len(data) - 10:
            device_id = _decode_ascii(data[10 : 10 + declared_length])

    strings = _ascii_strings(data)
    api_server = next(
        (part for part in strings if "gizwits" in part.lower() or ":" in part), ""
    )
    version = next(
        (
            part
            for part in reversed(strings)
            if "." in part and any(character.isdigit() for character in part)
        ),
        "",
    )

    return DiscoveredJebaoDevice(
        host=host,
        device_id=device_id,
        fingerprint=fingerprint,
        version=version,
        api_server=api_server,
    )


def discovery_match_score(
    configured: JebaoMlwDeviceConfig, discovered: DiscoveredJebaoDevice
) -> int:
    """Return how confidently a discovery response matches a configured device."""

    discovered_ids = {
        value
        for value in (
            discovered.stable_id,
            discovered.device_id,
            discovered.fingerprint,
        )
        if value
    }
    configured_ids = {
        value
        for value in (
            configured.id,
            configured.discovery_id,
            configured.discovery_fingerprint,
        )
        if value
    }

    if configured_ids & discovered_ids:
        return 100

    if configured.host and configured.host == discovered.host:
        return 10

    return 0


def discover_devices(timeout: float = DEFAULT_DISCOVERY_TIMEOUT) -> list[DiscoveredJebaoDevice]:
    """Discover Jebao devices by UDP broadcast."""

    deadline = time.monotonic() + timeout
    devices: dict[str, DiscoveredJebaoDevice] = {}

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_socket.settimeout(0.5)

    try:
        udp_socket.sendto(DISCOVERY_REQUEST, ("255.255.255.255", DISCOVERY_PORT))
        while time.monotonic() < deadline:
            remaining = max(deadline - time.monotonic(), 0.1)
            udp_socket.settimeout(min(remaining, 0.5))
            try:
                data, address = udp_socket.recvfrom(2048)
            except socket.timeout:
                continue

            device = parse_discovery_response(data, address[0])
            if device is None:
                continue

            devices[device.stable_id] = device
    finally:
        udp_socket.close()

    return list(devices.values())


async def async_discover_devices(
    hass: HomeAssistant, timeout: float = DEFAULT_DISCOVERY_TIMEOUT
) -> list[DiscoveredJebaoDevice]:
    """Run UDP discovery away from the event loop."""

    return await hass.async_add_executor_job(partial(discover_devices, timeout))


def parse_mlw_state_from_frame(data: bytes, previous: PumpState | None = None) -> PumpState | None:
    """Parse the MLW-10 status frame used by the tested script."""

    if len(data) < 15 or data[:4] != PREFIX or data[4] != 0x95:
        return None

    raw_mode = data[11]
    flow = data[12]
    frequency = data[13]
    feed_time_left = data[14]
    is_on = (raw_mode & 0x01) == 1
    base_mode = raw_mode & 0xFE
    mode = MODE_FROM_RAW_BASE.get(base_mode)

    return PumpState(
        connected=True,
        is_on=is_on,
        mode=mode,
        raw_mode=raw_mode,
        flow=flow,
        frequency=frequency,
        feed_time_left=feed_time_left,
        last_seen=datetime.now(timezone.utc),
    )


def iter_mlw_states(data: bytes, previous: PumpState | None = None) -> list[PumpState]:
    """Return all MLW states found in a received TCP chunk."""

    states: list[PumpState] = []
    offset = data.find(PREFIX)
    while offset != -1:
        state = parse_mlw_state_from_frame(data[offset:], previous)
        if state is not None:
            states.append(state)
            previous = state
        offset = data.find(PREFIX, offset + 1)
    return states


def clamp_int(value: int | float | None, minimum: int, maximum: int, default: int) -> int:
    """Clamp a number into the expected device range."""

    if value is None:
        value = default
    return max(minimum, min(maximum, int(round(value))))


class MlwPumpClient:
    """Async TCP client for one Jebao MLW pump."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        response_timeout: float = 5,
        ping_interval: float = 10,
    ) -> None:
        self.host = host
        self.port = port
        self.response_timeout = response_timeout
        self.ping_interval = ping_interval

        self.state = PumpState()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._write_lock = asyncio.Lock()
        self._ping_task: asyncio.Task[None] | None = None
        self._seq_num = 0x2A

    @property
    def connected(self) -> bool:
        """Return true when the TCP stream is open."""

        return self._writer is not None and not self._writer.is_closing()

    async def async_connect(self) -> None:
        """Open the TCP connection and complete the Gizwits login."""

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.response_timeout,
            )
            await self._handshake()
        except (asyncio.TimeoutError, OSError) as err:
            await self.async_close()
            raise JebaoMlwConnectionError(
                f"Cannot connect to {self.host}:{self.port}"
            ) from err

        self.state = replace(self.state, connected=True)
        self._ping_task = asyncio.create_task(self._ping_loop())

    async def _handshake(self) -> None:
        await self._write(PASSCODE_REQUEST)
        passcode_response = await self._read_once()

        if len(passcode_response) < 8 or passcode_response[7] != 0x07:
            raise JebaoMlwConnectionError("Device did not return a passcode response")

        login_request = bytearray(passcode_response)
        login_request[7] = 0x08

        await self._write(bytes(login_request))
        login_response = await self._read_once()

        if (
            len(login_response) < 9
            or login_response[7] != 0x09
            or login_response[8] != 0x00
        ):
            raise JebaoMlwConnectionError("Device login failed")

        await self._write(SERIAL_DATA_REQUEST)

    async def _read_once(self) -> bytes:
        if self._reader is None:
            raise JebaoMlwConnectionError("Device is not connected")

        data = await asyncio.wait_for(self._reader.read(1024), self.response_timeout)
        if not data:
            raise JebaoMlwConnectionError("Device closed the connection")
        return data

    async def async_listen(self):
        """Yield state updates until the TCP connection closes."""

        if self._reader is None:
            raise JebaoMlwConnectionError("Device is not connected")

        while True:
            data = await self._reader.read(1024)
            if not data:
                raise JebaoMlwConnectionError("Device closed the connection")

            for state in iter_mlw_states(data, self.state):
                self.state = state
                yield state

    async def _write(self, data: bytes) -> None:
        if self._writer is None or self._writer.is_closing():
            raise JebaoMlwCommandError("Device is not connected")

        self._writer.write(data)
        await asyncio.wait_for(self._writer.drain(), self.response_timeout)

    async def _send_command(self, payload: bytes) -> None:
        async with self._write_lock:
            seq = bytes([self._seq_num & 0xFF])
            self._seq_num = (self._seq_num + 1) % 256

            message = COMMAND_HEADER + seq + COMMAND_PADDING + payload
            await self._write(message.ljust(422, b"\x00"))

    async def async_set_power(self, is_on: bool) -> PumpState:
        """Turn the pump motor on or off."""

        payload = bytes([0x00, 0x01, 0x00, 0x01 if is_on else 0x00, 0x00, 0x00])
        await self._send_command(payload)
        self.state = replace(self.state, connected=True, is_on=is_on)
        return self.state

    async def async_set_mode(
        self,
        mode: str,
        *,
        flow: int | float | None = None,
        frequency: int | float | None = None,
        auto_on: bool = True,
    ) -> PumpState:
        """Set a wave mode and optionally turn the motor on."""

        if mode not in MODE_PROFILES:
            raise JebaoMlwCommandError(f"Unsupported mode: {mode}")

        profile = MODE_PROFILES[mode]
        flow_value = clamp_int(
            flow,
            MIN_FLOW,
            MAX_FLOW,
            self.state.flow if self.state.flow is not None else DEFAULT_FLOW,
        )

        if profile.supports_frequency:
            frequency_value = clamp_int(
                frequency,
                MIN_FREQUENCY,
                MAX_FREQUENCY,
                self.state.frequency
                if self.state.frequency is not None
                else profile.default_frequency,
            )
        else:
            frequency_value = profile.default_frequency

        await self._send_command(
            bytes([0x03, 0x6E, 0x00, profile.code, flow_value, frequency_value])
        )

        if auto_on:
            await asyncio.sleep(0.1)
            await self.async_set_power(True)

        self.state = replace(
            self.state,
            connected=True,
            is_on=True if auto_on else self.state.is_on,
            mode=mode,
            raw_mode=profile.code | (0x01 if auto_on else 0x00),
            flow=flow_value,
            frequency=frequency_value,
        )
        return self.state

    async def async_start_feed(self, minutes: int | float) -> PumpState:
        """Start feed mode for the requested number of minutes."""

        feed_minutes = clamp_int(
            minutes, MIN_FEED_DURATION, MAX_FEED_DURATION, MIN_FEED_DURATION
        )
        await self._send_command(
            bytes([0x04, 0x04, 0x00, 0x04, 0x00, 0x00, feed_minutes, 0x00])
        )

        self.state = replace(
            self.state,
            connected=True,
            is_on=True,
            mode=MODE_FEED,
            raw_mode=0x05,
            feed_time_left=feed_minutes,
        )
        return self.state

    async def _ping_loop(self) -> None:
        while self.connected:
            await asyncio.sleep(self.ping_interval)
            if not self.connected:
                return
            try:
                await self._write(PING_REQUEST)
            except (JebaoMlwError, OSError, asyncio.TimeoutError):
                _LOGGER.debug("Ping failed for %s:%s", self.host, self.port)
                return

    async def async_close(self) -> None:
        """Close the TCP stream."""

        if self._ping_task is not None:
            self._ping_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ping_task
            self._ping_task = None

        writer = self._writer
        self._writer = None
        self._reader = None

        if writer is not None:
            writer.close()
            with contextlib.suppress(OSError, asyncio.TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), 2)

        self.state = replace(self.state, connected=False)


async def async_validate_device(host: str, port: int = DEFAULT_PORT) -> None:
    """Open and close a connection to validate manual config flow input."""

    client = MlwPumpClient(host, port)
    try:
        await client.async_connect()
    finally:
        await client.async_close()
