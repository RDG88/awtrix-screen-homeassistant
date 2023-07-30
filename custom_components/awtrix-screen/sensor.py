import logging
import requests
import voluptuous as vol
from datetime import timedelta
import json

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import track_time_interval

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Custom Screen Sensor"

SCAN_INTERVAL = timedelta(seconds=5)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_URL): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the custom sensor platform."""
    api_endpoint = config[CONF_URL]
    name = config[CONF_NAME]

    sensors = [CustomScreenSensor(name, api_endpoint)]

    add_entities(sensors)

    def update_sensors(event_time):
        """Update all the sensors."""
        for sensor in sensors:
            sensor.update()

    # Schedule the update function based on the scan_interval
    track_time_interval(hass, update_sensors, SCAN_INTERVAL)


class CustomScreenSensor(Entity):
    """Representation of a Custom Screen Sensor."""

    def __init__(self, name, api_endpoint):
        """Initialize the sensor."""
        self._name = name
        self._api_endpoint = api_endpoint
        self._state = 1
        self._attributes = {}

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
                    # Convert data to JSON-formatted string and store it in the "screen" attribute
                    self._attributes["screen"] = json.dumps(data)
                else:
                    _LOGGER.warning("Invalid data format received from API.")
            else:
                _LOGGER.warning("Request to API failed with status code: %s", response.status_code)
        except requests.exceptions.RequestException as e:
            _LOGGER.warning("Error fetching data from API: %s", e)

        # Add a "test" attribute and set its value to "test"
        self._attributes["test"] = "test"
