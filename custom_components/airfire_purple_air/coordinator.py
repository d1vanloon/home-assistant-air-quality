from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import fetch_latest
from .const import CONF_SENSOR_ID, LOGGER, SCAN_INTERVAL
from .model import AirFireError, AirFireReading, SensorId

type AirFireConfigEntry = ConfigEntry[AirFireCoordinator]


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

    async def _async_update_data(self) -> AirFireReading:
        try:
            return await fetch_latest(
                async_get_clientsession(self.hass), self.sensor_id
            )
        except AirFireError as err:
            raise UpdateFailed(f"{self.sensor_id}: {err}") from err
