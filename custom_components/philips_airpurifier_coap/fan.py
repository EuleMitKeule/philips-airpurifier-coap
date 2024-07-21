"""Philips Air Purifier & Humidifier."""

from __future__ import annotations

import logging

from custom_components.philips_airpurifier_coap.config_entry_data import ConfigEntryData

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .philips import model_to_class

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the fan platform."""

    config_entry_data: ConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    model_class = model_to_class.get(config_entry_data.device_information.model)

    if model_class:
        fan_entity = model_class(hass, entry, config_entry_data)
    else:
        _LOGGER.error(
            "Unsupported model: %s", config_entry_data.device_information.model
        )
        return

    async_add_entities([fan_entity])
