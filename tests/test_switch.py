"""End-to-end tests: load the integration in Home Assistant and drive the switches."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.tcontrol.const import (
    CONF_CONNECTION_TYPE,
    CONF_NUM_CHANNELS,
    CONF_SCAN_INTERVAL_MS,
    CONF_SERIAL_PORT,
    CONF_TCP_HOST,
    CONF_TCP_PORT,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_TCP,
    DOMAIN,
)

from .fake_device import FakeDevice

SERIAL_DATA = {
    CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
    CONF_SERIAL_PORT: "/dev/ttyUSB0",
    CONF_NUM_CHANNELS: 8,
    CONF_SCAN_INTERVAL_MS: 2000,
}

TCP_DATA = {
    CONF_CONNECTION_TYPE: CONNECTION_TYPE_TCP,
    CONF_TCP_HOST: "192.168.1.50",
    CONF_TCP_PORT: 8888,
    CONF_NUM_CHANNELS: 8,
    CONF_SCAN_INTERVAL_MS: 2000,
}


async def _setup(hass: HomeAssistant, data: dict) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=data, unique_id="test")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, channel: int) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        SWITCH_DOMAIN, DOMAIN, f"{entry.entry_id}_channel_{channel}"
    )
    assert entity_id is not None, f"no entity registered for channel {channel}"
    return entity_id


@pytest.mark.parametrize(
    ("data", "transport"),
    [(SERIAL_DATA, "fake_serial"), (TCP_DATA, "fake_tcp")],
)
async def test_setup_and_control(
    hass: HomeAssistant,
    request: pytest.FixtureRequest,
    data: dict,
    transport: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The integration loads, reflects device state and can switch relays."""
    device: FakeDevice = request.getfixturevalue(transport)
    device.relays[3] = True

    with caplog.at_level(logging.WARNING):
        entry = await _setup(hass, data)

    assert entry.state is ConfigEntryState.LOADED

    # No deprecation / error noise from Home Assistant about this integration.
    noise = [
        rec.getMessage()
        for rec in caplog.records
        if rec.levelno >= logging.WARNING
        and "tcontrol" in rec.getMessage()
        and "has not been tested by Home Assistant" not in rec.getMessage()
    ]
    assert not noise, f"unexpected warnings: {noise}"

    # Initial poll reflects the real relay state.
    assert hass.states.get(_entity_id(hass, entry, 3)).state == STATE_ON
    assert hass.states.get(_entity_id(hass, entry, 1)).state == STATE_OFF

    # Turn on channel 8 -> S008ONE is sent and state updates.
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: _entity_id(hass, entry, 8)},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert "S008ONE" in device.received
    assert device.relays[8] is True
    assert hass.states.get(_entity_id(hass, entry, 8)).state == STATE_ON

    # Turn off channel 3 -> S003OFE is sent and state updates.
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: _entity_id(hass, entry, 3)},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert "S003OFE" in device.received
    assert hass.states.get(_entity_id(hass, entry, 3)).state == STATE_OFF

    # The controller is never opened twice at the same time.
    assert device.max_concurrent_opens == 1

    # Unload cleanly.
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_single_device_groups_all_channels(
    hass: HomeAssistant, fake_serial: FakeDevice
) -> None:
    """All switch entities hang off one device in the registry."""
    entry = await _setup(hass, SERIAL_DATA)
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, "/dev/ttyUSB0"), entry.entry_id
    )
    assert device is not None
    assert device.manufacturer == "TControl"

    entity_registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert len(entities) == 8
    assert {e.device_id for e in entities} == {device.id}


async def test_sixteen_channel_board(
    hass: HomeAssistant, device: FakeDevice, fake_serial: FakeDevice
) -> None:
    """A 16-channel controller answers with 16 status bits and channel 16 is addressable."""
    device.num_channels = 16
    device.relays = dict.fromkeys(range(1, 17), False)
    device.relays[16] = True

    entry = await _setup(hass, {**SERIAL_DATA, CONF_NUM_CHANNELS: 16})
    assert hass.states.get(_entity_id(hass, entry, 16)).state == STATE_ON
    assert hass.states.get(_entity_id(hass, entry, 10)).state == STATE_OFF

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: _entity_id(hass, entry, 10)},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert "S00AONE" in device.received
    assert hass.states.get(_entity_id(hass, entry, 10)).state == STATE_ON


async def test_unreachable_device_does_not_crash(
    hass: HomeAssistant, broken_serial: None
) -> None:
    """When the controller is unplugged the entry retries instead of loading blind."""
    entry = await _setup(hass, SERIAL_DATA)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_echoing_bridge_is_parsed(
    hass: HomeAssistant, device: FakeDevice, fake_tcp: FakeDevice
) -> None:
    """A bridge that echoes S00QLE before the answer must not truncate the frame."""
    device.echo = True
    device.relays[2] = True
    entry = await _setup(hass, TCP_DATA)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(_entity_id(hass, entry, 2)).state == STATE_ON


async def test_device_going_offline_marks_entities_unavailable(
    hass: HomeAssistant, device: FakeDevice, fake_serial: FakeDevice
) -> None:
    """A failed poll marks the switches unavailable and a later poll recovers them."""
    entry = await _setup(hass, SERIAL_DATA)
    entity_id = _entity_id(hass, entry, 1)
    assert hass.states.get(entity_id).state == STATE_OFF

    device.offline = True
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    device.offline = False
    device.relays[1] = True
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON


async def test_failed_command_raises(
    hass: HomeAssistant, device: FakeDevice, fake_serial: FakeDevice
) -> None:
    """A relay command that cannot be delivered fails loudly instead of silently."""
    entry = await _setup(hass, SERIAL_DATA)
    entity_id = _entity_id(hass, entry, 5)

    device.offline = True
    with pytest.raises(HomeAssistantError, match="channel 5"):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
    # State was not optimistically flipped for a command that never arrived.
    assert hass.states.get(entity_id).state == STATE_OFF


async def test_rapid_toggles_and_polls_never_overlap_on_the_wire(
    hass: HomeAssistant, device: FakeDevice, fake_tcp: FakeDevice
) -> None:
    """Commands and polls from different executor threads are serialised."""
    entry = await _setup(hass, TCP_DATA)
    coordinator = entry.runtime_data

    calls = [
        hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: _entity_id(hass, entry, ch)},
            blocking=True,
        )
        for ch in range(1, 9)
    ]
    await asyncio.gather(
        *calls, coordinator.async_refresh(), coordinator.async_refresh()
    )
    await hass.async_block_till_done()

    assert all(device.relays.values())
    assert all(
        hass.states.get(_entity_id(hass, entry, ch)).state == STATE_ON
        for ch in range(1, 9)
    )
    assert device.max_concurrent_opens == 1, (
        "poll and command opened the bridge concurrently"
    )


async def test_silent_controller_retries_setup(
    hass: HomeAssistant, device: FakeDevice, fake_serial: FakeDevice
) -> None:
    """A controller that opens fine but never answers S00QLE is not treated as loaded."""
    device.respond = False
    entry = await _setup(hass, SERIAL_DATA)
    assert entry.state is ConfigEntryState.SETUP_RETRY
