"""Number entities for Jebao MLW pumps."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import (
    FREQUENCY_MODES,
    MAX_FEED_DURATION,
    MAX_FLOW,
    MAX_FREQUENCY,
    MIN_FEED_DURATION,
    MIN_FLOW,
    MIN_FREQUENCY,
)
from .const import DOMAIN
from .coordinator import JebaoMlwCoordinator
from .entity import JebaoMlwEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up number entities."""

    coordinator: JebaoMlwCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for device_id in coordinator.devices:
        entities.extend(
            (
                JebaoMlwFlowNumber(coordinator, device_id),
                JebaoMlwFrequencyNumber(coordinator, device_id),
                JebaoMlwFeedDurationNumber(coordinator, device_id),
            )
        )
    async_add_entities(entities)


class JebaoMlwFlowNumber(JebaoMlwEntity, NumberEntity):
    """Flow percentage control."""

    _attr_icon = "mdi:fan-speed-3"
    _attr_native_min_value = MIN_FLOW
    _attr_native_max_value = MAX_FLOW
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: JebaoMlwCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "flow", "Flow")

    @property
    def native_value(self) -> int | None:
        """Return the latest flow value."""

        if self.state_data is None:
            return None
        return self.state_data.flow

    async def async_set_native_value(self, value: float) -> None:
        """Set pump flow."""

        await self.controller.async_set_flow(value)


class JebaoMlwFrequencyNumber(JebaoMlwEntity, NumberEntity):
    """Frequency control for pulse/cross/sine modes."""

    _attr_icon = "mdi:sine-wave"
    _attr_native_min_value = MIN_FREQUENCY
    _attr_native_max_value = MAX_FREQUENCY
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "Hz"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: JebaoMlwCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "frequency", "Frequency")

    @property
    def available(self) -> bool:
        """Return true when current mode uses frequency."""

        if not super().available:
            return False
        return self.state_data.mode in FREQUENCY_MODES

    @property
    def native_value(self) -> int | None:
        """Return latest frequency value."""

        if self.state_data is None:
            return None
        return self.state_data.frequency

    async def async_set_native_value(self, value: float) -> None:
        """Set pump frequency."""

        await self.controller.async_set_frequency(value)


class JebaoMlwFeedDurationNumber(JebaoMlwEntity, NumberEntity):
    """Feed mode duration used by the feed button."""

    _attr_icon = "mdi:timer-cog-outline"
    _attr_native_min_value = MIN_FEED_DURATION
    _attr_native_max_value = MAX_FEED_DURATION
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: JebaoMlwCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "feed_duration", "Feed duration")

    @property
    def native_value(self) -> int:
        """Return configured feed duration."""

        return self.controller.feed_duration

    async def async_set_native_value(self, value: float) -> None:
        """Store feed duration for the next feed command."""

        self.controller.async_set_feed_duration(value)
        self.async_write_ha_state()
