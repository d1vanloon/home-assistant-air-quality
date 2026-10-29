from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp import ClientError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    UnitOfDensity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.airfire_purple_air.client import CannotConnect
from custom_components.airfire_purple_air.const import (
    CONF_SENSOR_ID,
    DOMAIN,
    PAS_CATALOG_URL,
    data_url,
)
from custom_components.airfire_purple_air.coordinator import async_cached_catalog
from custom_components.airfire_purple_air.model import SensorId, parse_catalog

_CATALOG = Path(__file__).parent / "fixtures" / "pas_snippet.csv"


@pytest.fixture(autouse=True)
def _catalog(aioclient_mock) -> None:
    aioclient_mock.get(PAS_CATALOG_URL, text=_CATALOG.read_text(encoding="utf-8"))


def _catalog_gets(aioclient_mock) -> int:
    catalog = URL(PAS_CATALOG_URL)
    return sum(1 for call in aioclient_mock.mock_calls if call[1] == catalog)


def _entry(sensor_id: str, title: str | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=sensor_id,
        title=title or f"Purple Air {sensor_id}",
        data={CONF_SENSOR_ID: sensor_id},
    )


def _entity_id(hass: HomeAssistant, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


async def test_pm25_state_is_the_latest_csv_row(
    hass: HomeAssistant, aioclient_mock, sensor_csv: str
) -> None:
    aioclient_mock.get(data_url(SensorId("281078")), text=sensor_csv)
    entry = _entry("281078")
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass, "281078_pm25"))
    assert state is not None
    assert state.state == "3.3"
    assert (
        state.attributes[ATTR_UNIT_OF_MEASUREMENT]
        == UnitOfDensity.MICROGRAMS_PER_CUBIC_METER
    )
    assert state.attributes[ATTR_DEVICE_CLASS] == "pm25"
    assert state.attributes["sampled_at"] == "2026-10-28T00:05:06-05:00"

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, "281078"), entry.entry_id
    )
    assert device is not None
    assert device.name == "Purple Air 281078"


async def test_two_sensors_create_two_devices(
    hass: HomeAssistant, aioclient_mock, sensor_csv: str
) -> None:
    entries = []
    for sensor_id in ("281078", "42"):
        aioclient_mock.get(data_url(SensorId(sensor_id)), text=sensor_csv)
        entry = _entry(sensor_id)
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        entries.append(entry)
    await hass.async_block_till_done()

    registry = dr.async_get(hass)
    names = {
        device.name
        for entry in entries
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert names == {"Purple Air 281078", "Purple Air 42"}
    assert hass.states.get(_entity_id(hass, "281078_pm25")).state == "3.3"
    assert hass.states.get(_entity_id(hass, "42_pm25")).state == "3.3"


async def test_unknown_numeric_column_becomes_a_sensor(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(
        data_url(SensorId("281078")),
        text="pm25,voc,local_ts\n3.3,12,2026-10-28 00:05:06-0500\n",
    )
    entry = _entry("281078")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass, "281078_voc"))
    assert state is not None
    assert state.state == "12.0"
    assert state.attributes.get(ATTR_DEVICE_CLASS) is None
    assert ATTR_UNIT_OF_MEASUREMENT not in state.attributes


async def test_new_csv_column_adds_a_sensor(
    hass: HomeAssistant, aioclient_mock
) -> None:
    url = data_url(SensorId("281078"))
    aioclient_mock.get(
        url,
        text="pm25,local_ts\n1.5,2026-10-28 00:05:06-0500\n",
    )
    entry = _entry("281078")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get_entity_id("sensor", DOMAIN, "281078_pm10") is None

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        url,
        text="pm25,pm10,local_ts\n2.5,8,2026-10-28 00:15:06-0500\n",
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    pm10 = hass.states.get(_entity_id(hass, "281078_pm10"))
    assert pm10 is not None
    assert pm10.state == "8.0"
    assert hass.states.get(_entity_id(hass, "281078_pm25")).state == "2.5"


async def test_factor_entities_expose_catalog_coordinates(
    hass: HomeAssistant, aioclient_mock
) -> None:
    reading = "pm25,voc,local_ts\n3.3,1.5,2026-10-28 00:05:06-0500\n"
    entries = []
    for sensor_id in ("281078", "281079"):
        aioclient_mock.get(data_url(SensorId(sensor_id)), text=reading)
        entry = _entry(sensor_id)
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        entries.append(entry)
    await hass.async_block_till_done()

    for unique_id in ("281078_pm25", "281078_voc"):
        state = hass.states.get(_entity_id(hass, unique_id))
        assert state is not None
        assert state.attributes["latitude"] == 44.89095
        assert state.attributes["longitude"] == -123.06918
        assert state.attributes["sampled_at"] == "2026-10-28T00:05:06-05:00"
    other = hass.states.get(_entity_id(hass, "281079_pm25"))
    assert other is not None
    assert other.attributes["latitude"] == 44.905
    assert other.attributes["longitude"] == -123.06918
    assert entries[0].data == {CONF_SENSOR_ID: "281078"}
    assert entries[1].data == {CONF_SENSOR_ID: "281079"}
    assert _catalog_gets(aioclient_mock) == 1

    await entries[0].runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _catalog_gets(aioclient_mock) == 1


async def test_sensor_missing_from_the_catalog_has_no_coordinates(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        PAS_CATALOG_URL,
        text="sensor_index,latitude,longitude\n1,0,0\n",
    )
    aioclient_mock.get(
        data_url(SensorId("281078")),
        text="pm25,local_ts\n3.3,2026-10-28 00:05:06-0500\n",
    )
    entry = _entry("281078")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass, "281078_pm25"))
    assert state is not None
    assert state.state == "3.3"
    assert "latitude" not in state.attributes
    assert "longitude" not in state.attributes
    assert state.attributes["sampled_at"] == "2026-10-28T00:05:06-05:00"
    assert entry.data == {CONF_SENSOR_ID: "281078"}


async def test_coordinates_appear_when_the_catalog_recovers(
    hass: HomeAssistant, aioclient_mock
) -> None:
    url = data_url(SensorId("281078"))
    reading = "pm25,local_ts\n3.3,2026-10-28 00:05:06-0500\n"
    aioclient_mock.clear_requests()
    aioclient_mock.get(PAS_CATALOG_URL, exc=ClientError())
    aioclient_mock.get(url, text=reading)
    entry = _entry("281078")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass, "281078_pm25"))
    assert state is not None
    assert state.state == "3.3"
    assert "latitude" not in state.attributes

    aioclient_mock.clear_requests()
    aioclient_mock.get(PAS_CATALOG_URL, text=_CATALOG.read_text(encoding="utf-8"))
    aioclient_mock.get(url, text=reading)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass, "281078_pm25"))
    assert state is not None
    assert state.attributes["latitude"] == 44.89095
    assert state.attributes["longitude"] == -123.06918
    assert _catalog_gets(aioclient_mock) == 1


async def test_concurrent_catalog_failures_share_one_request(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def fail_together(_session):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        raise CannotConnect("down")

    monkeypatch.setattr(
        "custom_components.airfire_purple_air.coordinator.fetch_catalog",
        fail_together,
    )
    first = asyncio.create_task(async_cached_catalog(hass))
    await asyncio.sleep(0)
    second = asyncio.create_task(async_cached_catalog(hass))
    results = await asyncio.gather(first, second, return_exceptions=True)

    assert calls == 1
    assert all(isinstance(result, CannotConnect) for result in results)

    async def succeed(_session):
        nonlocal calls
        calls += 1
        return parse_catalog(_CATALOG.read_text(encoding="utf-8"))

    monkeypatch.setattr(
        "custom_components.airfire_purple_air.coordinator.fetch_catalog",
        succeed,
    )
    catalog = await async_cached_catalog(hass)

    assert calls == 2
    assert catalog[0].sensor_index == "281078"
    assert catalog[0].latitude == 44.89095


async def test_cancelling_one_catalog_waiter_leaves_the_download_running(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def wait_then_catalog(_session):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return parse_catalog(_CATALOG.read_text(encoding="utf-8"))

    monkeypatch.setattr(
        "custom_components.airfire_purple_air.coordinator.fetch_catalog",
        wait_then_catalog,
    )
    first = asyncio.create_task(async_cached_catalog(hass))
    await started.wait()
    second = asyncio.create_task(async_cached_catalog(hass))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    catalog = await second

    assert calls == 1
    assert catalog[0].sensor_index == "281078"
    assert catalog[0].latitude == 44.89095
    assert (await async_cached_catalog(hass))[0].sensor_index == "281078"
    assert calls == 1
