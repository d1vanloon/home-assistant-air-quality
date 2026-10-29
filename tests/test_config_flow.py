from __future__ import annotations

from pathlib import Path

from aiohttp import ClientError
from yarl import URL

from homeassistant import config_entries
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.selector import LocationSelector
from homeassistant.util.unit_conversion import DistanceConverter

from custom_components.airfire_purple_air.const import (
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_SENSOR_ID,
    DOMAIN,
    PAS_CATALOG_URL,
    data_url,
)
from custom_components.airfire_purple_air.model import SensorId

_CATALOG = Path(__file__).parent / "fixtures" / "pas_snippet.csv"
_EMPTY_CATALOG = "sensor_index,latitude,longitude\n"
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


def _radius_meters(miles: float) -> float:
    return float(
        round(
            DistanceConverter.convert(miles, UnitOfLength.MILES, UnitOfLength.METERS)
        )
    )


def _area(latitude: float, longitude: float, miles: float = 5) -> dict[str, float]:
    return {
        CONF_LATITUDE: latitude,
        CONF_LONGITUDE: longitude,
        "radius": _radius_meters(miles),
    }


def _selector(schema, name: str):
    for key, validator in schema.schema.items():
        if getattr(key, "schema", None) == name:
            return validator
    raise AssertionError(list(schema.schema))


def _mock_empty_catalog(aioclient_mock) -> None:
    aioclient_mock.get(PAS_CATALOG_URL, text=_EMPTY_CATALOG)


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
    _mock_empty_catalog(aioclient_mock)
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
    _mock_empty_catalog(aioclient_mock)
    aioclient_mock.get(data_url(SensorId("281078")), text=sensor_csv)

    result = await _configure(hass, **{CONF_SENSOR_ID: " 281078 "})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Purple Air 281078"
    assert result["data"] == {CONF_SENSOR_ID: "281078"}


async def test_second_sensor_creates_a_second_entry(
    hass: HomeAssistant, aioclient_mock, sensor_csv: str
) -> None:
    _mock_empty_catalog(aioclient_mock)
    for sensor_id in ("281078", "281079"):
        aioclient_mock.get(data_url(SensorId(sensor_id)), text=sensor_csv)
        result = await _configure(hass, **{CONF_SENSOR_ID: sensor_id})
        assert result["type"] is FlowResultType.CREATE_ENTRY

    entries = hass.config_entries.async_entries(DOMAIN)
    assert {entry.unique_id for entry in entries} == {"281078", "281079"}


async def test_duplicate_sensor_aborts(
    hass: HomeAssistant, aioclient_mock, sensor_csv: str
) -> None:
    _mock_empty_catalog(aioclient_mock)
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
    selector = _selector(form["data_schema"], CONF_LOCATION)
    assert isinstance(selector, LocationSelector)
    assert selector.config["radius"] is True
    default = _default(form["data_schema"], CONF_LOCATION)
    assert default[CONF_LATITUDE] == _HOME_LATITUDE
    assert default[CONF_LONGITUDE] == _HOME_LONGITUDE
    assert default["radius"] == _radius_meters(5)

    pick = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {CONF_LOCATION: _area(_HOME_LATITUDE, _HOME_LONGITUDE)},
    )
    assert pick["type"] is FlowResultType.FORM
    assert pick["step_id"] == "pick"
    assert _sensor_options(pick["data_schema"]) == [
        {"value": "281078", "label": "281078 · 0.0 mi · PM2.5 3.3"},
        {"value": "281079", "label": "281079 · 1.0 mi"},
    ]
    assert _catalog_gets(aioclient_mock) == 1

    result = await hass.config_entries.flow.async_configure(
        pick["flow_id"], {CONF_SENSOR_ID: "281078"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Purple Air 281078"
    assert result["data"] == {CONF_SENSOR_ID: "281078"}
    assert result["result"].unique_id == "281078"
    # Discovery keeps its own catalog. Setup reads it again for map coordinates.
    assert _catalog_gets(aioclient_mock) == 2


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
        {CONF_LOCATION: _area(_HOME_LATITUDE, _HOME_LONGITUDE)},
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
        {CONF_LOCATION: _area(0, 0)},
    )
    assert empty["type"] is FlowResultType.FORM
    assert empty["step_id"] == "nearby"
    assert empty["errors"]["base"] == "no_nearby_sensors"

    pick = await hass.config_entries.flow.async_configure(
        empty["flow_id"],
        {CONF_LOCATION: _area(_HOME_LATITUDE, _HOME_LONGITUDE)},
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
        {CONF_LOCATION: _area(_HOME_LATITUDE, _HOME_LONGITUDE)},
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
        {CONF_LOCATION: _area(_HOME_LATITUDE, _HOME_LONGITUDE)},
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
        {CONF_LOCATION: _area(_HOME_LATITUDE, _HOME_LONGITUDE)},
    )

    result = await hass.config_entries.flow.async_configure(
        pick["flow_id"], {CONF_SENSOR_ID: "281078"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pick"
    assert result["errors"]["base"] == "sensor_not_found"
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_nearby_uses_a_center_other_than_home(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(PAS_CATALOG_URL, text=_CATALOG.read_text(encoding="utf-8"))
    menu = await _start(hass)
    form = await _choose(hass, menu["flow_id"], "nearby")

    pick = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {CONF_LOCATION: _area(47.6062, -122.3321)},
    )

    assert pick["step_id"] == "pick"
    assert _sensor_options(pick["data_schema"]) == [
        {"value": "999001", "label": "999001 · 0.0 mi · PM2.5 8.0"}
    ]


async def test_nearby_accepts_the_25_mile_circle_and_rejects_one_more_meter(
    hass: HomeAssistant, aioclient_mock
) -> None:
    menu = await _start(hass)
    form = await _choose(hass, menu["flow_id"], "nearby")

    too_wide = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            CONF_LOCATION: {
                CONF_LATITUDE: _HOME_LATITUDE,
                CONF_LONGITUDE: _HOME_LONGITUDE,
                "radius": _radius_meters(25) + 1,
            }
        },
    )

    assert too_wide["type"] is FlowResultType.FORM
    assert too_wide["step_id"] == "nearby"
    assert too_wide["errors"]["location"] == "radius_out_of_range"
    assert _catalog_gets(aioclient_mock) == 0

    aioclient_mock.get(PAS_CATALOG_URL, text=_CATALOG.read_text(encoding="utf-8"))
    pick = await hass.config_entries.flow.async_configure(
        too_wide["flow_id"],
        {CONF_LOCATION: _area(_HOME_LATITUDE, _HOME_LONGITUDE, 25)},
    )

    assert pick["step_id"] == "pick"
    assert [option["value"] for option in _sensor_options(pick["data_schema"])] == [
        "281078",
        "281079",
    ]


async def test_nearby_rejects_a_missing_or_zero_radius(
    hass: HomeAssistant, aioclient_mock
) -> None:
    menu = await _start(hass)
    form = await _choose(hass, menu["flow_id"], "nearby")

    missing = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            CONF_LOCATION: {
                CONF_LATITUDE: _HOME_LATITUDE,
                CONF_LONGITUDE: _HOME_LONGITUDE,
            }
        },
    )

    assert missing["errors"]["location"] == "radius_out_of_range"
    assert _catalog_gets(aioclient_mock) == 0

    zero = await hass.config_entries.flow.async_configure(
        missing["flow_id"],
        {CONF_LOCATION: {**_area(_HOME_LATITUDE, _HOME_LONGITUDE), "radius": 0}},
    )

    assert zero["step_id"] == "nearby"
    assert zero["errors"]["location"] == "radius_out_of_range"
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_nearby_rejects_a_coordinate_outside_the_map(
    hass: HomeAssistant, aioclient_mock
) -> None:
    menu = await _start(hass)
    form = await _choose(hass, menu["flow_id"], "nearby")

    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {CONF_LOCATION: {**_area(0, 0), CONF_LATITUDE: 120}},
    )

    assert result["step_id"] == "nearby"
    assert result["errors"]["location"] == "invalid_location"
    assert _catalog_gets(aioclient_mock) == 0
    assert hass.config_entries.async_entries(DOMAIN) == []
