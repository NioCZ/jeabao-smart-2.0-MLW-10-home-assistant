"""Runtime coordination for Jebao MLW devices."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import replace
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import (
    FREQUENCY_MODES,
    MODE_CONSTANT,
    MODE_FEED,
    MODE_PROFILES,
    DiscoveredJebaoDevice,
    JebaoMlwDeviceConfig,
    MlwPumpClient,
    PumpState,
    async_discover_devices,
    build_devices_from_config,
    clamp_int,
    discovery_match_score,
)
from .const import (
    CONF_API_SERVER,
    CONF_DEVICE_ID,
    CONF_DISCOVERY_FINGERPRINT,
    CONF_DISCOVERY_ID,
    CONF_DEVICES,
    CONF_HOST,
    CONF_RECONNECT_DELAY,
    CONF_VERSION,
    DEFAULT_FEED_DURATION,
    DEFAULT_RECONNECT_DELAY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class JebaoMlwCoordinator(DataUpdateCoordinator[dict[str, PumpState]]):
    """Coordinate push updates for all configured pumps."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        raw_devices = entry.options.get(CONF_DEVICES) or entry.data.get(CONF_DEVICES, [])
        self.devices = build_devices_from_config(raw_devices)
        self.reconnect_delay = int(
            entry.options.get(
                CONF_RECONNECT_DELAY,
                entry.data.get(CONF_RECONNECT_DELAY, DEFAULT_RECONNECT_DELAY),
            )
        )
        self.controllers: dict[str, JebaoMlwController] = {}
        self._discovery_cache: list[DiscoveredJebaoDevice] = []
        self._discovery_cache_at = 0.0
        self._discovery_lock = asyncio.Lock()

        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.async_set_updated_data({device_id: PumpState() for device_id in self.devices})

    async def async_start(self) -> None:
        """Start one background connection task per configured pump."""

        for device_id, device in self.devices.items():
            controller = JebaoMlwController(
                self.hass,
                device_id,
                device,
                self.reconnect_delay,
                self._async_resolve_host,
                self._handle_state_update,
            )
            self.controllers[device_id] = controller
            controller.async_start()

    async def async_stop(self) -> None:
        """Stop all background tasks."""

        await asyncio.gather(
            *(controller.async_stop() for controller in self.controllers.values()),
            return_exceptions=True,
        )
        self.controllers.clear()

    @callback
    def _handle_state_update(self, device_id: str, state: PumpState) -> None:
        data = dict(self.data or {})
        data[device_id] = state
        self.async_set_updated_data(data)

    async def _async_discover_cached(self, *, force: bool = False) -> list[DiscoveredJebaoDevice]:
        """Discover devices, sharing one UDP result between pump controllers."""

        async with self._discovery_lock:
            cache_age = time.monotonic() - self._discovery_cache_at
            if self._discovery_cache and not force and cache_age < 5:
                return self._discovery_cache

            self._discovery_cache = await async_discover_devices(self.hass)
            self._discovery_cache_at = time.monotonic()
            return self._discovery_cache

    async def _async_resolve_host(
        self, device_id: str, current_host: str
    ) -> str:
        """Find the current IP address for a configured pump."""

        device = self.devices[device_id]
        try:
            discovered_devices = await self._async_discover_cached()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Jebao MLW UDP discovery failed: %s", err)
            return current_host
        matches = sorted(
            (
                (discovery_match_score(device, discovered), discovered)
                for discovered in discovered_devices
            ),
            key=lambda item: item[0],
            reverse=True,
        )

        if matches and matches[0][0] > 0:
            discovered = matches[0][1]
            if discovered.host != current_host:
                _LOGGER.info(
                    "Resolved Jebao MLW pump %s from %s to %s by UDP discovery",
                    device_id,
                    current_host or "unknown host",
                    discovered.host,
                )
            self.devices[device_id] = replace(
                device,
                host=discovered.host,
                discovery_id=discovered.device_id or device.discovery_id,
                discovery_fingerprint=discovered.fingerprint
                or device.discovery_fingerprint,
                version=discovered.version or device.version,
                api_server=discovered.api_server or device.api_server,
            )
            self._persist_discovery_metadata(device_id, current_host, discovered)
            return discovered.host

        return current_host

    @callback
    def _persist_discovery_metadata(
        self,
        device_id: str,
        current_host: str,
        discovered: DiscoveredJebaoDevice,
    ) -> None:
        """Persist learned discovery identity and latest fallback host."""

        uses_options = CONF_DEVICES in self.entry.options
        container = dict(self.entry.options if uses_options else self.entry.data)
        raw_devices = [dict(device) for device in container.get(CONF_DEVICES, [])]
        changed = False

        for raw_device in raw_devices:
            if not _raw_device_matches(device_id, current_host, raw_device, discovered):
                continue

            updates = {
                CONF_HOST: discovered.host,
                CONF_DISCOVERY_ID: discovered.device_id,
                CONF_DISCOVERY_FINGERPRINT: discovered.fingerprint,
                CONF_VERSION: discovered.version,
                CONF_API_SERVER: discovered.api_server,
            }
            for key, value in updates.items():
                if value and raw_device.get(key) != value:
                    raw_device[key] = value
                    changed = True
            break

        if not changed:
            return

        container[CONF_DEVICES] = raw_devices
        if uses_options:
            self.hass.config_entries.async_update_entry(
                self.entry, options=container
            )
        else:
            self.hass.config_entries.async_update_entry(self.entry, data=container)


def _raw_device_matches(
    device_id: str,
    current_host: str,
    raw_device: dict[str, Any],
    discovered: DiscoveredJebaoDevice,
) -> bool:
    """Return true when a raw config-entry device is the discovered pump."""

    identifiers = {
        str(value)
        for value in (
            raw_device.get(CONF_DEVICE_ID),
            raw_device.get(CONF_DISCOVERY_ID),
            raw_device.get(CONF_DISCOVERY_FINGERPRINT),
            raw_device.get(CONF_HOST),
        )
        if value
    }
    discovered_identifiers = {
        str(value)
        for value in (
            device_id,
            current_host,
            discovered.stable_id,
            discovered.device_id,
            discovered.fingerprint,
            discovered.host,
        )
        if value
    }
    return bool(identifiers & discovered_identifiers)


class JebaoMlwController:
    """Maintain one persistent connection with automatic reconnect."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        device: JebaoMlwDeviceConfig,
        reconnect_delay: int,
        host_resolver,
        state_callback,
    ) -> None:
        self.hass = hass
        self.device_id = device_id
        self.host = device.host
        self.port = device.port
        self.reconnect_delay = reconnect_delay
        self._host_resolver = host_resolver
        self._state_callback = state_callback

        self.feed_duration = DEFAULT_FEED_DURATION
        self.state = PumpState()
        self._client: MlwPumpClient | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def async_start(self) -> None:
        """Start the connection loop."""

        self._stop_event.clear()
        self._task = self.hass.async_create_task(
            self._connection_loop(), name=f"jebao_mlw_{self.device_id}"
        )

    async def async_stop(self) -> None:
        """Stop the connection loop and close the socket."""

        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        if self._client is not None:
            await self._client.async_close()
            self._client = None

    async def _connection_loop(self) -> None:
        while not self._stop_event.is_set():
            self.host = await self._host_resolver(self.device_id, self.host)
            client = MlwPumpClient(self.host, self.port)
            self._client = client

            try:
                await client.async_connect()
                self._set_state(replace(client.state, connected=True))
                _LOGGER.info("Connected to Jebao MLW pump %s at %s:%s", self.device_id, self.host, self.port)

                async for state in client.async_listen():
                    self._set_state(state)
                    if self._stop_event.is_set():
                        break

            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                if not self._stop_event.is_set():
                    _LOGGER.warning(
                        "Connection to Jebao MLW pump %s at %s:%s failed: %s",
                        self.device_id,
                        self.host,
                        self.port,
                        err,
                    )
            finally:
                await client.async_close()
                if self._client is client:
                    self._client = None

                if not self._stop_event.is_set():
                    self._set_state(replace(self.state, connected=False))
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(
                            self._stop_event.wait(), timeout=self.reconnect_delay
                        )

    @callback
    def _set_state(self, state: PumpState) -> None:
        self.state = state
        self._state_callback(self.device_id, state)

    def _require_client(self) -> MlwPumpClient:
        if self._client is None or not self._client.connected:
            raise HomeAssistantError("Jebao pump is not connected")
        return self._client

    async def _run_command(self, command: str, *args: Any, **kwargs: Any) -> PumpState:
        client = self._require_client()
        try:
            method = getattr(client, command)
            state = await method(*args, **kwargs)
        except Exception as err:  # noqa: BLE001
            await client.async_close()
            raise HomeAssistantError(f"Cannot send command to Jebao pump: {err}") from err

        self._set_state(state)
        return state

    async def async_turn_on(self) -> None:
        """Turn the pump on."""

        await self._run_command("async_set_power", True)

    async def async_turn_off(self) -> None:
        """Turn the pump off."""

        await self._run_command("async_set_power", False)

    async def async_set_mode(self, mode: str) -> None:
        """Set the active pump mode."""

        if mode not in MODE_PROFILES:
            raise HomeAssistantError(f"Unsupported Jebao mode: {mode}")
        await self._run_command("async_set_mode", mode)

    async def async_set_flow(self, flow: int | float) -> None:
        """Update flow by resending the current mode."""

        mode = self.state.mode
        if mode in (None, MODE_FEED):
            mode = MODE_CONSTANT
        await self._run_command(
            "async_set_mode",
            mode,
            flow=flow,
            frequency=self.state.frequency,
        )

    async def async_set_frequency(self, frequency: int | float) -> None:
        """Update frequency for modes that support it."""

        mode = self.state.mode
        if mode not in FREQUENCY_MODES:
            raise HomeAssistantError("The current Jebao mode does not use frequency")

        await self._run_command(
            "async_set_mode",
            mode,
            flow=self.state.flow,
            frequency=frequency,
        )

    async def async_start_feed(self) -> None:
        """Start feed mode with the locally configured duration."""

        await self._run_command("async_start_feed", self.feed_duration)

    @callback
    def async_set_feed_duration(self, minutes: int | float) -> None:
        """Store feed duration for the next feed-mode button press."""

        self.feed_duration = clamp_int(minutes, 1, 60, DEFAULT_FEED_DURATION)
