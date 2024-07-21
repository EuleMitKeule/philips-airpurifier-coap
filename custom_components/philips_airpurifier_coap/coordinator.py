import asyncio
import contextlib
import logging
from asyncio import Task
from collections.abc import Callable
from typing import Any

from aioairctrl import CoAPClient
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback

from .const import MISSED_PACKAGE_COUNT
from .timer import Timer

_LOGGER = logging.getLogger(__name__)


class Coordinator:
    """Class to coordinate the data requests from the Philips API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: CoAPClient,
        host: str,
        status: dict[str, Any],
    ) -> None:
        """Initialize the coordinator."""

        self.hass = hass
        self.client = client
        self.host = host
        self.status = status

        self._listeners: list[CALLBACK_TYPE] = []
        self._task: Task | None = None

        self._reconnect_task: Task | None = None
        self._timeout: int = 60

        self._timer_disconnected = Timer(
            timeout=self._timeout * MISSED_PACKAGE_COUNT,
            callback=self.reconnect,
            autostart=False,
        )
        self._timer_disconnected.auto_restart = True

    async def shutdown(self):
        """Shutdown the API connection."""

        _LOGGER.debug("shutdown: called for host %s", self.host)

        if self._reconnect_task is not None:
            _LOGGER.debug(
                "shutdown: cancelling reconnect task for host %s",
                self.host,
            )
            self._reconnect_task.cancel()

        if self._timer_disconnected is not None:
            _LOGGER.debug(
                "shutdown: cancelling timeout task for host %s",
                self.host,
            )
            self._timer_disconnected.cancel()

        if self.client is not None:
            await self.client.shutdown()

    async def reconnect(self):
        """Reconnect to the API connection."""

        _LOGGER.debug("reconnect: called for host %s", self.host)

        try:
            if self._reconnect_task is not None:
                # Reconnect stuck
                _LOGGER.debug(
                    "reconnect: cancelling reconnect task for host %s",
                    self.host,
                )
                self._reconnect_task.cancel()
                self._reconnect_task = None

            _LOGGER.debug(
                "reconnect: creating new reconnect task for host %s",
                self.host,
            )
            self._reconnect_task = asyncio.create_task(self._reconnect())

        except:
            _LOGGER.exception("Exception on starting reconnect!")

    async def _reconnect(self):
        try:
            _LOGGER.debug("Reconnecting")
            with contextlib.suppress(Exception):
                await self.client.shutdown()
            self.client = await CoAPClient.create(self.host)
            self._start_observing()
        except asyncio.CancelledError:
            pass
        except:
            _LOGGER.exception("_reconnect error")

    @callback
    def async_add_listener(self, update_callback: CALLBACK_TYPE) -> Callable[[], None]:
        """Listen for data updates."""

        start_observing = not self._listeners
        self._listeners.append(update_callback)

        if start_observing:
            self._start_observing()

        @callback
        def remove_listener() -> None:
            """Remove update listener."""

            self.async_remove_listener(update_callback)

        return remove_listener

    @callback
    def async_remove_listener(self, update_callback) -> None:
        """Remove data update."""

        self._listeners.remove(update_callback)

        if not self._listeners and self._task:
            self._task.cancel()
            self._task = None

    async def _async_observe_status(self) -> None:
        """Fetch the status of the device."""

        async for status in self.client.observe_status():
            _LOGGER.debug("Status update: %s", status)

            self.status = status
            # self._timer_disconnected.reset()

            for update_callback in self._listeners:
                update_callback()

    def _start_observing(self) -> None:
        """Schedule state observation."""

        if self._task:
            self._task.cancel()
            self._task = None

        self._task = self.hass.async_create_task(self._async_observe_status())
        # self._timer_disconnected.reset()
