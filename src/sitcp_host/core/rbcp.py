"""Encoding and validation for the SiTCP Remote Bus Control Protocol."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Final

from sitcp_host.errors import RbcpProtocolError

RBCP_VERSION: Final[int] = 0xF
RBCP_PACKET_TYPE: Final[int] = 0xF
RBCP_HEADER_SIZE: Final[int] = 8
RBCP_MAX_DATA_LENGTH: Final[int] = 0xFF


class RbcpCommand(IntEnum):
    WRITE = 0x8
    READ = 0xC


@dataclass(frozen=True, slots=True)
class RbcpRequest:
    command: RbcpCommand
    packet_id: int
    address: int
    length: int
    data: bytes = b""


@dataclass(frozen=True, slots=True)
class RbcpReply:
    command: RbcpCommand
    packet_id: int
    address: int
    length: int
    data: bytes
    flag: int

    @property
    def bus_error(self) -> bool:
        return bool(self.flag & 0x01)


def _check_u8(value: int, name: str) -> None:
    if not 0 <= value <= 0xFF:
        raise ValueError(f"{name} must be in the range 0..255")


def _check_address(address: int) -> None:
    if not 0 <= address <= 0xFFFFFFFF:
        raise ValueError("address must be a 32-bit unsigned integer")


def build_request(
    command: RbcpCommand,
    address: int,
    *,
    packet_id: int,
    length: int | None = None,
    data: bytes = b"",
) -> bytes:
    """Build a complete RBCP command datagram payload."""

    _check_u8(packet_id, "packet_id")
    _check_address(address)

    command = RbcpCommand(command)
    payload = bytes(data)
    if length is None:
        length = len(payload)

    if not 1 <= length <= RBCP_MAX_DATA_LENGTH:
        raise ValueError("RBCP data length must be in the range 1..255")

    if command is RbcpCommand.READ:
        if payload:
            raise ValueError("RBCP read requests must not contain data")
    elif len(payload) != length:
        raise ValueError("write data length does not match the length field")

    return bytes(
        (
            (RBCP_VERSION << 4) | RBCP_PACKET_TYPE,
            (int(command) << 4),
            packet_id,
            length,
        )
    ) + address.to_bytes(4, "big") + payload


def build_read_request(address: int, *, length: int, packet_id: int) -> bytes:
    return build_request(
        RbcpCommand.READ,
        address,
        packet_id=packet_id,
        length=length,
    )


def build_write_request(address: int, data: bytes, *, packet_id: int) -> bytes:
    return build_request(
        RbcpCommand.WRITE,
        address,
        packet_id=packet_id,
        data=data,
    )


def build_reply(
    command: RbcpCommand,
    address: int,
    *,
    packet_id: int,
    data: bytes = b"",
    bus_error: bool = False,
) -> bytes:
    """Build an RBCP ACK datagram payload, primarily for simulators and tests."""

    _check_u8(packet_id, "packet_id")
    _check_address(address)
    command = RbcpCommand(command)
    payload = bytes(data)
    if len(payload) > RBCP_MAX_DATA_LENGTH:
        raise ValueError("RBCP reply data cannot exceed 255 bytes")
    if not bus_error and not payload:
        raise ValueError("a normal RBCP reply must contain at least one data byte")

    flag = 0x08 | (0x01 if bus_error else 0)
    return bytes(
        (
            (RBCP_VERSION << 4) | RBCP_PACKET_TYPE,
            (int(command) << 4) | flag,
            packet_id,
            len(payload),
        )
    ) + address.to_bytes(4, "big") + payload


def parse_request(packet: bytes) -> RbcpRequest:
    """Parse and validate an RBCP command packet."""

    raw = bytes(packet)
    if len(raw) < RBCP_HEADER_SIZE:
        raise RbcpProtocolError("RBCP request is shorter than 8 bytes")
    if raw[0] != 0xFF:
        raise RbcpProtocolError("invalid RBCP VER/TYPE; expected 0xFF")

    command_code = raw[1] >> 4
    flag = raw[1] & 0x0F
    try:
        command = RbcpCommand(command_code)
    except ValueError as exc:
        raise RbcpProtocolError(f"unsupported RBCP command 0x{command_code:X}") from exc
    if flag != 0:
        raise RbcpProtocolError("command packets must have FLAG=0")

    packet_id = raw[2]
    length = raw[3]
    address = int.from_bytes(raw[4:8], "big")
    payload = raw[RBCP_HEADER_SIZE:]
    if length == 0:
        raise RbcpProtocolError("RBCP data length must not be zero")

    if command is RbcpCommand.READ:
        if payload:
            raise RbcpProtocolError("RBCP read request contains unexpected data")
    elif len(payload) != length:
        raise RbcpProtocolError("RBCP write request length does not match its payload")

    return RbcpRequest(
        command=command,
        packet_id=packet_id,
        address=address,
        length=length,
        data=payload,
    )


def parse_reply(packet: bytes) -> RbcpReply:
    """Parse and validate an RBCP ACK packet."""

    raw = bytes(packet)
    if len(raw) < RBCP_HEADER_SIZE:
        raise RbcpProtocolError("RBCP reply is shorter than 8 bytes")
    if raw[0] != 0xFF:
        raise RbcpProtocolError("invalid RBCP VER/TYPE; expected 0xFF")

    command_code = raw[1] >> 4
    flag = raw[1] & 0x0F
    try:
        command = RbcpCommand(command_code)
    except ValueError as exc:
        raise RbcpProtocolError(f"unsupported RBCP command 0x{command_code:X}") from exc
    if not flag & 0x08:
        raise RbcpProtocolError("received an RBCP command, expected an ACK")

    packet_id = raw[2]
    length = raw[3]
    address = int.from_bytes(raw[4:8], "big")
    payload = raw[RBCP_HEADER_SIZE:]
    if len(payload) != length:
        raise RbcpProtocolError(
            f"RBCP reply length field is {length}, but payload has {len(payload)} bytes"
        )
    if length == 0 and not flag & 0x01:
        raise RbcpProtocolError("normal RBCP reply contains no data")

    return RbcpReply(
        command=command,
        packet_id=packet_id,
        address=address,
        length=length,
        data=payload,
        flag=flag,
    )


def validate_reply(reply: RbcpReply, request: RbcpRequest) -> None:
    """Check that a reply belongs to the command that is awaiting an ACK."""

    if reply.packet_id != request.packet_id:
        raise RbcpProtocolError("RBCP reply ID does not match the request")
    if reply.command is not request.command:
        raise RbcpProtocolError("RBCP reply command does not match the request")
    if reply.address != request.address:
        raise RbcpProtocolError("RBCP reply address does not match the request")
    if not reply.bus_error and reply.length != request.length:
        raise RbcpProtocolError("RBCP reply length does not match the request")

