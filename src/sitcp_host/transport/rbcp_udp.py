"""UDP transport for RBCP slow-control requests."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable
from typing import Final

from sitcp_host.core.rbcp import (
    RbcpCommand,
    RbcpReply,
    RbcpRequest,
    build_read_request,
    build_write_request,
    parse_reply,
    parse_request,
    validate_reply,
)
from sitcp_host.errors import (
    RbcpBusError,
    RbcpProtocolError,
    RbcpTimeoutError,
)

_MAX_RBCP_DATAGRAM: Final[int] = 4096


class RbcpUdpClient:
    """Serialize RBCP requests over one IPv4 UDP socket."""

    def __init__(
        self,
        host: str,
        *,
        port: int = 4660,
        timeout_s: float = 0.8,
        retries: int = 2,
        initial_packet_id: int = 0,
        socket_factory: Callable[[], socket.socket] | None = None,
    ) -> None:
        if not host:
            raise ValueError("host must not be empty")
        if not 1 <= port <= 65535:
            raise ValueError("port must be in the range 1..65535")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if not 0 <= retries <= 10:
            raise ValueError("retries must be in the range 0..10")
        if not 0 <= initial_packet_id <= 0xFF:
            raise ValueError("initial_packet_id must be in the range 0..255")

        self.host = host
        self.port = port
        self.timeout_s = float(timeout_s)
        self.retries = retries
        self._next_packet_id = initial_packet_id
        self._socket_factory = socket_factory or (
            lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        )
        self._socket: socket.socket | None = None
        self._peer: tuple[str, int] | None = None
        self._lock = threading.Lock()

    @property
    def endpoint(self) -> tuple[str, int]:
        return self.host, self.port

    def __enter__(self) -> RbcpUdpClient:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def read(self, address: int, length: int = 1) -> RbcpReply:
        if not 1 <= length <= 0xFF:
            raise ValueError("read length must be in the range 1..255")
        packet_id = self._allocate_packet_id()
        request = parse_request(
            build_read_request(address, length=length, packet_id=packet_id)
        )
        return self._exchange(request)

    def write(self, address: int, data: bytes) -> RbcpReply:
        payload = bytes(data)
        if not payload:
            raise ValueError("RBCP write data must not be empty")
        if len(payload) > 0xFF:
            raise ValueError("RBCP write data cannot exceed 255 bytes")
        packet_id = self._allocate_packet_id()
        request = parse_request(
            build_write_request(address, payload, packet_id=packet_id)
        )
        return self._exchange(request)

    def _allocate_packet_id(self) -> int:
        with self._lock:
            packet_id = self._next_packet_id
            self._next_packet_id = (packet_id + 1) & 0xFF
            return packet_id

    def _ensure_socket(self) -> socket.socket:
        if self._socket is not None:
            return self._socket

        try:
            peer_info = socket.getaddrinfo(
                self.host,
                self.port,
                family=socket.AF_INET,
                type=socket.SOCK_DGRAM,
            )[0][4]
        except OSError as exc:
            raise RbcpProtocolError(
                f"cannot resolve RBCP endpoint {self.host}:{self.port}: {exc}"
            ) from exc

        udp_socket = self._socket_factory()
        udp_socket.setblocking(False)
        self._socket = udp_socket
        self._peer = (peer_info[0], peer_info[1])
        return udp_socket

    def _exchange(self, request: RbcpRequest) -> RbcpReply:
        packet = (
            build_read_request(
                request.address,
                length=request.length,
                packet_id=request.packet_id,
            )
            if request.command is RbcpCommand.READ
            else build_write_request(
                request.address,
                request.data,
                packet_id=request.packet_id,
            )
        )

        with self._lock:
            udp_socket = self._ensure_socket()
            assert self._peer is not None
            attempts = self.retries + 1

            for _attempt in range(attempts):
                try:
                    udp_socket.sendto(packet, self._peer)
                except OSError:
                    time.sleep(0.001)
                    continue

                deadline = time.monotonic() + self.timeout_s
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        raw_reply, source = udp_socket.recvfrom(_MAX_RBCP_DATAGRAM)
                    except BlockingIOError:
                        time.sleep(min(0.005, remaining))
                        continue
                    except OSError:
                        time.sleep(min(0.005, remaining))
                        continue

                    if source[0] != self._peer[0] or source[1] != self._peer[1]:
                        continue

                    reply = parse_reply(raw_reply)
                    if reply.packet_id != request.packet_id:
                        continue
                    validate_reply(reply, request)
                    if reply.bus_error:
                        raise RbcpBusError(
                            f"SiTCP reported a bus error for "
                            f"address 0x{request.address:08X}"
                        )
                    return reply

        raise RbcpTimeoutError(
            f"no matching RBCP ACK from {self.host}:{self.port} "
            f"after {attempts} attempt(s)"
        )

    def read_u8(self, address: int) -> int:
        return self.read(address, 1).data[0]

    def write_u8(self, address: int, value: int) -> None:
        if not 0 <= value <= 0xFF:
            raise ValueError("RBCP byte value must be in the range 0..255")
        self.write(address, bytes((value,)))

