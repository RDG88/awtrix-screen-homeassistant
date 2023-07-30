import logging
from datetime import timedelta

import requests
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (CONF_NAME, CONF_URL, CONF_SCAN_INTERVAL)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import track_time_interval

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=5)  # Adjust the interval as needed

DEFAULT_NAME = "Custom Screen Sensor"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_URL): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional("scan_interval", default=5): cv.positive_int,
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the custom sensor platform."""
    api_endpoint = config[CONF_URL]
    name = config[CONF_NAME]
    scan_interval = timedelta(seconds=config["scan_interval"])

    sensors = [CustomScreenSensor(name, api_endpoint, scan_interval)]

    add_entities(sensors)

    def update_sensors(event_time):
        """Update all the sensors."""
        for sensor in sensors:
            sensor.update()

    # Schedule the update function based on the scan_interval
    track_time_interval(hass, update_sensors, scan_interval)


class CustomScreenSensor(Entity):
    """Representation of a Custom Screen Sensor."""

    def __init__(self, name, api_endpoint, scan_interval):
        """Initialize the sensor."""
        self._name = name
        self._api_endpoint = api_endpoint
        self._state = None
        self._attributes = {}
        self._scan_interval = scan_interval

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    def update(self):
        """Fetch new state data for the sensor."""
        try:
            response = requests.get(self._api_endpoint, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    self._state = data[0]
                    self._attributes["screen"] = data  # Store the entire data list as the "screen" attribute
                else:
                    _LOGGER.warning("Invalid data format received from API.")
            else:
                _LOGGER.warning("Request to API failed with status code: %s", response.status_code)
        except requests.exceptions.RequestException as e:
            _LOGGER.warning("Error fetching data from API: %s", e)
