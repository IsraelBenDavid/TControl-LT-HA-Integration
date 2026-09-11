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

# Protocol markers
QUERY_COMMAND = "S00QLE"
RESPONSE_PREFIX = "A00"
RESPONSE_END = "E"


def _channel_to_hex(channel: int) -> str:
    """Convert a 1-based channel number to the hex character(s) used by the protocol.

    Channels 1-9 map to '1'-'9', channels 10-15 map to 'A'-'F',
    channel 16 maps to '10'.
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

    def read_state(self) -> dict[int, bool]:
        """Query the controller for all channel states (blocking).

        Returns a dict mapping 1-based channel number to bool (True = ON).
        Returns an empty dict on communication or parse failure.
        """
        try:
            if self._connection_type == CONNECTION_TYPE_SERIAL:
                raw = self._query_serial()
            else:
                raw = self._query_tcp()
        except (OSError, serial.SerialException) as err:
            _LOGGER.error("Failed to query state: %s", err)
            return {}

        return self._parse_response(raw)

    def test_connection(self) -> bool:
        """Try to open and immediately close the connection (blocking).

        Returns True on success, False on failure.
        """
        try:
            if self._connection_type == CONNECTION_TYPE_SERIAL:
                with serial.Serial(self._port, BAUD_RATE, timeout=SERIAL_TIMEOUT):
                    pass
            else:
                sock = socket.create_connection(
                    (self._host, self._tcp_port), timeout=SERIAL_TIMEOUT
                )
                sock.close()
        except (OSError, serial.SerialException) as err:
            _LOGGER.debug("Connection test failed: %s", err)
            return False
        return True

    # ------------------------------------------------------------------
    # Query transport methods
    # ------------------------------------------------------------------

    def _query_serial(self) -> str:
        """Send the query command over serial and return the raw response."""
        _LOGGER.debug("Serial TX [%s]: %s", self._port, QUERY_COMMAND)
        with serial.Serial(self._port, BAUD_RATE, timeout=SERIAL_TIMEOUT) as ser:
            ser.write(QUERY_COMMAND.encode("ascii"))
            response = self._read_until_end_serial(ser)
        _LOGGER.debug("Serial RX [%s]: %s", self._port, response)
        return response

    def _query_tcp(self) -> str:
        """Send the query command over TCP and return the raw response."""
        _LOGGER.debug("TCP TX [%s:%s]: %s", self._host, self._tcp_port, QUERY_COMMAND)
        with socket.create_connection(
            (self._host, self._tcp_port), timeout=SERIAL_TIMEOUT
        ) as sock:
            sock.sendall(QUERY_COMMAND.encode("ascii"))
            response = self._read_until_end_tcp(sock)
        _LOGGER.debug("TCP RX [%s:%s]: %s", self._host, self._tcp_port, response)
        return response

    # ------------------------------------------------------------------
    # Response reading helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_until_end_serial(ser: serial.Serial) -> str:
        """Read from serial port until 'E' terminator or timeout."""
        buf = b""
        while True:
            chunk = ser.read(1)
            if not chunk:
                # Timeout — return whatever we have
                break
            buf += chunk
            if chunk == b"E":
                break
        return buf.decode("ascii", errors="replace")

    @staticmethod
    def _read_until_end_tcp(sock: socket.socket) -> str:
        """Read from TCP socket until 'E' terminator or timeout."""
        sock.settimeout(SERIAL_TIMEOUT)
        buf = b""
        while True:
            try:
                chunk = sock.recv(1)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            if chunk == b"E":
                break
        return buf.decode("ascii", errors="replace")

    # ------------------------------------------------------------------
    # Response parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: str) -> dict[int, bool]:
        """Parse a response like 'A0011111100E' into {channel: bool}.

        Expected format: A00[STATUS_BITS]E
        STATUS_BITS length is dynamic (8 or 16 depending on hardware).
        """
        raw = raw.strip()
        if not raw.startswith(RESPONSE_PREFIX) or not raw.endswith(RESPONSE_END):
            _LOGGER.warning("Invalid response format: %r", raw)
            return {}

        status_bits = raw[len(RESPONSE_PREFIX) : -len(RESPONSE_END)]

        if not status_bits or not all(c in ("0", "1") for c in status_bits):
            _LOGGER.warning("Invalid status bits in response: %r", status_bits)
            return {}

        return {
            channel: bit == "1"
            for channel, bit in enumerate(status_bits, start=1)
        }

    # ------------------------------------------------------------------
    # Private send-only transport methods
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
