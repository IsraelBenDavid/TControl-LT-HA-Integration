"""Data update coordinator for the TControl LT16 integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SCAN_INTERVAL_MS,
    DEFAULT_SCAN_INTERVAL_MS,
    DOMAIN,
    MIN_SCAN_INTERVAL_MS,
)
from .hub import TControlError, TControlHub

_LOGGER = logging.getLogger(__name__)

type TControlConfigEntry = ConfigEntry[TControlCoordinator]


class TControlCoordinator(DataUpdateCoordinator[dict[int, bool]]):
    """Polls the controller for relay states at the configured interval."""

    config_entry: TControlConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: TControlConfigEntry, hub: TControlHub
    ) -> None:
        """Initialise the coordinator."""
        # Never poll faster than the serial line can sustain.
        scan_interval_ms = max(
            int(entry.data.get(CONF_SCAN_INTERVAL_MS, DEFAULT_SCAN_INTERVAL_MS)),
            MIN_SCAN_INTERVAL_MS,
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {hub.identifier}",
            update_interval=timedelta(milliseconds=scan_interval_ms),
            # Only notify entities when a relay actually changed.
            always_update=False,
        )
        self.hub = hub

    async def _async_update_data(self) -> dict[int, bool]:
        """Fetch the relay states from the controller."""
        try:
            return await self.hass.async_add_executor_job(self.hub.read_state)
        except TControlError as err:
            raise UpdateFailed(str(err)) from err
