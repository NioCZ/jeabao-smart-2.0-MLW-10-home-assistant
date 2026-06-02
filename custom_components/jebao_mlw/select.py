"""Select entities for Jebao MLW modes."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MODE_BY_LABEL, MODE_LABELS
from .const import DOMAIN
from .coordinator import JebaoMlwCoordinator
from .entity import JebaoMlwEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up select entities."""

    coordinator: JebaoMlwCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        JebaoMlwModeSelect(coordinator, device_id)
        for device_id in coordinator.devices
    )


class JebaoMlwModeSelect(JebaoMlwEntity, SelectEntity):
    """Wave mode selector."""

    _attr_icon = "mdi:tune-variant"
    _attr_options = MODE_LABELS

    def __init__(self, coordinator: JebaoMlwCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "mode", "Mode")

    @property
    def current_option(self) -> str | None:
        """Return the current mode label."""

        if self.state_data is None:
            return None
        return self.state_data.mode_label

    async def async_select_option(self, option: str) -> None:
        """Set a new wave mode."""

        await self.controller.async_set_mode(MODE_BY_LABEL[option])
