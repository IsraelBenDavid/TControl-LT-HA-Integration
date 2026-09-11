"""The TControl LT16 integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import TControlConfigEntry, TControlCoordinator
from .hub import TControlHub

PLATFORMS: list[Platform] = [Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: TControlConfigEntry) -> bool:
    """Set up TControl LT16 from a config entry."""
    hub = TControlHub(dict(entry.data))
    coordinator = TControlCoordinator(hass, entry, hub)

    # Reads the real relay states before any entity is created.  If the
    # controller is unreachable this raises ConfigEntryNotReady and Home
    # Assistant retries the setup in the background.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TControlConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
