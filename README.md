# AirFire Purple Air

A custom [Home Assistant](https://www.home-assistant.io/) integration that reads outdoor air quality from PurpleAir sensors through the [AirNow Fire and Smoke Map](https://fire.airnow.gov/) data export.

You add a sensor by picking one near Home Assistant, or by entering its PurpleAir sensor ID. Home Assistant polls the AirFire ten-minute CSV for that sensor and creates one sensor entity for each measured column. PM2.5 uses the PM2.5 device class and micrograms per cubic meter.

This integration is unofficial. It is not affiliated with PurpleAir, AirNow, or the AirFire team.

## Requirements

- Home Assistant 2026.9.0 or newer.
- A numeric PurpleAir sensor ID that AirFire publishes. Sensor `281078` is a working example.

## Install with HACS

[![Open HACS repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=d1vanloon&repository=home-assistant-air-quality&category=integration)

1. Open the button above, or add `https://github.com/d1vanloon/home-assistant-air-quality` as a custom repository in HACS with category **Integration**.
2. Install **AirFire Purple Air**.
3. Restart Home Assistant.

## Install the files yourself

Copy `custom_components/airfire_purple_air/` into the `custom_components/` folder of your Home Assistant configuration directory. Restart Home Assistant.

## Add a sensor

In Home Assistant, go to **Settings** → **Devices & services** → **Add Integration** and search for **AirFire Purple Air**.

### Pick a nearby sensor

1. Choose **Nearby**.
2. Check the latitude, longitude, and search radius. The form starts at the Home Assistant location with a radius of 5 miles. Distances are in miles.
3. Choose a sensor. Each row shows the sensor ID, the distance, and the current PM2.5 when AirFire has a value.

A sensor that is already added is left off the list. If no sensors are in range, widen the radius or change the location, then search again. The widest search is 25 miles.

### Enter a sensor ID

1. On the [Fire and Smoke Map](https://fire.airnow.gov/), click the outdoor PurpleAir sensor you want and note its name and place.
2. Open the [PurpleAir map](https://map.purpleair.com/) and click that same sensor.
3. Read the `select` value in the address bar. In `?select=281078`, the sensor ID is `281078`.
4. Confirm AirFire publishes that sensor. This URL should download a CSV whose first line is `pm25,local_ts`:

   `https://airfire-data-exports.s3.us-west-2.amazonaws.com/maps/purple_air/v4/timeseries/ten_min/281078.csv`

5. Choose **Enter sensor ID**.
6. Enter the sensor ID. Add a name if you want one. Leave the name blank to use `Purple Air` plus the ID.

To add another sensor, run **Add Integration** again with a different ID. Each sensor is its own device.

## Entities

The latest CSV row is the current reading. Each numeric column becomes a sensor on that device.

| CSV column | Entity | Unit |
| --- | --- | --- |
| `pm25` | PM2.5 | μg/m³ |

A numeric column without a known description still becomes a sensor. It uses the column name and has no device class. The `local_ts` column is the sample time. Each entity exposes it as the `sampled_at` attribute.

Home Assistant polls each sensor about every 10 minutes. That matches the export interval.

## Data source

```text
https://airfire-data-exports.s3.us-west-2.amazonaws.com/maps/purple_air/v4/timeseries/ten_min/{sensor_id}.csv
```

Replace `{sensor_id}` with the PurpleAir sensor index. This integration reads that ten-minute CSV while the sensor is configured.

Home Assistant reads this catalog only while you add a sensor.

```text
https://airfire-data-exports.s3.us-west-2.amazonaws.com/maps/purple_air/v4/pas.csv
```

That file has no sensor names. Polling does not read it.

## Troubleshooting

- **AirFire has no data for that sensor ID.** The ID is not in the ten-minute export. Check the CSV URL in a browser.
- **AirFire returned data that could not be read.** The file was empty, the timestamp could not be read, or the latest row had no numeric measurement.
- **Could not reach AirFire.** Home Assistant could not download the CSV. Try again later.
- **No unconfigured sensors are within that radius.** Widen the search or change the latitude and longitude. A sensor you already added is hidden.

## License

MIT. See [LICENSE](LICENSE).
