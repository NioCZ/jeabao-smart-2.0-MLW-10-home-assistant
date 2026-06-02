"""Base entity helpers for the Jebao MLW local integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import JebaoMlwController, JebaoMlwCoordinator


class JebaoMlwEntity(CoordinatorEntity[JebaoMlwCoordinator]):
    """Base entity for one configured pump."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: JebaoMlwCoordinator, device_id: str, key: str, name: str) -> None:
        super().__init__(coordinator)
        self.device_id = device_id
        self.device = coordinator.devices[device_id]
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_name = name

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant device metadata."""

        info: DeviceInfo = {
            "identifiers": {(DOMAIN, self.device.id)},
            "manufacturer": MANUFACTURER,
            "model": self.device.model,
            "name": self.device.name,
        }
        if self.device.version:
            info["sw_version"] = self.device.version
        return info

    @property
    def available(self) -> bool:
        """Return true when the pump TCP connection is alive."""

        return bool(self.state_data and self.state_data.connected)

    @property
    def state_data(self):
        """Return the latest state for this pump."""

        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.device_id)

    @property
    def controller(self) -> JebaoMlwController:
        """Return the runtime controller for this pump."""

        return self.coordinator.controllers[self.device_id]
