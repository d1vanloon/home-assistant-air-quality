from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AirFireCoordinator


class AirFireEntity(CoordinatorEntity[AirFireCoordinator]):
    _attr_has_entity_name = True
    _attr_attribution = "AirNow Fire and Smoke Map"

    def __init__(self, coordinator: AirFireCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.sensor_id)},
            name=entry.title,
            manufacturer="PurpleAir",
            model="PurpleAir",
        )
