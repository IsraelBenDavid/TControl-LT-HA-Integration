"""Communication hub for the TControl LT16 controller."""

from __future__ import annotations

import logging
import socket

import serial

from .const import (
    CONF_CONNECTION_TYPE,
    CONF_SERIAL_PORT,
    CONF_TCP_HOST,
    CONF_TCP_PORT,
    CONNECTION_TYPE_SERIAL,
    DEFAULT_TCP_PORT,
)

_LOGGER = logging.getLogger(__name__)

# Serial settings per protocol spec
BAUD_RATE = 9600
SERIAL_TIMEOUT = 1


def _channel_to_hex(channel: int) -> str:
    """Convert a 1-based channel number to the single hex character used by the protocol.

    Channels 1-9 map to '1'-'9', channels 10-16 map to 'A'-'F'.
    """
    return format(channel, "X")


class TControlHub:
    """Manages communication with the TControl LT16 hardware."""

    def __init__(self, config: dict) -> None:
        """Initialise with a config-entry data dict."""
        self._connection_type: str = config[CONF_CONNECTION_TYPE]
        if self._connection_type == CONNECTION_TYPE_SERIAL:
            self._port: str = config[CONF_SERIAL_PORT]
            self._host: str | None = None
            self._tcp_port: int | None = None
        else:
            self._port = ""
            self._host = config[CONF_TCP_HOST]
            self._tcp_port = int(config.get(CONF_TCP_PORT, DEFAULT_TCP_PORT))

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def identifier(self) -> str:
        """Return a stable identifier for the physical device."""
        if self._connection_type == CONNECTION_TYPE_SERIAL:
            return self._port
        return f"{self._host}:{self._tcp_port}"

    # ------------------------------------------------------------------
    # Command builders
    # ------------------------------------------------------------------

    @staticmethod
    def build_command(channel: int, turn_on: bool) -> str:
        """Build the ASCII command string for a given channel and action."""
        hex_ch = _channel_to_hex(channel)
        action = "ONE" if turn_on else "OFE"
        return f"S00{hex_ch}{action}"

    # ------------------------------------------------------------------
    # I/O — these are blocking and MUST be called via async_add_executor_job
    # ------------------------------------------------------------------

    def send_command(self, channel: int, turn_on: bool) -> None:
        """Open connection, send command, close connection (blocking)."""
        cmd = self.build_command(channel, turn_on)
        if self._connection_type == CONNECTION_TYPE_SERIAL:
            self._send_serial(cmd)
        else:
            self._send_tcp(cmd)

    def test_connection(self) -> bool:
        """Try to open and immediately close the connection (blocking).

        Returns True on success, False on failure.
        """
        try:
            if self._connection_type == CONNECTION_TYPE_SERIAL:
                with serial.Serial(self._port, BAUD_RATE, timeout=SERIAL_TIMEOUT):
                    pass
            else:
                sock = socket.create_connection((self._host, self._tcp_port), timeout=SERIAL_TIMEOUT)
                sock.close()
        except (OSError, serial.SerialException) as err:
            _LOGGER.debug("Connection test failed: %s", err)
            return False
        return True

    # ------------------------------------------------------------------
    # Private transport methods
    # ------------------------------------------------------------------

    def _send_serial(self, cmd: str) -> None:
        """Send *cmd* over a serial port (blocking)."""
        _LOGGER.debug("Serial TX [%s]: %s", self._port, cmd)
        try:
            with serial.Serial(self._port, BAUD_RATE, timeout=SERIAL_TIMEOUT) as ser:
                ser.write(cmd.encode("ascii"))
        except serial.SerialException as err:
            _LOGGER.error("Serial send failed on %s: %s", self._port, err)
            raise

    def _send_tcp(self, cmd: str) -> None:
        """Send *cmd* over a TCP socket (blocking)."""
        _LOGGER.debug("TCP TX [%s:%s]: %s", self._host, self._tcp_port, cmd)
        try:
            with socket.create_connection(
                (self._host, self._tcp_port), timeout=SERIAL_TIMEOUT
            ) as sock:
                sock.sendall(cmd.encode("ascii"))
        except OSError as err:
            _LOGGER.error(
                "TCP send failed to %s:%s: %s", self._host, self._tcp_port, err
            )
            raise
