"""Button entities for Jebao MLW pumps."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import JebaoMlwCoordinator
from .entity import JebaoMlwEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up button entities."""

    coordinator: JebaoMlwCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        JebaoMlwFeedButton(coordinator, device_id)
        for device_id in coordinator.devices
    )


class JebaoMlwFeedButton(JebaoMlwEntity, ButtonEntity):
    """Start feed mode."""

    _attr_icon = "mdi:fish-food"

    def __init__(self, coordinator: JebaoMlwCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "feed", "Start feed mode")

    async def async_press(self) -> None:
        """Start feed mode."""

        await self.controller.async_start_feed()
