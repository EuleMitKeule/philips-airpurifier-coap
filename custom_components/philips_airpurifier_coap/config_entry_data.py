from dataclasses import dataclass

from aioairctrl import CoAPClient

from custom_components.philips_airpurifier_coap.coordinator import Coordinator
from custom_components.philips_airpurifier_coap.model import (
    DeviceInformation,
    DeviceStatus,
)


@dataclass
class ConfigEntryData:
    """Config entry data class."""

    device_information: DeviceInformation
    client: CoAPClient
    coordinator: Coordinator
    latest_status: DeviceStatus | None = None
