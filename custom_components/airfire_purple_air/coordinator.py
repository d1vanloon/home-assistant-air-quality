from __future__ import annotations

import asyncio
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import fetch_catalog, fetch_latest
from .const import CONF_SENSOR_ID, DOMAIN, LOGGER, SCAN_INTERVAL
from .model import (
    AirFireError,
    AirFireReading,
    CatalogSensor,
    SensorId,
    coordinates_for,
)

type AirFireConfigEntry = ConfigEntry[AirFireCoordinator]


@dataclass
class _CatalogCache:
    lock: asyncio.Lock
    sensors: tuple[CatalogSensor, ...] | None = None


def _catalog_cache(hass: HomeAssistant) -> _CatalogCache:
    cached = hass.data.get(DOMAIN)
    if isinstance(cached, _CatalogCache):
        return cached
    cache = _CatalogCache(lock=asyncio.Lock())
    hass.data[DOMAIN] = cache
    return cache


async def async_cached_catalog(hass: HomeAssistant) -> tuple[CatalogSensor, ...]:
    cache = _catalog_cache(hass)
    async with cache.lock:
        if cache.sensors is None:
            cache.sensors = await fetch_catalog(async_get_clientsession(hass))
        return cache.sensors


class AirFireCoordinator(DataUpdateCoordinator[AirFireReading]):
    config_entry: AirFireConfigEntry

    def __init__(self, hass: HomeAssistant, entry: AirFireConfigEntry) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=SCAN_INTERVAL,
        )
        self.sensor_id = SensorId(entry.data[CONF_SENSOR_ID])
        # pas.csv is the only feed with coordinates. The ten-minute file has none.
        self.latitude: float | None = None
        self.longitude: float | None = None

    async def _async_update_data(self) -> AirFireReading:
        try:
            reading = await fetch_latest(
                async_get_clientsession(self.hass), self.sensor_id
            )
        except AirFireError as err:
            raise UpdateFailed(f"{self.sensor_id}: {err}") from err
        await self._async_load_coordinates()
        return reading

    async def _async_load_coordinates(self) -> None:
        if self.latitude is not None and self.longitude is not None:
            return
        try:
            catalog = await async_cached_catalog(self.hass)
        except AirFireError:
            LOGGER.debug("Catalog coordinates unavailable for %s", self.sensor_id)
            return
        found = coordinates_for(catalog, self.sensor_id)
        if found is None:
            return
        self.latitude, self.longitude = found
