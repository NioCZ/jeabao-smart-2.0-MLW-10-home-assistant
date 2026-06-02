"""Runtime coordination for Jebao MLW devices."""

from __future__ import annotations

import asyncio
import contextlib
import logging
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
    MlwPumpClient,
    PumpState,
    build_devices_from_config,
    clamp_int,
)
from .const import (
    CONF_DEVICES,
    CONF_RECONNECT_DELAY,
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

        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.async_set_updated_data({device_id: PumpState() for device_id in self.devices})

    async def async_start(self) -> None:
        """Start one background connection task per configured pump."""

        for device_id, device in self.devices.items():
            controller = JebaoMlwController(
                self.hass,
                device_id,
                device.host,
                device.port,
                self.reconnect_delay,
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


class JebaoMlwController:
    """Maintain one persistent connection with automatic reconnect."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        host: str,
        port: int,
        reconnect_delay: int,
        state_callback,
    ) -> None:
        self.hass = hass
        self.device_id = device_id
        self.host = host
        self.port = port
        self.reconnect_delay = reconnect_delay
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
