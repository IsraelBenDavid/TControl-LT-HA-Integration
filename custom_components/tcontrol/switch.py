"""Switch platform for TControl LT16."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NUM_CHANNELS, DEFAULT_NUM_CHANNELS, DOMAIN, MANUFACTURER, MODEL
from .coordinator import TControlConfigEntry, TControlCoordinator
from .hub import TControlError


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TControlConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up TControl switch entities from a config entry."""
    coordinator = entry.runtime_data
    num_channels: int = entry.data.get(CONF_NUM_CHANNELS, DEFAULT_NUM_CHANNELS)

    async_add_entities(
        TControlSwitch(coordinator, entry, channel)
        for channel in range(1, num_channels + 1)
    )


class TControlSwitch(CoordinatorEntity[TControlCoordinator], SwitchEntity):
    """Representation of a single TControl LT16 relay channel."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TControlCoordinator,
        entry: TControlConfigEntry,
        channel: int,
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator)
        self._channel = channel
        self._attr_unique_id = f"{entry.entry_id}_channel_{channel}"
        self._attr_name = f"Channel {channel}"
        # Every channel belongs to the one physical controller.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.hub.identifier)},
            name=f"TControl LT16 ({coordinator.hub.identifier})",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the relay is on, None if the board did not report it."""
        return self.coordinator.data.get(self._channel)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the relay channel on."""
        await self._async_set_relay(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the relay channel off."""
        await self._async_set_relay(False)

    async def _async_set_relay(self, turn_on: bool) -> None:
        """Send the relay command and reflect the result immediately."""
        try:
            await self.hass.async_add_executor_job(
                self.coordinator.hub.send_command, self._channel, turn_on
            )
        except TControlError as err:
            # Surfaces in the UI / automation trace instead of failing silently.
            raise HomeAssistantError(
                f"Failed to turn {'on' if turn_on else 'off'} TControl channel "
                f"{self._channel}: {err}"
            ) from err

        # Show the new state right away; the next poll confirms it from the
        # hardware.  (async_request_refresh alone is debounced, so a second
        # toggle within its cooldown would otherwise stay stale.)
        self.coordinator.async_set_updated_data(
            {**self.coordinator.data, self._channel: turn_on}
        )
        await self.coordinator.async_request_refresh()
