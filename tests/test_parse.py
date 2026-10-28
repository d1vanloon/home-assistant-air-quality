from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from custom_components.airfire_purple_air.model import (
    InvalidReading,
    SensorId,
    parse_latest_reading,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "281078.csv"


def test_parse_latest_reading_uses_last_row() -> None:
    reading = parse_latest_reading(_FIXTURE.read_text(encoding="utf-8"))

    assert reading.factors == {"pm25": 3.3}
    assert reading.timestamp == datetime(
        2026, 10, 28, 0, 5, 6, tzinfo=timezone(timedelta(hours=-5))
    )


def test_parse_rejects_header_only() -> None:
    with pytest.raises(InvalidReading):
        parse_latest_reading("pm25,local_ts\n")


def test_parse_does_not_reuse_an_older_row_when_latest_has_no_measurement() -> None:
    text = (
        "pm25,local_ts\n"
        "1.0,2026-10-28 00:00:00-0500\n"
        ",2026-10-28 00:10:00-0500\n"
    )
    with pytest.raises(InvalidReading):
        parse_latest_reading(text)


def test_parse_ignores_non_numeric_columns() -> None:
    text = "pm25,flag,local_ts\n4.0,ok,2026-10-28 00:05:06-0500\n"
    assert parse_latest_reading(text).factors == {"pm25": 4.0}


def test_parse_keeps_negative_measurements() -> None:
    text = "pm25,local_ts\n-0.1,2026-10-27 21:01:05-0500\n"
    assert parse_latest_reading(text).factors["pm25"] == -0.1


def test_sensor_id_strips_space_and_rejects_letters() -> None:
    assert SensorId(" 281078 ") == "281078"
    with pytest.raises(ValueError):
        SensorId("281078a")
    with pytest.raises(ValueError):
        SensorId("²")
