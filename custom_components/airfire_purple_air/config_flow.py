from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import UnitOfLength
from homeassistant.helpers import aiohttp_client
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    LocationSelector,
    LocationSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util.unit_conversion import DistanceConverter

from .client import CannotConnect, SensorNotFound, fetch_catalog, fetch_latest
from .const import (
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_SENSOR_ID,
    DEFAULT_RADIUS_MILES,
    DOMAIN,
    MAX_RADIUS_MILES,
)
from .model import (
    AirFireError,
    CatalogSensor,
    InvalidCatalog,
    InvalidReading,
    NearbySensor,
    SensorId,
    nearby,
    nearby_label,
)

# The location selector calls this field "radius" and stores it in meters.
_SELECTOR_RADIUS = "radius"

BY_ID_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SENSOR_ID): cv.string,
        vol.Optional(CONF_NAME): cv.string,
    }
)


def _error_key(err: AirFireError) -> str:
    if isinstance(err, SensorNotFound):
        return "sensor_not_found"
    if isinstance(err, (InvalidReading, InvalidCatalog)):
        return "invalid_data"
    if isinstance(err, CannotConnect):
        return "cannot_connect"
    raise TypeError(f"Unhandled AirFire error {type(err).__name__}")


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _whole_meters(miles: float) -> float:
    # The map UI rounds the radius to a whole meter.
    return float(
        round(
            DistanceConverter.convert(miles, UnitOfLength.MILES, UnitOfLength.METERS)
        )
    )


def _radius_miles(radius_meters: float) -> float | None:
    if radius_meters <= 0:
        return None
    if radius_meters > _whole_meters(MAX_RADIUS_MILES):
        return None
    return DistanceConverter.convert(
        radius_meters, UnitOfLength.METERS, UnitOfLength.MILES
    )


def _search_area(location: object) -> tuple[float, float, float] | str:
    if not isinstance(location, Mapping):
        return "invalid_location"
    latitude = _as_float(location.get(CONF_LATITUDE))
    longitude = _as_float(location.get(CONF_LONGITUDE))
    if (
        latitude is None
        or longitude is None
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return "invalid_location"
    radius_meters = _as_float(location.get(_SELECTOR_RADIUS))
    if radius_meters is None:
        return "radius_out_of_range"
    radius_miles = _radius_miles(radius_meters)
    if radius_miles is None:
        return "radius_out_of_range"
    return (latitude, longitude, radius_miles)


class AirFirePurpleAirConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._catalog: tuple[CatalogSensor, ...] | None = None
        self._matches: tuple[NearbySensor, ...] = ()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="user",
            menu_options=["nearby", "by_id"],
        )

    async def async_step_by_id(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                sensor_id = SensorId(user_input[CONF_SENSOR_ID])
            except ValueError:
                errors[CONF_SENSOR_ID] = "invalid_sensor_id"
            else:
                name = user_input.get(CONF_NAME) or ""
                try:
                    return await self._async_create_from_sensor(sensor_id, name)
                except AirFireError as err:
                    errors["base"] = _error_key(err)

        schema = BY_ID_SCHEMA
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(BY_ID_SCHEMA, user_input)
        return self.async_show_form(step_id="by_id", data_schema=schema, errors=errors)

    async def async_step_nearby(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            area = _search_area(user_input.get(CONF_LOCATION))
            if isinstance(area, str):
                errors[CONF_LOCATION] = area
            else:
                error = await self._async_collect_matches(area)
                if error is None:
                    return await self.async_step_pick()
                errors["base"] = error

        schema = self._nearby_schema()
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="nearby", data_schema=schema, errors=errors)

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                sensor_id = SensorId(user_input[CONF_SENSOR_ID])
            except ValueError:
                errors[CONF_SENSOR_ID] = "invalid_sensor_id"
            else:
                try:
                    return await self._async_create_from_sensor(sensor_id, "")
                except AirFireError as err:
                    errors["base"] = _error_key(err)

        return self.async_show_form(
            step_id="pick",
            data_schema=self._pick_schema(),
            errors=errors,
        )

    async def _async_collect_matches(
        self, area: tuple[float, float, float]
    ) -> str | None:
        latitude, longitude, radius_miles = area
        try:
            catalog = await self._async_catalog()
        except AirFireError as err:
            return _error_key(err)
        configured = self._configured_sensor_ids()
        matches = [
            sensor
            for sensor in nearby(catalog, latitude, longitude, radius_miles)
            if sensor.sensor_index not in configured
        ]
        if not matches:
            return "no_nearby_sensors"
        self._matches = tuple(matches)
        return None

    async def _async_catalog(self) -> tuple[CatalogSensor, ...]:
        if self._catalog is not None:
            return self._catalog
        catalog = await fetch_catalog(
            aiohttp_client.async_get_clientsession(self.hass)
        )
        self._catalog = catalog
        return catalog

    def _configured_sensor_ids(self) -> set[str]:
        return {
            entry.unique_id
            for entry in self._async_current_entries()
            if entry.unique_id is not None
        }

    def _default_location(self) -> dict[str, float]:
        return {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            _SELECTOR_RADIUS: _whole_meters(DEFAULT_RADIUS_MILES),
        }

    def _nearby_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(
                    CONF_LOCATION, default=self._default_location()
                ): LocationSelector(LocationSelectorConfig(radius=True)),
            }
        )

    def _pick_schema(self) -> vol.Schema:
        options: list[SelectOptionDict] = [
            SelectOptionDict(value=sensor.sensor_index, label=nearby_label(sensor))
            for sensor in self._matches
        ]
        return vol.Schema(
            {
                vol.Required(CONF_SENSOR_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

    async def _async_create_from_sensor(
        self, sensor_id: SensorId, name: str
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(sensor_id)
        self._abort_if_unique_id_configured()
        await fetch_latest(
            aiohttp_client.async_get_clientsession(self.hass),
            sensor_id,
        )
        title = name.strip() or f"Purple Air {sensor_id}"
        return self.async_create_entry(
            title=title,
            data={CONF_SENSOR_ID: sensor_id},
        )
