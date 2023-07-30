import logging
import aiohttp
import voluptuous as vol
from datetime import timedelta
import json

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval

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


class CustomScreenSensor(Entity):
    """Representation of a Custom Screen Sensor."""

    def __init__(self, name, api_endpoint):
        """Initialize the sensor."""
        self._name = name
        self._api_endpoint = api_endpoint
        self._state = 1
        self._attributes = {"test": "test"}

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

    async def async_added_to_hass(self):
        """Call when entity about to be added to Home Assistant."""
        await self.async_update()

    async def async_update(self):
        """Fetch new state data for the sensor."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self._api_endpoint, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, list):
                            # Convert data to JSON-formatted string and store it in the "screen" attribute
                            self._attributes["screen"] = json.dumps(data)
                            # Log the received data
                            _LOGGER.debug("Received data from API: %s", data)
                        else:
                            _LOGGER.warning("Invalid data format received from API.")
                    else:
                        _LOGGER.warning("Request to API failed with status code: %s", response.status)
        except aiohttp.ClientError as e:
            _LOGGER.warning("Error fetching data from API: %s", e)

        # Update the test attribute to always be "test"
        self._attributes["test"] = "test"
