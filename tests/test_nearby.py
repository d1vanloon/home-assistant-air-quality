from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.airfire_purple_air.model import (
    CatalogSensor,
    InvalidCatalog,
    SensorId,
    coordinates_for,
    nearby,
    nearby_label,
    parse_catalog,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "pas_snippet.csv"
_HOME = (44.89095, -123.06918)


def _sensor(
    sensor_index: str,
    latitude: float,
    longitude: float,
    pm25: float | None = None,
) -> CatalogSensor:
    return CatalogSensor(
        sensor_index=SensorId(sensor_index),
        latitude=latitude,
        longitude=longitude,
        pm25=pm25,
    )


def test_parse_catalog_keeps_usable_rows_and_a_blank_pm() -> None:
    sensors = parse_catalog(_FIXTURE.read_text(encoding="utf-8"))

    assert [sensor.sensor_index for sensor in sensors] == [
        "281078",
        "281079",
        "999001",
    ]
    assert sensors[0].pm25 == 3.3
    assert sensors[1].pm25 is None
    assert sensors[2].pm25 == 8.0


def test_parse_catalog_keeps_a_zero_pm_and_drops_a_non_finite_pm() -> None:
    text = (
        "sensor_index,latitude,longitude,epa_pm25\n"
        "10,0,0,0\n"
        "11,0,1,nan\n"
        "12,1,0,inf\n"
    )
    sensors = {sensor.sensor_index: sensor.pm25 for sensor in parse_catalog(text)}

    assert sensors == {"10": 0.0, "11": None, "12": None}


def test_parse_catalog_keeps_the_first_row_for_a_duplicate_id() -> None:
    text = "sensor_index,latitude,longitude,epa_pm25\n5,0,0,1\n5,10,10,9\n"
    sensors = parse_catalog(text)

    assert len(sensors) == 1
    assert sensors[0].latitude == 0
    assert sensors[0].pm25 == 1


def test_parse_catalog_rejects_a_file_without_sensor_columns() -> None:
    with pytest.raises(InvalidCatalog):
        parse_catalog("pm25,local_ts\n1,2026-10-28 00:00:00+0000\n")


def test_parse_catalog_returns_an_empty_tuple_for_a_header_only_file() -> None:
    assert parse_catalog("sensor_index,latitude,longitude\n") == ()


def test_nearby_orders_by_miles_and_drops_sensors_outside_the_radius() -> None:
    sensors = parse_catalog(_FIXTURE.read_text(encoding="utf-8"))

    found = nearby(sensors, _HOME[0], _HOME[1], 5)

    assert [sensor.sensor_index for sensor in found] == ["281078", "281079"]
    assert found[0].distance_miles == pytest.approx(0)
    assert found[1].distance_miles == pytest.approx(0.971, abs=0.001)
    assert nearby_label(found[0]) == "281078 · 0.0 mi · PM2.5 3.3"
    assert nearby_label(found[1]) == "281079 · 1.0 mi"


def test_nearby_uses_miles_for_one_degree_of_latitude() -> None:
    sensors = (
        _sensor("1", 0, 0, 3.3),
        _sensor("2", 1, 0),
    )

    found = nearby(sensors, 0, 0, 70)

    assert [sensor.sensor_index for sensor in found] == ["1", "2"]
    assert found[1].distance_miles == pytest.approx(69.09, abs=0.05)
    assert nearby(sensors, 0, 0, 5)[0].sensor_index == "1"
    assert len(nearby(sensors, 0, 0, 5)) == 1


def test_nearby_includes_a_sensor_on_the_radius_and_breaks_ties_by_id() -> None:
    sensors = (
        _sensor("20", 0, 0),
        _sensor("3", 0, 0),
        _sensor("4", 1, 0),
    )
    on_radius = nearby(sensors, 0, 0, 0)
    assert [sensor.sensor_index for sensor in on_radius] == ["3", "20"]

    one_degree = nearby(sensors, 0, 0, 200)[-1].distance_miles
    assert len(nearby(sensors, 0, 0, one_degree)) == 3
    assert len(nearby(sensors, 0, 0, one_degree - 0.01)) == 2


def test_nearby_label_shows_a_zero_pm_reading() -> None:
    sensor = nearby((_sensor("8", 1, 2, 0.0),), 1, 2, 1)[0]

    assert nearby_label(sensor) == "8 · 0.0 mi · PM2.5 0.0"


def test_nearby_of_an_empty_catalog_is_empty() -> None:
    assert nearby((), 44.0, -123.0, 5) == []


def test_coordinates_for_reads_the_catalog_row() -> None:
    sensors = parse_catalog(_FIXTURE.read_text(encoding="utf-8"))

    assert coordinates_for(sensors, "281078") == (44.89095, -123.06918)
    assert coordinates_for(sensors, "281079") == (44.905, -123.06918)
    assert coordinates_for(sensors, "42") is None
