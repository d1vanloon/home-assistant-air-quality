from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import aiohttp_client
import homeassistant.helpers.config_validation as cv

from .client import CannotConnect, SensorNotFound, fetch_latest
from .const import CONF_NAME, CONF_SENSOR_ID, DOMAIN
from .model import AirFireError, InvalidReading, SensorId

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SENSOR_ID): cv.string,
        vol.Optional(CONF_NAME): cv.string,
    }
)


def _error_key(err: AirFireError) -> str:
    if isinstance(err, SensorNotFound):
        return "sensor_not_found"
    if isinstance(err, InvalidReading):
        return "invalid_data"
    if isinstance(err, CannotConnect):
        return "cannot_connect"
    raise TypeError(f"Unhandled AirFire error {type(err).__name__}")


class AirFirePurpleAirConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                sensor_id = SensorId(user_input[CONF_SENSOR_ID])
            except ValueError:
                errors[CONF_SENSOR_ID] = "invalid_sensor_id"
            else:
                await self.async_set_unique_id(sensor_id)
                self._abort_if_unique_id_configured()
                try:
                    await fetch_latest(
                        aiohttp_client.async_get_clientsession(self.hass),
                        sensor_id,
                    )
                except AirFireError as err:
                    errors["base"] = _error_key(err)
                else:
                    name = (user_input.get(CONF_NAME) or "").strip()
                    return self.async_create_entry(
                        title=name or f"Purple Air {sensor_id}",
                        data={CONF_SENSOR_ID: sensor_id},
                    )

        schema = USER_SCHEMA
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(USER_SCHEMA, user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
