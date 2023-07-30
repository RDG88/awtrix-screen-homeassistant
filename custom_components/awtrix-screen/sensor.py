import logging
import os
import requests
import voluptuous as vol
from datetime import timedelta, datetime
import json
from requests.exceptions import RequestException, ConnectTimeout, ConnectionError

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_NAME, CONF_URL, CONF_SCAN_INTERVAL
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import track_time_interval, call_later

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


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the custom sensor platform."""
    api_endpoint = config[CONF_URL]
    name = config[CONF_NAME]
    scan_interval = config.get(
        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
    )  # Corrected indentation
    sensors = [CustomScreenSensor(name, api_endpoint, scan_interval)]

    add_entities(sensors)

    def update_sensors(event_time):
        """Update all the sensors."""
        for sensor in sensors:
            sensor.update()

    def check_online_status(now):
        """Check if the device is online."""
        try:
            response = requests.get(api_endpoint, timeout=5)
            online = response.status_code == 200
        except RequestException as e:
            _LOGGER.warning("Error fetching data from API: %s", e)
            online = False

        for sensor in sensors:
            # Check if the online status has changed since the last check
            if sensor.is_online() != online:
                sensor.update_online_status(online)

    # Perform the initial online status check after a small delay when Home Assistant starts
    call_later(hass, 5, check_online_status)

    # Schedule the regular update function and online status check based on the scan_interval
    track_time_interval(hass, update_sensors, scan_interval)
    track_time_interval(hass, check_online_status, ONLINE_CHECK_INTERVAL)


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

    def update_online_status(self, online):
        """Update the online status."""
        if not online:
            self._error_counter += 1
            if self._error_counter >= self._max_errors:
                _LOGGER.warning("Device is offline: %s", self._name)
                self._online = False
                self._state = 0
                # Trigger an online status check after the offline check delay
                self._offline_delay = call_later(
                    self.hass, OFFLINE_CHECK_DELAY.total_seconds(), self.check_online
                )
        else:
            if not self._online:
                _LOGGER.warning("Device is back online: %s", self._name)
                self._online = True
                # Set the state to None to trigger an update on the next scheduled interval
                self._state = None
                # Cancel any previously scheduled online status check
                if self._offline_delay is not None:
                    self._offline_delay()
                    self._offline_delay = None

    def check_online(self, *args):
        """Check if the device is online after the delay."""
        _LOGGER.warning("Checking if device is online: %s", self._name)
        try:
            response = requests.get(self._api_endpoint, timeout=5)
            online = response.status_code == 200
        except RequestException as e:
            _LOGGER.warning("Error fetching data from API: %s", e)
            online = False

        self.update_online_status(online)

    def update(self):
        """Fetch new state data for the sensor if the device is online."""
        if not self._online:
            # If the device is offline, set the "screen" attribute with the offline data
            self._state_attributes["screen"] = json.dumps(ALL_SCREEN_DATA["offline"])
            return

        try:
            response = requests.get(self._api_endpoint, timeout=5)
            if response.status_code == 200:
                data = response.json()
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
                _LOGGER.warning(
                    "Request to API failed with status code: %s", response.status_code
                )
                self._handle_error()
        except ConnectTimeout as e:
            _LOGGER.warning("Timeout while fetching data from API: %s", e)
            self._handle_error()
        except ConnectionError as e:
            _LOGGER.warning("Connection error while fetching data from API: %s", e)
            self._handle_error()
        except RequestException as e:
            _LOGGER.warning("Other request error while fetching data from API: %s", e)
            self._handle_error()

        # Add a "test" attribute and set its value to "test"
        self._state_attributes["test"] = "test"

    def _handle_error(self):
        """Handle consecutive errors and set the state to offline if needed."""
        self._error_counter += 1
        if self._error_counter >= self._max_errors:
            _LOGGER.warning("Device is offline: %s", self._name)
            self._online = False
            self._state = 0
            # Trigger an online status check after the offline check delay
            self._offline_delay = call_later(
                self.hass, OFFLINE_CHECK_DELAY.total_seconds(), self.check_online
            )
