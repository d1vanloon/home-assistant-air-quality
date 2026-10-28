from __future__ import annotations

from http import HTTPStatus

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import data_url
from .model import AirFireError, AirFireReading, SensorId, parse_latest_reading

_TIMEOUT = ClientTimeout(total=30)


class SensorNotFound(AirFireError):
    pass


class CannotConnect(AirFireError):
    pass


async def fetch_latest(session: ClientSession, sensor_id: SensorId) -> AirFireReading:
    try:
        async with session.get(data_url(sensor_id), timeout=_TIMEOUT) as response:
            status = response.status
            body = await response.text()
    except (ClientError, TimeoutError) as err:
        raise CannotConnect("Could not reach AirFire") from err

    if status == HTTPStatus.NOT_FOUND:
        raise SensorNotFound(f"No AirFire CSV for {sensor_id}")
    if status != HTTPStatus.OK:
        raise CannotConnect(f"AirFire returned HTTP {status}")
    return parse_latest_reading(body)
