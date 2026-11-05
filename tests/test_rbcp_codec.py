from __future__ import annotations

import unittest

from sitcp_host.core.rbcp import (
    RbcpCommand,
    build_read_request,
    build_reply,
    build_write_request,
    parse_reply,
    parse_request,
    validate_reply,
)
from sitcp_host.errors import RbcpProtocolError


class RbcpCodecTests(unittest.TestCase):
    def test_build_read_request_matches_wire_format(self) -> None:
        packet = build_read_request(0x010A, length=1, packet_id=0x42)
        self.assertEqual(
            packet,
            bytes.fromhex("FF C0 42 01 00 00 01 0A"),
        )

    def test_build_write_request_matches_wire_format(self) -> None:
        packet = build_write_request(0x0020, b"\x01", packet_id=0x42)
        self.assertEqual(
            packet,
            bytes.fromhex("FF 80 42 01 00 00 00 20 01"),
        )

    def test_request_round_trip(self) -> None:
        packet = build_write_request(0x0000, b"\x34\x12", packet_id=7)
        request = parse_request(packet)
        self.assertEqual(request.command, RbcpCommand.WRITE)
        self.assertEqual(request.address, 0)
        self.assertEqual(request.data, b"\x34\x12")
        self.assertEqual(request.length, 2)

    def test_reply_round_trip_and_validation(self) -> None:
        request = parse_request(
            build_read_request(0x010A, length=1, packet_id=0x42)
        )
        reply = parse_reply(
            build_reply(
                RbcpCommand.READ,
                0x010A,
                packet_id=0x42,
                data=b"\x02",
            )
        )
        validate_reply(reply, request)
        self.assertFalse(reply.bus_error)
        self.assertEqual(reply.data, b"\x02")

    def test_bus_error_reply_is_preserved(self) -> None:
        reply = parse_reply(
            build_reply(
                RbcpCommand.READ,
                0x010A,
                packet_id=1,
                bus_error=True,
            )
        )
        self.assertTrue(reply.bus_error)
        self.assertEqual(reply.length, 0)

    def test_command_with_ack_flag_is_rejected(self) -> None:
        packet = bytearray(build_read_request(0, length=1, packet_id=1))
        packet[1] |= 0x08
        with self.assertRaises(RbcpProtocolError):
            parse_request(bytes(packet))

    def test_reply_with_wrong_payload_length_is_rejected(self) -> None:
        packet = build_reply(
            RbcpCommand.READ,
            0,
            packet_id=1,
            data=b"\x01",
        )
        with self.assertRaises(RbcpProtocolError):
            parse_reply(packet[:-1])

    def test_zero_length_request_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_read_request(0, length=0, packet_id=1)


if __name__ == "__main__":
    unittest.main()

