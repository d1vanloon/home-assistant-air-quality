from __future__ import annotations

from collections.abc import Mapping

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityStateAttribute, UnitOfDensity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AirFireConfigEntry, AirFireCoordinator
from .entity import AirFireEntity

FACTOR_META: Mapping[str, SensorEntityDescription] = {
    "pm25": SensorEntityDescription(
        key="pm25",
        name="PM2.5",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
}


def description_for(factor: str) -> SensorEntityDescription:
    known = FACTOR_META.get(factor)
    if known is not None:
        return known
    return SensorEntityDescription(
        key=factor,
        name=factor,
        state_class=SensorStateClass.MEASUREMENT,
    )


class AirFireFactorSensor(AirFireEntity, SensorEntity):
    def __init__(self, coordinator: AirFireCoordinator, factor: str) -> None:
        super().__init__(coordinator)
        self.entity_description = description_for(factor)
        self._attr_unique_id = f"{coordinator.sensor_id}_{factor}"

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.entity_description.key in self.coordinator.data.factors
        )

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.factors.get(self.entity_description.key)

    @property
    def extra_state_attributes(self) -> Mapping[str, str | float]:
        attributes: dict[str, str | float] = {
            "sampled_at": self.coordinator.data.timestamp.isoformat(),
        }
        latitude = self.coordinator.latitude
        longitude = self.coordinator.longitude
        if latitude is not None and longitude is not None:
            attributes[EntityStateAttribute.LATITUDE] = latitude
            attributes[EntityStateAttribute.LONGITUDE] = longitude
        return attributes


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirFireConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    seen: set[str] = set()

    @callback
    def _add_new_factors() -> None:
        fresh = [key for key in coordinator.data.factors if key not in seen]
        if not fresh:
            return
        seen.update(fresh)
        async_add_entities(AirFireFactorSensor(coordinator, key) for key in fresh)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_factors))
    _add_new_factors()
