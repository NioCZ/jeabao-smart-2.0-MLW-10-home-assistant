"""Sensor entities for Jebao MLW pumps."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import JebaoMlwCoordinator
from .entity import JebaoMlwEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors."""

    coordinator: JebaoMlwCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for device_id in coordinator.devices:
        entities.extend(
            (
                JebaoMlwFeedRemainingSensor(coordinator, device_id),
                JebaoMlwLastSeenSensor(coordinator, device_id),
                JebaoMlwRawModeSensor(coordinator, device_id),
            )
        )
    async_add_entities(entities)


class JebaoMlwFeedRemainingSensor(JebaoMlwEntity, SensorEntity):
    """Remaining feed time sensor."""

    _attr_icon = "mdi:timer-sand"
    _attr_native_unit_of_measurement = "min"

    def __init__(self, coordinator: JebaoMlwCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "feed_remaining", "Feed remaining")

    @property
    def native_value(self) -> int | None:
        """Return remaining feed time in minutes."""

        if self.state_data is None:
            return None
        return self.state_data.feed_time_left


class JebaoMlwLastSeenSensor(JebaoMlwEntity, SensorEntity):
    """Timestamp of the latest status frame."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: JebaoMlwCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "last_seen", "Last seen")

    @property
    def native_value(self):
        """Return latest status timestamp."""

        if self.state_data is None:
            return None
        return self.state_data.last_seen


class JebaoMlwRawModeSensor(JebaoMlwEntity, SensorEntity):
    """Diagnostic raw mode byte."""

    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:code-hexadecimal"

    def __init__(self, coordinator: JebaoMlwCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "raw_mode", "Raw mode")

    @property
    def native_value(self) -> str | None:
        """Return raw mode byte as hex."""

        if self.state_data is None or self.state_data.raw_mode is None:
            return None
        return f"0x{self.state_data.raw_mode:02x}"
