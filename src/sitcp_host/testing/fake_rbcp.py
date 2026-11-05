"""Local UDP device used to develop and test the RBCP client without hardware."""

from __future__ import annotations

import argparse
import socket
import threading
import time

from sitcp_host.core.rbcp import (
    RbcpCommand,
    build_reply,
    parse_request,
)
from sitcp_host.errors import RbcpProtocolError


class FakeRbcpServer:
    """Threaded in-memory SiTCP RBCP endpoint."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._requested_host = host
        self._requested_port = port
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.settimeout(0.05)
        self._socket.bind((host, port))
        self.host, self.port = self._socket.getsockname()
        self.memory: dict[int, int] = {}
        self.drop_requests = 0
        self.error_requests = 0
        self.response_id_delta = 0
        self.last_error: Exception | None = None
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._serve,
            name=f"fake-rbcp-{self.port}",
            daemon=True,
        )

    def __enter__(self) -> FakeRbcpServer:
        self.start()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.stop()

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._socket.close()

    def set_bytes(self, address: int, data: bytes) -> None:
        for offset, value in enumerate(data):
            self.memory[address + offset] = value

    def get_bytes(self, address: int, length: int) -> bytes:
        return bytes(self.memory.get(address + offset, 0) for offset in range(length))

    def _serve(self) -> None:
        while not self._stop_event.is_set():
            try:
                packet, peer = self._socket.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            if self.drop_requests:
                self.drop_requests -= 1
                continue

            try:
                request = parse_request(packet)
            except RbcpProtocolError as exc:
                self.last_error = exc
                continue

            if self.error_requests:
                self.error_requests -= 1
                reply = build_reply(
                    request.command,
                    request.address,
                    packet_id=request.packet_id,
                    bus_error=True,
                )
            elif request.command is RbcpCommand.READ:
                data = self.get_bytes(request.address, request.length)
                reply = build_reply(
                    request.command,
                    request.address,
                    packet_id=request.packet_id,
                    data=data,
                )
            else:
                self.set_bytes(request.address, request.data)
                reply = build_reply(
                    request.command,
                    request.address,
                    packet_id=request.packet_id,
                    data=request.data,
                )

            if self.response_id_delta:
                reply = (
                    reply[:2]
                    + bytes(((reply[2] + self.response_id_delta) & 0xFF,))
                    + reply[3:]
                )

            try:
                self._socket.sendto(reply, peer)
            except OSError as exc:
                self.last_error = exc
                break


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a local fake SiTCP RBCP device")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4660)
    args = parser.parse_args(argv)

    server = FakeRbcpServer(args.host, args.port)
    server.set_bytes(0x0108, b"\x34\x12")
    server.set_bytes(0x010A, b"\x02")
    server.set_bytes(0x010B, b"\x00")
    server.start()
    print(f"Fake RBCP device listening on {server.host}:{server.port}")
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

