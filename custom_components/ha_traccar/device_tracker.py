"""Support for Traccar device tracking."""
from __future__ import annotations

import logging


from homeassistant.components.device_tracker import (
    SourceType,
    TrackerEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    TRACKER_UPDATE,
    ATTR_ACCURACY,
    ATTR_ALTITUDE,
    ATTR_BATTERY,
    ATTR_BEARING,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_SPEED
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure a dispatcher connection based on a config entry."""

    @callback
    def _receive_data(server, device, position):
        """Receive set location."""
        if device.unique_id in hass.data[DOMAIN][entry.entry_id]["devices"]:
            return

        hass.data[DOMAIN][entry.entry_id]["devices"].add(device.unique_id)

        async_add_entities(
            [TraccarEntity(server,device, position)]
        )

    async_dispatcher_connect(hass, TRACKER_UPDATE, _receive_data)

    # Restore previously loaded devices
    dev_reg = device_registry.async_get(hass)
    dev_ids = {
        identifier[1]
        for device in dev_reg.devices.values()
        for identifier in device.identifiers
        if identifier[0] == DOMAIN
    }
    if not dev_ids:
        return

    entities = []
    for dev_id in dev_ids:
        hass.data[DOMAIN]["devices"].add(dev_id)
        entity = TraccarEntity(dev_id, None, None, None, None, None)
        entities.append(entity)

    async_add_entities(entities)


class TraccarEntity(TrackerEntity, RestoreEntity):
    """Represent a tracked device."""

    def __init__(self, server, device, position):
        """Set up Geofency entity."""
        self._accuracy = position.accuracy or 0.0
        self._attributes = {}
        self._name = device.name
        self._battery = position.attributes.get("batteryLevel", -1)
        self._latitude = position.latitude
        self._longitude = position.longitude
        self._unsub_dispatcher = None
        self._unique_id = f"{server}-{device.unique_id}"
        self._server = server
        self._device_unique_id = device.unique_id

    @property
    def battery_level(self):
        """Return battery value of the device."""
        return self._battery

    @property
    def extra_state_attributes(self):
        """Return device specific attributes."""
        return self._attributes

    @property
    def latitude(self):
        """Return latitude value of the device."""
        return self._latitude

    @property
    def longitude(self):
        """Return longitude value of the device."""
        return self._longitude

    @property
    def location_accuracy(self):
        """Return the gps accuracy of the device."""
        return self._accuracy

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique ID."""
        return self._unique_id

    @property
    def device_info(self):
        """Return the device info."""
        return {"name": self._name, "identifiers": {(DOMAIN, self._unique_id)}}

    @property
    def source_type(self) -> SourceType:
        """Return the source type, eg gps or router, of the device."""
        return SourceType.GPS

    async def async_added_to_hass(self) -> None:
        """Register state update callback."""
        await super().async_added_to_hass()
        self._unsub_dispatcher = async_dispatcher_connect(
            self.hass, TRACKER_UPDATE, self._async_receive_data
        )

        # don't restore if we got created with data
        if self._latitude is not None or self._longitude is not None:
            return

        if (state := await self.async_get_last_state()) is None:
            self._latitude = None
            self._longitude = None
            self._accuracy = None
            self._attributes = {
                ATTR_ALTITUDE: None,
                ATTR_BEARING: None,
                ATTR_SPEED: None,
            }
            self._battery = None
            return

        attr = state.attributes
        self._latitude = attr.get(ATTR_LATITUDE)
        self._longitude = attr.get(ATTR_LONGITUDE)
        self._accuracy = attr.get(ATTR_ACCURACY)
        self._attributes = {
            ATTR_ALTITUDE: attr.get(ATTR_ALTITUDE),
            ATTR_BEARING: attr.get(ATTR_BEARING),
            ATTR_SPEED: attr.get(ATTR_SPEED),
        }
        self._battery = attr.get(ATTR_BATTERY)

    async def async_will_remove_from_hass(self) -> None:
        """Clean up after entity before removal."""
        await super().async_will_remove_from_hass()
        self._unsub_dispatcher()

    @callback
    def _async_receive_data(
        self, server, device, position
    ):
        """Mark the device as seen."""
        if server != self._server or device.unique_id != self._device_unique_id:
            return

        self._name = device.name
        self._latitude = position.latitude
        self._longitude = position.longitude
        self._battery = position.attributes.get("batteryLevel", -1)
        self._accuracy = position.accuracy or 0.0
        self._attributes.update(position.attributes)
        self.async_write_ha_state()