"""Tests for the TControl LT16 config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

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


async def _start(hass: HomeAssistant, connection_type: str):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONNECTION_TYPE: connection_type}
    )


async def test_serial_flow_creates_entry(
    hass: HomeAssistant, fake_serial: FakeDevice
) -> None:
    """Serial happy path."""
    result = await _start(hass, CONNECTION_TYPE_SERIAL)
    assert result["step_id"] == "serial"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SERIAL_PORT: "/dev/ttyUSB1",
            CONF_NUM_CHANNELS: 16,
            CONF_SCAN_INTERVAL_MS: 500,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "TControl (/dev/ttyUSB1)"
    assert result["data"] == {
        CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
        CONF_SERIAL_PORT: "/dev/ttyUSB1",
        CONF_NUM_CHANNELS: 16,
        CONF_SCAN_INTERVAL_MS: 500,
    }
    assert result["result"].unique_id == "/dev/ttyUSB1"


async def test_tcp_flow_creates_entry(
    hass: HomeAssistant, fake_tcp: FakeDevice
) -> None:
    """TCP happy path."""
    result = await _start(hass, CONNECTION_TYPE_TCP)
    assert result["step_id"] == "tcp"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TCP_HOST: "10.0.0.7",
            CONF_TCP_PORT: 8888,
            CONF_NUM_CHANNELS: 8,
            CONF_SCAN_INTERVAL_MS: 2000,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "TControl (10.0.0.7:8888)"
    assert result["result"].unique_id == "10.0.0.7:8888"


async def test_cannot_connect_shows_error(
    hass: HomeAssistant, broken_serial: None
) -> None:
    """An unreachable controller keeps the user on the form with an error."""
    result = await _start(hass, CONNECTION_TYPE_SERIAL)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
            CONF_NUM_CHANNELS: 8,
            CONF_SCAN_INTERVAL_MS: 2000,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_port_aborts(
    hass: HomeAssistant, fake_serial: FakeDevice
) -> None:
    """The same port cannot be added twice."""
    MockConfigEntry(domain=DOMAIN, unique_id="/dev/ttyUSB0", data={}).add_to_hass(hass)
    result = await _start(hass, CONNECTION_TYPE_SERIAL)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
            CONF_NUM_CHANNELS: 8,
            CONF_SCAN_INTERVAL_MS: 2000,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
