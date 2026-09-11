"""Communication hub for the TControl LT16 controller.

The controller speaks a tiny ASCII protocol over a serial line (optionally
behind a TCP-to-serial bridge):

* ``S00<HEX>ONE`` / ``S00<HEX>OFE`` switch relay ``<HEX>`` (1-9, A-F) on / off.
* ``S00QLE`` asks for the state of every relay.  The controller answers with
  ``A00<STATUS_BITS>E`` where ``STATUS_BITS`` is one ``0``/``1`` character per
  channel (8 characters on an 8-channel board, 16 on a 16-channel board).

Every method that touches the wire is blocking and MUST be run in an executor
thread.  The hub opens the port, performs one exchange and closes it again;
a lock guarantees that the periodic state poll and relay commands never open
the port at the same time (serial-to-TCP bridges typically accept a single
client, and interleaved serial traffic corrupts both exchanges).
"""

from __future__ import annotations

import logging
import re
import socket
import threading
import time

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
SERIAL_TIMEOUT = 1.0

# Upper bound for one query/response exchange, in seconds.  Protects against a
# controller (or bridge) that keeps streaming data without ever sending a frame.
RESPONSE_DEADLINE = 3.0

# Protocol markers
QUERY_COMMAND = "S00QLE"
STATUS_FRAME = re.compile(r"A00([01]{1,16})E")


class TControlError(Exception):
    """Base error for hub failures."""


class TControlConnectionError(TControlError):
    """The controller could not be reached or the transport failed."""


class TControlResponseError(TControlError):
    """The controller answered with something that is not a status frame."""


def _channel_to_hex(channel: int) -> str:
    """Convert a 1-based channel number to the hex character(s) used by the protocol.

    Channels 1-9 map to '1'-'9', channels 10-15 map to 'A'-'F',
    channel 16 maps to '10'.
    """
    return format(channel, "X")


def parse_status_frame(raw: str) -> dict[int, bool]:
    """Extract the relay states from a raw response buffer.

    The buffer may contain noise before the frame (for example an echo of the
    ``S00QLE`` command from the bridge), so the frame is searched rather than
    matched from the start.  Returns a dict mapping the 1-based channel number
    to ``True`` (on) / ``False`` (off).
    """
    match = STATUS_FRAME.search(raw)
    if match is None:
        raise TControlResponseError(f"No status frame in response {raw!r}")
    bits = match.group(1)
    return {channel: bit == "1" for channel, bit in enumerate(bits, start=1)}


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
        # Serialises every open/exchange/close cycle across executor threads.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def identifier(self) -> str:
        """Return a stable identifier for the physical device."""
        if self._connection_type == CONNECTION_TYPE_SERIAL:
            return self._port
        return f"{self._host}:{self._tcp_port}"

    @staticmethod
    def build_command(channel: int, turn_on: bool) -> str:
        """Build the ASCII command string for a given channel and action."""
        hex_ch = _channel_to_hex(channel)
        action = "ONE" if turn_on else "OFE"
        return f"S00{hex_ch}{action}"

    # ------------------------------------------------------------------
    # I/O — blocking, MUST be called via hass.async_add_executor_job
    # ------------------------------------------------------------------

    def send_command(self, channel: int, turn_on: bool) -> None:
        """Open the connection, send a relay command and close it again.

        Raises TControlConnectionError if the command could not be delivered.
        """
        cmd = self.build_command(channel, turn_on)
        with self._lock:
            self._exchange(cmd, expect_reply=False)

    def read_state(self) -> dict[int, bool]:
        """Query the controller for all channel states.

        Returns a dict mapping the 1-based channel number to bool (True = ON).
        Raises TControlConnectionError if the controller cannot be reached and
        TControlResponseError if it does not answer with a status frame.
        """
        with self._lock:
            raw = self._exchange(QUERY_COMMAND, expect_reply=True)
        state = parse_status_frame(raw)
        _LOGGER.debug("State from %s: %s", self.identifier, state)
        return state

    def test_connection(self) -> bool:
        """Check that the controller is reachable and answers a state query."""
        try:
            self.read_state()
        except TControlError as err:
            _LOGGER.debug("Connection test to %s failed: %s", self.identifier, err)
            return False
        return True

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _exchange(self, payload: str, *, expect_reply: bool) -> str:
        """Perform one open → send → (read) → close cycle on the transport."""
        _LOGGER.debug("TX [%s]: %s", self.identifier, payload)
        try:
            if self._connection_type == CONNECTION_TYPE_SERIAL:
                reply = self._exchange_serial(payload, expect_reply)
            else:
                reply = self._exchange_tcp(payload, expect_reply)
        except (OSError, serial.SerialException) as err:
            # SerialException is an IOError subclass, listed for clarity.
            raise TControlConnectionError(
                f"Communication with TControl at {self.identifier} failed: {err}"
            ) from err
        if expect_reply:
            _LOGGER.debug("RX [%s]: %s", self.identifier, reply)
        return reply

    def _exchange_serial(self, payload: str, expect_reply: bool) -> str:
        """Serial transport for one exchange."""
        with serial.Serial(self._port, BAUD_RATE, timeout=SERIAL_TIMEOUT) as ser:
            # Drop anything the controller sent while the port was closed so an
            # old frame is never mistaken for the answer to this query.
            ser.reset_input_buffer()
            ser.write(payload.encode("ascii"))
            # Make sure the bytes really left the port before we close it.
            ser.flush()
            if not expect_reply:
                return ""
            return self._read_frame(lambda: ser.read(max(1, ser.in_waiting)))

    def _exchange_tcp(self, payload: str, expect_reply: bool) -> str:
        """TCP (serial bridge) transport for one exchange."""
        with socket.create_connection(
            (self._host, self._tcp_port), timeout=SERIAL_TIMEOUT
        ) as sock:
            sock.sendall(payload.encode("ascii"))
            if not expect_reply:
                return ""
            sock.settimeout(SERIAL_TIMEOUT)

            def _recv() -> bytes:
                try:
                    return sock.recv(64)
                except TimeoutError:
                    return b""

            return self._read_frame(_recv)

    @staticmethod
    def _read_frame(read_chunk) -> str:
        """Accumulate data until a complete A00...E frame is seen or we time out.

        ``read_chunk`` returns b"" when the transport timed out.  Reading stops
        at the first complete frame rather than at the first "E" so an echoed
        command (``S00QLE`` also ends with an E) cannot truncate the answer.
        """
        deadline = time.monotonic() + RESPONSE_DEADLINE
        buf = b""
        while time.monotonic() < deadline:
            chunk = read_chunk()
            if not chunk:
                break
            buf += chunk
            text = buf.decode("ascii", errors="replace")
            if STATUS_FRAME.search(text):
                return text
        return buf.decode("ascii", errors="replace")
