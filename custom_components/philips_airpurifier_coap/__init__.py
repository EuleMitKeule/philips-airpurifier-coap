"""Support for Philips AirPurifier with CoAP."""

from __future__ import annotations

import asyncio
from functools import partial
from ipaddress import IPv6Address, ip_address
import json
import logging
from os import path, walk

from aioairctrl import CoAPClient
from custom_components.philips_airpurifier_coap.config_entry_data import ConfigEntryData
from custom_components.philips_airpurifier_coap.model import DeviceInformation
from getmac import get_mac_address

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.http.view import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_DEVICE_ID,
    CONF_MODEL,
    CONF_STATUS,
    DOMAIN,
    ICONLIST_URL,
    ICONS,
    ICONS_PATH,
    LOADER_PATH,
    LOADER_URL,
    PAP,
)
from .coordinator import Coordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["fan", "binary_sensor", "sensor", "switch", "light", "select", "number"]


class ListingView(HomeAssistantView):
    """Provide a json list of the used icons."""

    requires_auth = False

    def __init__(self, hass: HomeAssistant, url) -> None:  # noqa: D107
        self._hass = hass
        self.url = url
        self.name = "Icon Listing"

    async def get(self, request):  # noqa: D102
        return json.dumps(self._hass.data[DOMAIN][ICONS])


async def async_setup(hass: HomeAssistant, config) -> bool:
    """Set up the icons for the Philips AirPurifier integration."""
    _LOGGER.debug("async_setup called")

    hass.http.register_static_path(LOADER_URL, hass.config.path(LOADER_PATH), True)
    add_extra_js_url(hass, LOADER_URL)

    iset = PAP
    iconpath = hass.config.path(ICONS_PATH + "/" + iset)

    # walk the directory to get the icons
    icons = []
    for dirpath, _dirnames, filenames in walk(iconpath):
        icons.extend(
            [
                {"name": path.join(dirpath[len(iconpath) :], fn[:-4])}
                for fn in filenames
                if fn.endswith(".svg")
            ]
        )

    # store icons
    data = hass.data.get(DOMAIN)
    if data is None:
        hass.data[DOMAIN] = {}

    hass.data[DOMAIN][ICONS] = icons

    # register path and view
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/philips_airpurifier_coap/icons/pap",
                "/workspaces/core/config/custom_components/philips_airpurifier_coap/icons/pap",
                True,
            )
        ]
    )
    hass.http.register_view(ListingView(hass, ICONLIST_URL + "/" + iset))

    return True


async def async_get_mac_address_from_host(hass: HomeAssistant, host: str) -> str | None:
    """Get mac address from host."""
    mac_address: str | None

    # first we try if this is an ip address
    try:
        ip_addr = ip_address(host)
    except ValueError:
        # that didn't work, so try a hostname
        mac_address = await hass.async_add_executor_job(
            partial(get_mac_address, hostname=host)
        )
    else:
        # it is an ip address, but it could be IPv4 or IPv6
        if ip_addr.version == 4:
            mac_address = await hass.async_add_executor_job(
                partial(get_mac_address, ip=host)
            )
        else:
            ip_addr = IPv6Address(int(ip_addr))
            mac_address = await hass.async_add_executor_job(
                partial(get_mac_address, ip6=str(ip_addr))
            )
    if not mac_address:
        return None

    return format_mac(mac_address)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Philips AirPurifier integration."""

    host = entry.data[CONF_HOST]
    model = entry.data[CONF_MODEL]
    name = entry.data[CONF_NAME]
    device_id = entry.data[CONF_DEVICE_ID]
    status = entry.data[CONF_STATUS]
    mac = await async_get_mac_address_from_host(hass, host)

    try:
        client = await asyncio.wait_for(CoAPClient.create(host), timeout=25)
    except TimeoutError as ex:
        _LOGGER.warning(r"Failed to connect to host %s: %s", host, ex)

        raise ConfigEntryNotReady from ex

    device_information = DeviceInformation(
        host=host, mac=mac, model=model, name=name, device_id=device_id
    )

    coordinator = Coordinator(hass, client, host, status)

    config_entry_data = ConfigEntryData(
        device_information=device_information,
        coordinator=coordinator,
        latest_status=status,
        client=client,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = config_entry_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""

    for p in PLATFORMS:
        await hass.config_entries.async_forward_entry_unload(entry, p)

    config_entry_data: ConfigEntryData = hass.data[DOMAIN][entry.entry_id]

    await config_entry_data.coordinator.shutdown()

    hass.data[DOMAIN].pop(entry.entry_id)

    return True
