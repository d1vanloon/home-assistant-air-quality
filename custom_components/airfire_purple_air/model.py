from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from types import MappingProxyType
from typing import Mapping

TIMESTAMP_COLUMN = "local_ts"
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S%z"


class AirFireError(Exception):
    pass


class InvalidReading(AirFireError):
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
