"""Binary sensors for Jebao MLW pumps."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import JebaoMlwCoordinator
from .entity import JebaoMlwEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up binary sensors."""

    coordinator: JebaoMlwCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        JebaoMlwConnectionBinarySensor(coordinator, device_id)
        for device_id in coordinator.devices
    )


class JebaoMlwConnectionBinarySensor(JebaoMlwEntity, BinarySensorEntity):
    """Connection status sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: JebaoMlwCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "connected", "Connected")

    @property
    def available(self) -> bool:
        """The connection entity itself is always available."""

        return True

    @property
    def is_on(self) -> bool:
        """Return current connection state."""

        return bool(self.state_data and self.state_data.connected)
