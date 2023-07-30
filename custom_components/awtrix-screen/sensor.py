import logging
import os
import voluptuous as vol
from datetime import timedelta, datetime
import json
import aiohttp
import asyncio

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Custom Screen Sensor"

CONF_SCAN_INTERVAL = "scan_interval"
LIVE_SCAN_INTERVAL = timedelta(seconds=1)
SCAN_INTERVAL = timedelta(seconds=1)
DEFAULT_SCAN_INTERVAL = LIVE_SCAN_INTERVAL.seconds
ONLINE_CHECK_INTERVAL = timedelta(seconds=10)
OFFLINE_CHECK_DELAY = timedelta(seconds=5)


def load_screen_data():
    """Load all sets of screen data from the JSON file."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "screen_data.json")
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        _LOGGER.warning("Error loading offline screen data. Using a default value.")
        return {
            "offline": [16711680] * 256
        }  # Default value if the file cannot be loaded or has incorrect data


ALL_SCREEN_DATA = load_screen_data()

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_URL): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.time_period,
    }
)


async def async_http_get_with_retries(session, url, retries=3, timeout=5):
    for retry in range(retries):
        try:
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    _LOGGER.warning(
                        "Request to API failed with status code: %s", response.status
                    )
                    return None
        except aiohttp.ClientError as e:
            _LOGGER.warning("Error fetching data from API: %s", e)
            if retry + 1 < retries:
                await asyncio.sleep(2 ** retry)
    return None


async def async_http_check_online(api_endpoint):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_endpoint, timeout=5) as response:
                return response.status == 200
    except aiohttp.ClientError as e:
        _LOGGER.warning("Error fetching data from API: %s", e)
        return False


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the custom sensor platform."""
    api_endpoint = config[CONF_URL]
    name = config[CONF_NAME]
    scan_interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    sensors = [CustomScreenSensor(name, api_endpoint, scan_interval)]

    add_entities(sensors)

    async def async_update_sensors(event_time):
        """Update all the sensors."""
        for sensor in sensors:
            await sensor.async_update()

    async def async_check_online_status(now):
        """Check if the device is online."""
        online = await async_http_check_online(api_endpoint)

        for sensor in sensors:
            # Check if the online status has changed since the last check
            if sensor.is_online() != online:
                await sensor.async_update_online_status(online)

    # Perform the initial online status check after a small delay when Home Assistant starts
    hass.async_create_task(async_check_online_status(None))

    # Schedule the regular update function and online status check based on the scan_interval
    hass.async_create_task(async_update_sensors(None))
    hass.helpers.event.async_track_time_interval(
        async_update_sensors, scan_interval
    )
    hass.helpers.event.async_track_time_interval(
        async_check_online_status, ONLINE_CHECK_INTERVAL
    )


class CustomScreenSensor(Entity):
    """Representation of a Custom Screen Sensor."""

    def __init__(self, name, api_endpoint, scan_interval):
        """Initialize the sensor."""
        self._name = name
        self._api_endpoint = api_endpoint
        self._state = None  # Start with no state until the first update
        self._scan_interval = scan_interval
        self._state_attributes = {}
        self._online = False
        self._max_errors = 3  # Maximum consecutive errors before reporting offline
        self._error_counter = 0
        self._offline_delay = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._state_attributes

    def is_online(self):
        """Return the current online status."""
        return self._online

    async def async_update_online_status(self, online):
        """Update the online status."""
        if not online:
            self._error_counter += 1
            if self._error_counter >= self._max_errors:
                _LOGGER.warning("AWTRIX is offline: %s", self._name)
                self._online = False
                self._state = 0
                # Trigger an online status check after the offline check delay
                self._offline_delay = asyncio.get_event_loop().call_later(
                    OFFLINE_CHECK_DELAY.total_seconds(), self.async_check_online
                )
        else:
            if not self._online:
                _LOGGER.warning("AWTRIX is online: %s", self._name)
                self._online = True
                # Set the state to None to trigger an update on the next scheduled interval
                self._state = None
                # Cancel any previously scheduled online status check
                if self._offline_delay is not None:
                    self._offline_delay.cancel()
                    self._offline_delay = None

    async def async_check_online(self, *args):
        """Check if the device is online after the delay."""
        _LOGGER.warning("Checking if AWTRIX is online: %s", self._name)
        online = await async_http_check_online(self._api_endpoint)
        await self.async_update_online_status(online)

    async def async_update(self):
        """Fetch new state data for the sensor if the device is online."""
        if not self._online:
            # If the device is offline, set the "screen" attribute with the offline data
            self._state_attributes["screen"] = json.dumps(ALL_SCREEN_DATA["offline"])
            return

        async with aiohttp.ClientSession() as session:
            data = await async_http_get_with_retries(session, self._api_endpoint)
            if data is not None:
                if isinstance(data, list):
                    # Convert data to JSON-formatted string and store it in the "screen" attribute
                    self._state_attributes["screen"] = json.dumps(data)
                    # Log the received data
                    _LOGGER.debug("Received data from API: %s", data)
                    # Reset the error counter on a successful API response
                    self._error_counter = 0
                    # Set the state to 1 to indicate the device is online
                    self._state = 1
                else:
                    _LOGGER.warning("Invalid data format received from API.")
                    self._handle_error()
            else:
                self._handle_error()

        # Add a "test" attribute and set its value to "test"
        self._state_attributes["test"] = "test"

    def _handle_error(self):
        """Handle consecutive errors and set the state to offline if needed."""
        self._error_counter += 1
        if self._error_counter >= self._max_errors:
            _LOGGER.warning("AWTRIX is offline: %s", self._name)
            self._online = False
            self._state = 0
            # Trigger an online status check after the offline check delay
            self._offline_delay = asyncio.get_event_loop().call_later(
                OFFLINE_CHECK_DELAY.total_seconds(), self.async_check_online
            )
