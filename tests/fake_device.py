"""A simulated TControl LT16 controller for tests.

Implements the reverse-engineered ASCII protocol:

* ``S00<HEX>ONE`` / ``S00<HEX>OFE`` switch a relay on / off.
* ``S00QLE`` requests the state of all relays; the controller answers
  ``A00<STATUS_BITS>E`` where STATUS_BITS is 8 or 16 ``0``/``1`` characters.
"""

from __future__ import annotations

import re
import threading

_SET_RE = re.compile(r"^S00([0-9A-F]{1,2})(ONE|OFE)$")


class FakeDevice:
    """State machine for the simulated controller."""

    def __init__(self, num_channels: int = 8, *, echo: bool = False) -> None:
        """Initialise with all relays off."""
        self.num_channels = num_channels
        self.relays: dict[int, bool] = dict.fromkeys(range(1, num_channels + 1), False)
        self.echo = echo
        self.received: list[str] = []
        self.opens = 0
        self.concurrent_opens = 0
        self.max_concurrent_opens = 0
        self.respond = True
        self.offline = False
        self._lock = threading.Lock()

    # -- connection accounting --------------------------------------------

    def open(self) -> None:
        """Track a new connection to the controller."""
        if self.offline:
            raise OSError("device unplugged")
        with self._lock:
            self.opens += 1
            self.concurrent_opens += 1
            self.max_concurrent_opens = max(
                self.max_concurrent_opens, self.concurrent_opens
            )

    def close(self) -> None:
        """Track a closed connection."""
        with self._lock:
            self.concurrent_opens -= 1

    # -- protocol -----------------------------------------------------------

    def status_response(self) -> str:
        """Return the A00...E status frame."""
        bits = "".join("1" if self.relays[ch] else "0" for ch in sorted(self.relays))
        return f"A00{bits}E"

    def handle(self, payload: str) -> bytes:
        """Process a command and return the bytes the controller sends back."""
        self.received.append(payload)
        out = payload if self.echo else ""
        if not self.respond:
            return out.encode("ascii")
        if payload == "S00QLE":
            out += self.status_response()
        elif match := _SET_RE.match(payload):
            channel = int(match.group(1), 16)
            if channel in self.relays:
                self.relays[channel] = match.group(2) == "ONE"
        return out.encode("ascii")


class FakeSerial:
    """Stand-in for ``serial.Serial`` bound to a FakeDevice."""

    def __init__(
        self, device: FakeDevice, port: str, baudrate: int = 9600, **kwargs
    ) -> None:
        """Record the open parameters."""
        self.device = device
        self.port = port
        self.baudrate = baudrate
        self.timeout = kwargs.get("timeout")
        self._rx = b""
        self.is_open = False

    def __enter__(self) -> FakeSerial:
        """Open the port."""
        self.is_open = True
        self.device.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the port."""
        self.close()

    def close(self) -> None:
        """Close the port."""
        if self.is_open:
            self.is_open = False
            self.device.close()

    def reset_input_buffer(self) -> None:
        """Discard unread data."""
        self._rx = b""

    def flush(self) -> None:
        """Wait until all written data is transmitted (no-op for the fake)."""

    @property
    def in_waiting(self) -> int:
        """Number of bytes waiting to be read."""
        return len(self._rx)

    def write(self, data: bytes) -> int:
        """Send a command to the device."""
        self._rx += self.device.handle(data.decode("ascii"))
        return len(data)

    def read(self, size: int = 1) -> bytes:
        """Read up to ``size`` bytes, or b'' on timeout."""
        chunk, self._rx = self._rx[:size], self._rx[size:]
        return chunk


class FakeSocket:
    """Stand-in for a TCP socket returned by ``socket.create_connection``."""

    def __init__(
        self, device: FakeDevice, address: tuple[str, int], timeout: float | None
    ) -> None:
        """Connect to the simulated bridge."""
        self.device = device
        self.address = address
        self.timeout = timeout
        self._rx = b""
        self._closed = False
        self.device.open()

    def __enter__(self) -> FakeSocket:
        """Enter context."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the socket."""
        self.close()

    def settimeout(self, timeout: float | None) -> None:
        """Store the timeout."""
        self.timeout = timeout

    def sendall(self, data: bytes) -> None:
        """Send a command to the device."""
        self._rx += self.device.handle(data.decode("ascii"))

    def recv(self, size: int) -> bytes:
        """Receive up to ``size`` bytes; raise timeout when nothing is pending."""

        if not self._rx:
            raise TimeoutError("timed out")
        chunk, self._rx = self._rx[:size], self._rx[size:]
        return chunk

    def close(self) -> None:
        """Close the socket."""
        if not self._closed:
            self._closed = True
            self.device.close()
