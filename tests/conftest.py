"""Shared fixtures for the TControl LT16 tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest

from .fake_device import FakeDevice, FakeSerial, FakeSocket


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading of custom integrations for every test."""


@pytest.fixture
def device() -> FakeDevice:
    """Return a simulated TControl LT16 controller."""
    return FakeDevice(num_channels=8)


@pytest.fixture
def fake_serial(device: FakeDevice) -> Generator[FakeDevice]:
    """Patch pyserial so the hub talks to the simulated controller."""
    with patch(
        "custom_components.tcontrol.hub.serial.Serial",
        side_effect=lambda *args, **kwargs: FakeSerial(device, *args, **kwargs),
    ):
        yield device


@pytest.fixture
def fake_tcp(device: FakeDevice) -> Generator[FakeDevice]:
    """Patch socket.create_connection so the hub talks to the simulated controller."""

    def _connect(address: tuple[str, int], timeout: float | None = None) -> FakeSocket:
        return FakeSocket(device, address, timeout)

    with patch(
        "custom_components.tcontrol.hub.socket.create_connection", side_effect=_connect
    ):
        yield device


@pytest.fixture
def broken_serial() -> Generator[None]:
    """Patch pyserial so every open fails (device unplugged)."""
    import serial

    with patch(
        "custom_components.tcontrol.hub.serial.Serial",
        side_effect=serial.SerialException("could not open port"),
    ):
        yield


@pytest.fixture
def broken_tcp() -> Generator[None]:
    """Patch socket.create_connection so every connect fails."""
    with patch(
        "custom_components.tcontrol.hub.socket.create_connection",
        side_effect=TimeoutError("timed out"),
    ):
        yield
