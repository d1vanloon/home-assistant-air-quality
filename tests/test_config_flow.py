from __future__ import annotations

from aiohttp import ClientError

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.airfire_purple_air.const import (
    CONF_NAME,
    CONF_SENSOR_ID,
    DOMAIN,
    data_url,
)
from custom_components.airfire_purple_air.model import SensorId


async def _configure(hass: HomeAssistant, **fields: str) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], fields)


async def test_user_flow_creates_entry(
    hass: HomeAssistant, aioclient_mock, sensor_csv: str
) -> None:
    aioclient_mock.get(data_url(SensorId("281078")), text=sensor_csv)

    result = await _configure(
        hass, **{CONF_SENSOR_ID: "281078", CONF_NAME: "Backyard"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Backyard"
    assert result["data"] == {CONF_SENSOR_ID: "281078"}
    assert result["result"].unique_id == "281078"


async def test_user_flow_defaults_the_title(
    hass: HomeAssistant, aioclient_mock, sensor_csv: str
) -> None:
    aioclient_mock.get(data_url(SensorId("281078")), text=sensor_csv)

    result = await _configure(hass, **{CONF_SENSOR_ID: " 281078 "})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Purple Air 281078"
    assert result["data"] == {CONF_SENSOR_ID: "281078"}


async def test_second_sensor_creates_a_second_entry(
    hass: HomeAssistant, aioclient_mock, sensor_csv: str
) -> None:
    for sensor_id in ("281078", "281079"):
        aioclient_mock.get(data_url(SensorId(sensor_id)), text=sensor_csv)
        result = await _configure(hass, **{CONF_SENSOR_ID: sensor_id})
        assert result["type"] is FlowResultType.CREATE_ENTRY

    entries = hass.config_entries.async_entries(DOMAIN)
    assert {entry.unique_id for entry in entries} == {"281078", "281079"}


async def test_duplicate_sensor_aborts(
    hass: HomeAssistant, aioclient_mock, sensor_csv: str
) -> None:
    aioclient_mock.get(data_url(SensorId("281078")), text=sensor_csv)
    created = await _configure(hass, **{CONF_SENSOR_ID: "281078"})
    assert created["type"] is FlowResultType.CREATE_ENTRY

    result = await _configure(hass, **{CONF_SENSOR_ID: "281078"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_missing_sensor_stays_on_the_form(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(data_url(SensorId("281078")), status=404, text="")

    result = await _configure(hass, **{CONF_SENSOR_ID: "281078"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "sensor_not_found"


async def test_empty_csv_stays_on_the_form(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(
        data_url(SensorId("281078")),
        text="pm25,local_ts\n",
    )

    result = await _configure(hass, **{CONF_SENSOR_ID: "281078"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_data"


async def test_non_digit_sensor_id_stays_on_the_form(hass: HomeAssistant) -> None:
    result = await _configure(hass, **{CONF_SENSOR_ID: "abc"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["sensor_id"] == "invalid_sensor_id"
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_connection_error_stays_on_the_form(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(data_url(SensorId("281078")), exc=ClientError())

    result = await _configure(hass, **{CONF_SENSOR_ID: "281078"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"
