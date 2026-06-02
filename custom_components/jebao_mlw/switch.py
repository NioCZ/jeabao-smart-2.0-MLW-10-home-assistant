"""Switch entities for Jebao MLW pumps."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import JebaoMlwCoordinator
from .entity import JebaoMlwEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up switches."""

    coordinator: JebaoMlwCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        JebaoMlwPumpSwitch(coordinator, device_id)
        for device_id in coordinator.devices
    )


class JebaoMlwPumpSwitch(JebaoMlwEntity, SwitchEntity):
    """Main pump motor switch."""

    _attr_icon = "mdi:waves-arrow-right"

    def __init__(self, coordinator: JebaoMlwCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "power", "Pump")

    @property
    def is_on(self) -> bool | None:
        """Return true when the pump reports motor on."""

        if self.state_data is None:
            return None
        return self.state_data.is_on

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the pump on."""

        await self.controller.async_turn_on()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the pump off."""

        await self.controller.async_turn_off()
