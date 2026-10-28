from __future__ import annotations

from http import HTTPStatus

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import PAS_CATALOG_URL, data_url
from .model import (
    AirFireError,
    AirFireReading,
    CatalogSensor,
    SensorId,
    parse_catalog,
    parse_latest_reading,
)

_TIMEOUT = ClientTimeout(total=30)


class SensorNotFound(AirFireError):
    pass


class CannotConnect(AirFireError):
    pass


async def _read(session: ClientSession, url: str) -> tuple[int, str]:
    try:
        async with session.get(url, timeout=_TIMEOUT) as response:
            return response.status, await response.text()
    except (ClientError, TimeoutError) as err:
        raise CannotConnect("Could not reach AirFire") from err


async def fetch_latest(session: ClientSession, sensor_id: SensorId) -> AirFireReading:
    status, body = await _read(session, data_url(sensor_id))
    if status == HTTPStatus.NOT_FOUND:
        raise SensorNotFound(f"No AirFire CSV for {sensor_id}")
    if status != HTTPStatus.OK:
        raise CannotConnect(f"AirFire returned HTTP {status}")
    return parse_latest_reading(body)


async def fetch_catalog(session: ClientSession) -> tuple[CatalogSensor, ...]:
    status, body = await _read(session, PAS_CATALOG_URL)
    if status != HTTPStatus.OK:
        raise CannotConnect(f"AirFire catalog returned HTTP {status}")
    return parse_catalog(body)
