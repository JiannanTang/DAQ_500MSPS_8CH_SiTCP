"""TCP transport for the FPGA ADC data stream."""

from __future__ import annotations

import socket


class TcpDataClient:
    """Small socket wrapper that leaves frame parsing to the core layer."""

    def __init__(self, host: str, port: int, *, connect_timeout_s: float = 3.0) -> None:
        if not host:
            raise ValueError("host must not be empty")
        if not 1 <= port <= 65535:
            raise ValueError("port must be in the range 1..65535")
        if connect_timeout_s <= 0:
            raise ValueError("connect_timeout_s must be positive")
        self.host = host
        self.port = port
        self.connect_timeout_s = connect_timeout_s
        self._socket: socket.socket | None = None

    def connect(self) -> None:
        self.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.connect_timeout_s)
        try:
            sock.connect((self.host, self.port))
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(0.1)
        except OSError:
            sock.close()
            raise
        self._socket = sock

    def recv(self, size: int) -> bytes:
        if self._socket is None:
            raise OSError("TCP data client is not connected")
        return self._socket.recv(size)

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._socket.close()
            self._socket = None

