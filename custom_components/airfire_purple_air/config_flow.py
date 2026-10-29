from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import UnitOfLength
from homeassistant.helpers import aiohttp_client
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .client import CannotConnect, SensorNotFound, fetch_catalog, fetch_latest
from .const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RADIUS_MILES,
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
            try:
                catalog = await self._async_catalog()
            except AirFireError as err:
                errors["base"] = _error_key(err)
            else:
                matches = self._matches_for(user_input, catalog)
                if not matches:
                    errors["base"] = "no_nearby_sensors"
                else:
                    self._matches = tuple(matches)
                    return await self.async_step_pick()

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

    async def _async_catalog(self) -> tuple[CatalogSensor, ...]:
        if self._catalog is not None:
            return self._catalog
        catalog = await fetch_catalog(
            aiohttp_client.async_get_clientsession(self.hass)
        )
        self._catalog = catalog
        return catalog

    def _matches_for(
        self, user_input: dict[str, Any], catalog: tuple[CatalogSensor, ...]
    ) -> list[NearbySensor]:
        configured = self._configured_sensor_ids()
        return [
            sensor
            for sensor in nearby(
                catalog,
                float(user_input[CONF_LATITUDE]),
                float(user_input[CONF_LONGITUDE]),
                float(user_input[CONF_RADIUS_MILES]),
            )
            if sensor.sensor_index not in configured
        ]

    def _configured_sensor_ids(self) -> set[str]:
        return {
            entry.unique_id
            for entry in self._async_current_entries()
            if entry.unique_id is not None
        }

    def _nearby_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(
                    CONF_LATITUDE, default=self.hass.config.latitude
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=-90,
                        max=90,
                        step="any",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_LONGITUDE, default=self.hass.config.longitude
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=-180,
                        max=180,
                        step="any",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_RADIUS_MILES, default=DEFAULT_RADIUS_MILES
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0.1,
                        max=MAX_RADIUS_MILES,
                        step=0.1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement=UnitOfLength.MILES,
                    )
                ),
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
