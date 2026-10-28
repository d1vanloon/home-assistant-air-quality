from __future__ import annotations

from datetime import timedelta
import logging

from .model import SensorId

DOMAIN = "airfire_purple_air"
CONF_SENSOR_ID = "sensor_id"
CONF_NAME = "name"
SCAN_INTERVAL = timedelta(minutes=10)
LOGGER = logging.getLogger(__package__)

_DATA_URL = (
    "https://airfire-data-exports.s3.us-west-2.amazonaws.com"
    "/maps/purple_air/v4/timeseries/ten_min/{sensor_id}.csv"
)


def data_url(sensor_id: SensorId) -> str:
    return _DATA_URL.format(sensor_id=sensor_id)
