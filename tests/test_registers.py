from __future__ import annotations

import unittest
from pathlib import Path

from sitcp_host.core.device import RbcpDevice
from sitcp_host.core.registers import load_profile
from sitcp_host.errors import AddressRangeError, RegisterError


class StubClient:
    def __init__(self) -> None:
        self.memory = {
            0x0000: 0x34,
            0x0001: 0x12,
            0x010A: 0x02,
        }
        self.writes: list[tuple[int, bytes]] = []

    def read(self, address: int, length: int = 1):
        class Reply:
            data = b""

        reply = Reply()
        reply.data = bytes(
            self.memory.get(address + offset, 0) for offset in range(length)
        )
        return reply

    def write(self, address: int, data: bytes):
        self.writes.append((address, data))
        for offset, value in enumerate(data):
            self.memory[address + offset] = value
        return object()


class RegisterProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = Path(__file__).resolve().parents[1] / "config" / "registers.toml"
        cls.profile = load_profile(config)

    def setUp(self) -> None:
        self.client = StubClient()
        self.device = RbcpDevice(self.client, self.profile)

    def test_profile_contains_expected_maps(self) -> None:
        self.assertEqual(self.profile.rbcp_port, 4660)
        self.assertEqual(self.profile.tcp_port, 24)
        self.assertEqual(self.profile.register("temperature").address, 0x0108)
        self.assertEqual(self.profile.register("threshold_ch7").address, 0x000E)
        self.assertTrue(self.profile.register("software_trigger").momentary)
        self.assertTrue(self.profile.register("ad9528_reset").momentary)
        self.assertTrue(self.profile.register("trigger_buffer_clear").momentary)

    def test_read_little_endian_register(self) -> None:
        self.assertEqual(self.device.read_register("threshold_ch0"), 0x1234)

    def test_write_little_endian_register(self) -> None:
        self.device.write_register("threshold_ch0", 0xBEEF)
        self.assertEqual(self.client.writes, [(0x0000, b"\xEF\xBE")])
        self.assertEqual(self.device.read_register("threshold_ch0"), 0xBEEF)

    def test_read_only_space_rejects_write(self) -> None:
        with self.assertRaises(AddressRangeError):
            self.device.write_bytes(0x010A, b"\x00")

    def test_bit_width_is_enforced(self) -> None:
        with self.assertRaises(RegisterError):
            self.device.write_register("trigger_mode", 8)

    def test_pulse_returns_register_to_zero(self) -> None:
        self.device.pulse_register("software_trigger")
        self.assertEqual(
            self.client.writes,
            [(0x002A, b"\x01"), (0x002A, b"\x00")],
        )

    def test_raw_address_outside_catalog_is_rejected(self) -> None:
        with self.assertRaises(AddressRangeError):
            self.device.read_bytes(0x00000080, 1)


if __name__ == "__main__":
    unittest.main()

