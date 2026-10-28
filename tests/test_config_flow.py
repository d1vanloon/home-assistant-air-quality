from __future__ import annotations

from pathlib import Path

from aiohttp import ClientError
from yarl import URL

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.airfire_purple_air.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RADIUS_MILES,
    CONF_SENSOR_ID,
    DOMAIN,
    PAS_CATALOG_URL,
    data_url,
)
from custom_components.airfire_purple_air.model import SensorId

_CATALOG = Path(__file__).parent / "fixtures" / "pas_snippet.csv"
_HOME_LATITUDE = 44.89095
_HOME_LONGITUDE = -123.06918


async def _start(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"
    return result


async def _choose(hass: HomeAssistant, flow_id: str, step_id: str) -> dict:
    return await hass.config_entries.flow.async_configure(
        flow_id, {"next_step_id": step_id}
    )


async def _configure(hass: HomeAssistant, **fields: str) -> dict:
    menu = await _start(hass)
    form = await _choose(hass, menu["flow_id"], "by_id")
    assert form["type"] is FlowResultType.FORM
    assert form["step_id"] == "by_id"
    return await hass.config_entries.flow.async_configure(form["flow_id"], fields)


def _default(schema, name: str):
    for key in schema.schema:
        if getattr(key, "schema", None) == name:
            default = key.default
            if callable(default):
                return default()
            return default
    raise AssertionError(name)


def _sensor_options(schema) -> list[dict[str, str]]:
    for key, validator in schema.schema.items():
        if getattr(key, "schema", None) == CONF_SENSOR_ID:
            return list(validator.config["options"])
    raise AssertionError(list(schema.schema))


def _catalog_gets(aioclient_mock) -> int:
    catalog = URL(PAS_CATALOG_URL)
    return sum(1 for call in aioclient_mock.mock_calls if call[1] == catalog)


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


async def test_menu_offers_nearby_and_sensor_id(hass: HomeAssistant) -> None:
    result = await _start(hass)

    assert list(result["menu_options"]) == ["nearby", "by_id"]


async def test_nearby_flow_creates_entry(
    hass: HomeAssistant, aioclient_mock, sensor_csv: str
) -> None:
    hass.config.latitude = _HOME_LATITUDE
    hass.config.longitude = _HOME_LONGITUDE
    aioclient_mock.get(PAS_CATALOG_URL, text=_CATALOG.read_text(encoding="utf-8"))
    aioclient_mock.get(data_url(SensorId("281078")), text=sensor_csv)

    menu = await _start(hass)
    form = await _choose(hass, menu["flow_id"], "nearby")
    assert form["type"] is FlowResultType.FORM
    assert form["step_id"] == "nearby"
    assert _default(form["data_schema"], CONF_LATITUDE) == _HOME_LATITUDE
    assert _default(form["data_schema"], CONF_LONGITUDE) == _HOME_LONGITUDE
    assert _default(form["data_schema"], CONF_RADIUS_MILES) == 5

    pick = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            CONF_LATITUDE: _HOME_LATITUDE,
            CONF_LONGITUDE: _HOME_LONGITUDE,
            CONF_RADIUS_MILES: 5,
        },
    )
    assert pick["type"] is FlowResultType.FORM
    assert pick["step_id"] == "pick"
    assert _sensor_options(pick["data_schema"]) == [
        {"value": "281078", "label": "281078 · 0.0 mi · PM2.5 3.3"},
        {"value": "281079", "label": "281079 · 1.0 mi"},
    ]

    result = await hass.config_entries.flow.async_configure(
        pick["flow_id"], {CONF_SENSOR_ID: "281078"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Purple Air 281078"
    assert result["data"] == {CONF_SENSOR_ID: "281078"}
    assert result["result"].unique_id == "281078"
    assert _catalog_gets(aioclient_mock) == 1


async def test_nearby_omits_a_configured_sensor(
    hass: HomeAssistant, aioclient_mock, sensor_csv: str
) -> None:
    aioclient_mock.get(PAS_CATALOG_URL, text=_CATALOG.read_text(encoding="utf-8"))
    aioclient_mock.get(data_url(SensorId("281078")), text=sensor_csv)
    created = await _configure(hass, **{CONF_SENSOR_ID: "281078"})
    assert created["type"] is FlowResultType.CREATE_ENTRY

    menu = await _start(hass)
    form = await _choose(hass, menu["flow_id"], "nearby")
    pick = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            CONF_LATITUDE: _HOME_LATITUDE,
            CONF_LONGITUDE: _HOME_LONGITUDE,
            CONF_RADIUS_MILES: 5,
        },
    )

    assert _sensor_options(pick["data_schema"]) == [
        {"value": "281079", "label": "281079 · 1.0 mi"}
    ]


async def test_nearby_empty_result_can_widen_without_a_second_download(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(PAS_CATALOG_URL, text=_CATALOG.read_text(encoding="utf-8"))
    menu = await _start(hass)
    form = await _choose(hass, menu["flow_id"], "nearby")

    empty = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {CONF_LATITUDE: 0, CONF_LONGITUDE: 0, CONF_RADIUS_MILES: 5},
    )
    assert empty["type"] is FlowResultType.FORM
    assert empty["step_id"] == "nearby"
    assert empty["errors"]["base"] == "no_nearby_sensors"

    pick = await hass.config_entries.flow.async_configure(
        empty["flow_id"],
        {
            CONF_LATITUDE: _HOME_LATITUDE,
            CONF_LONGITUDE: _HOME_LONGITUDE,
            CONF_RADIUS_MILES: 5,
        },
    )

    assert pick["step_id"] == "pick"
    assert _catalog_gets(aioclient_mock) == 1
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_nearby_connection_error_stays_on_the_form(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(PAS_CATALOG_URL, exc=ClientError())
    menu = await _start(hass)
    form = await _choose(hass, menu["flow_id"], "nearby")

    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            CONF_LATITUDE: _HOME_LATITUDE,
            CONF_LONGITUDE: _HOME_LONGITUDE,
            CONF_RADIUS_MILES: 5,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "nearby"
    assert result["errors"]["base"] == "cannot_connect"
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_nearby_bad_catalog_stays_on_the_form(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(PAS_CATALOG_URL, text="not,a,catalog\n")
    menu = await _start(hass)
    form = await _choose(hass, menu["flow_id"], "nearby")

    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            CONF_LATITUDE: _HOME_LATITUDE,
            CONF_LONGITUDE: _HOME_LONGITUDE,
            CONF_RADIUS_MILES: 5,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_data"
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_nearby_missing_sensor_file_stays_on_the_pick_form(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(PAS_CATALOG_URL, text=_CATALOG.read_text(encoding="utf-8"))
    aioclient_mock.get(data_url(SensorId("281078")), status=404, text="")
    menu = await _start(hass)
    form = await _choose(hass, menu["flow_id"], "nearby")
    pick = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            CONF_LATITUDE: _HOME_LATITUDE,
            CONF_LONGITUDE: _HOME_LONGITUDE,
            CONF_RADIUS_MILES: 5,
        },
    )

    result = await hass.config_entries.flow.async_configure(
        pick["flow_id"], {CONF_SENSOR_ID: "281078"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pick"
    assert result["errors"]["base"] == "sensor_not_found"
    assert hass.config_entries.async_entries(DOMAIN) == []
