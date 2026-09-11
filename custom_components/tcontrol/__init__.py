"""The TControl LT16 integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SCAN_INTERVAL_MS,
    DEFAULT_SCAN_INTERVAL_MS,
    DOMAIN,
    MIN_SCAN_INTERVAL_MS,
)
from .hub import TControlHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TControl LT16 from a config entry."""
    hub = TControlHub(dict(entry.data))

    scan_interval_ms = max(
        entry.data.get(CONF_SCAN_INTERVAL_MS, DEFAULT_SCAN_INTERVAL_MS),
        MIN_SCAN_INTERVAL_MS,
    )

    async def _async_update_data() -> dict[int, bool]:
        """Fetch state from the controller."""
        state = await hass.async_add_executor_job(hub.read_state)
        if state is None:
            raise UpdateFailed("Failed to read state from TControl hub")
        return state

    coordinator: DataUpdateCoordinator[dict[int, bool]] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"TControl ({hub.identifier})",
        update_method=_async_update_data,
        update_interval=timedelta(milliseconds=scan_interval_ms),
    )

    # Perform a first refresh so entities have data on startup
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "hub": hub,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
