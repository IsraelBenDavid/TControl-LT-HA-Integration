"""Switch platform for TControl LT16."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_NUM_CHANNELS, DEFAULT_NUM_CHANNELS, DOMAIN, MANUFACTURER, MODEL
from .hub import TControlHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TControl switch entities from a config entry."""
    hub: TControlHub = hass.data[DOMAIN][entry.entry_id]
    num_channels: int = entry.data.get(CONF_NUM_CHANNELS, DEFAULT_NUM_CHANNELS)

    entities = [
        TControlSwitch(hub, entry, channel)
        for channel in range(1, num_channels + 1)
    ]
    async_add_entities(entities)


class TControlSwitch(SwitchEntity):
    """Representation of a single TControl LT16 relay channel."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hub: TControlHub,
        entry: ConfigEntry,
        channel: int,
    ) -> None:
        """Initialise the switch."""
        self._hub = hub
        self._channel = channel
        self._entry = entry
        self._attr_is_on = False

        self._attr_unique_id = f"{entry.entry_id}_channel_{channel}"
        self._attr_name = f"Channel {channel}"

    @property
    def device_info(self) -> DeviceInfo:
        """Group all channels under a single device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.identifier)},
            name=f"TControl LT16 ({self._hub.identifier})",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the relay channel on."""
        try:
            await self.hass.async_add_executor_job(
                self._hub.send_command, self._channel, True
            )
            self._attr_is_on = True
            self.async_write_ha_state()
        except (OSError, Exception):
            _LOGGER.error("Failed to turn on channel %s", self._channel)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the relay channel off."""
        try:
            await self.hass.async_add_executor_job(
                self._hub.send_command, self._channel, False
            )
            self._attr_is_on = False
            self.async_write_ha_state()
        except (OSError, Exception):
            _LOGGER.error("Failed to turn off channel %s", self._channel)
