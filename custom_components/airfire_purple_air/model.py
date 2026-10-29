from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from types import MappingProxyType
from typing import Mapping, Sequence

TIMESTAMP_COLUMN = "local_ts"
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S%z"


class AirFireError(Exception):
    pass


class InvalidReading(AirFireError):
    pass


class InvalidCatalog(AirFireError):
    pass


class SensorId(str):
    def __new__(cls, value: object) -> SensorId:
        if isinstance(value, SensorId):
            return value
        if not isinstance(value, str):
            raise ValueError("PurpleAir sensor id must be digits")
        text = value.strip()
        if not text.isdecimal():
            raise ValueError("PurpleAir sensor id must be digits")
        return str.__new__(cls, text)


@dataclass(frozen=True, slots=True)
class AirFireReading:
    timestamp: datetime
    factors: Mapping[str, float]


def _latest_sample(text: str) -> tuple[str, dict[str, str | None]]:
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames or TIMESTAMP_COLUMN not in reader.fieldnames:
        raise InvalidReading("CSV is missing local_ts")

    latest: dict[str, str | None] | None = None
    for row in reader:
        latest = row
    if latest is None:
        raise InvalidReading("CSV has no readings")
    return latest.get(TIMESTAMP_COLUMN) or "", latest


def _parse_timestamp(raw_timestamp: str) -> datetime:
    try:
        return datetime.strptime(raw_timestamp.strip(), _TIMESTAMP_FORMAT)
    except ValueError as err:
        raise InvalidReading("CSV timestamp is not readable") from err


def _numeric_factors(row: Mapping[str, str | None]) -> dict[str, float]:
    factors: dict[str, float] = {}
    for key, value in row.items():
        if key is None or key == TIMESTAMP_COLUMN or value is None:
            continue
        stripped = value.strip()
        if not stripped:
            continue
        try:
            number = float(stripped)
        except ValueError:
            continue
        if math.isfinite(number):
            factors[key] = number
    return factors


def parse_latest_reading(text: str) -> AirFireReading:
    raw_timestamp, row = _latest_sample(text)
    factors = _numeric_factors(row)
    if not factors:
        raise InvalidReading("CSV reading has no measurements")
    return AirFireReading(
        timestamp=_parse_timestamp(raw_timestamp),
        factors=MappingProxyType(factors),
    )


_EARTH_RADIUS_MILES = 3958.7613
_CATALOG_INDEX = "sensor_index"
_CATALOG_LATITUDE = "latitude"
_CATALOG_LONGITUDE = "longitude"
# epa_nowcast is a different average. A blank epa_pm25 stays blank.
_CATALOG_PM = "epa_pm25"


@dataclass(frozen=True, slots=True)
class CatalogSensor:
    sensor_index: SensorId
    latitude: float
    longitude: float
    pm25: float | None


@dataclass(frozen=True, slots=True)
class NearbySensor:
    sensor_index: SensorId
    distance_miles: float
    pm25: float | None


def _haversine_miles(
    latitude: float,
    longitude: float,
    other_latitude: float,
    other_longitude: float,
) -> float:
    lat1 = math.radians(latitude)
    lat2 = math.radians(other_latitude)
    d_lat = math.radians(other_latitude - latitude)
    d_lon = math.radians(other_longitude - longitude)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(a)))


def _optional_pm(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def _catalog_sensor(row: Mapping[str, str | None]) -> CatalogSensor | None:
    raw_index = row.get(_CATALOG_INDEX)
    raw_latitude = row.get(_CATALOG_LATITUDE)
    raw_longitude = row.get(_CATALOG_LONGITUDE)
    if raw_index is None or raw_latitude is None or raw_longitude is None:
        return None
    try:
        sensor_index = SensorId(raw_index)
        latitude = float(raw_latitude)
        longitude = float(raw_longitude)
    except ValueError:
        return None
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None
    if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
        return None
    return CatalogSensor(
        sensor_index=sensor_index,
        latitude=latitude,
        longitude=longitude,
        pm25=_optional_pm(row.get(_CATALOG_PM)),
    )


def parse_catalog(text: str) -> tuple[CatalogSensor, ...]:
    reader = csv.DictReader(StringIO(text))
    fieldnames = reader.fieldnames
    if fieldnames is None or any(
        name not in fieldnames
        for name in (_CATALOG_INDEX, _CATALOG_LATITUDE, _CATALOG_LONGITUDE)
    ):
        raise InvalidCatalog("Catalog CSV is missing sensor columns")

    sensors: dict[SensorId, CatalogSensor] = {}
    for row in reader:
        sensor = _catalog_sensor(row)
        if sensor is None or sensor.sensor_index in sensors:
            continue
        sensors[sensor.sensor_index] = sensor
    return tuple(sensors.values())


def nearby(
    sensors: Sequence[CatalogSensor],
    latitude: float,
    longitude: float,
    radius_miles: float,
) -> list[NearbySensor]:
    found: list[NearbySensor] = []
    for sensor in sensors:
        distance_miles = _haversine_miles(
            latitude, longitude, sensor.latitude, sensor.longitude
        )
        if distance_miles <= radius_miles:
            found.append(
                NearbySensor(
                    sensor_index=sensor.sensor_index,
                    distance_miles=distance_miles,
                    pm25=sensor.pm25,
                )
            )
    found.sort(key=lambda item: (item.distance_miles, int(item.sensor_index)))
    return found


def nearby_label(sensor: NearbySensor) -> str:
    label = f"{sensor.sensor_index} · {sensor.distance_miles:.1f} mi"
    if sensor.pm25 is None:
        return label
    return f"{label} · PM2.5 {sensor.pm25:.1f}"
