from __future__ import annotations

import unittest

from sitcp_host.core.device import RbcpDevice
from sitcp_host.core.registers import load_profile
from sitcp_host.errors import RbcpBusError, RbcpTimeoutError
from sitcp_host.testing.fake_rbcp import FakeRbcpServer
from sitcp_host.transport.rbcp_udp import RbcpUdpClient
from pathlib import Path


class RbcpUdpClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = Path(__file__).resolve().parents[1] / "config" / "registers.toml"
        cls.profile = load_profile(config)

    def setUp(self) -> None:
        self.server = FakeRbcpServer()
        self.server.set_bytes(0x0108, b"\x34\x12")
        self.server.set_bytes(0x010A, b"\x02")
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()

    def make_client(self, *, timeout: float = 0.2, retries: int = 1) -> RbcpUdpClient:
        return RbcpUdpClient(
            self.server.host,
            port=self.server.port,
            timeout_s=timeout,
            retries=retries,
        )

    def test_read_over_real_udp_socket(self) -> None:
        with self.make_client() as client:
            reply = client.read(0x010A, 1)
        self.assertEqual(reply.data, b"\x02")

    def test_write_over_real_udp_socket(self) -> None:
        with self.make_client() as client:
            client.write(0x0020, b"\x05")
        self.assertEqual(self.server.get_bytes(0x0020, 1), b"\x05")

    def test_retry_after_dropped_request(self) -> None:
        self.server.drop_requests = 1
        with self.make_client(timeout=0.05, retries=1) as client:
            reply = client.read(0x010A, 1)
        self.assertEqual(reply.data, b"\x02")

    def test_timeout_after_all_attempts(self) -> None:
        self.server.drop_requests = 10
        with self.make_client(timeout=0.03, retries=0) as client:
            with self.assertRaises(RbcpTimeoutError):
                client.read(0x010A, 1)

    def test_wrong_packet_id_is_ignored(self) -> None:
        self.server.response_id_delta = 1
        with self.make_client(timeout=0.03, retries=0) as client:
            with self.assertRaises(RbcpTimeoutError):
                client.read(0x010A, 1)

    def test_bus_error_is_reported(self) -> None:
        self.server.error_requests = 1
        with self.make_client() as client:
            with self.assertRaises(RbcpBusError):
                client.read(0x010A, 1)

    def test_device_layer_uses_transport(self) -> None:
        with self.make_client() as client:
            device = RbcpDevice(client, self.profile)
            self.assertEqual(device.read_register("temperature"), 0x1234)


if __name__ == "__main__":
    unittest.main()

