"""Device profile and register catalog loaded from a TOML file."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sitcp_host.errors import AddressRangeError, RegisterLookupError, RbcpProtocolError


@dataclass(frozen=True, slots=True)
class AddressSpace:
    name: str
    start: int
    end: int
    writable: bool

    def contains(self, address: int, length: int = 1) -> bool:
        if length < 1:
            return False
        return self.start <= address and address + length - 1 <= self.end


@dataclass(frozen=True, slots=True)
class RegisterDefinition:
    name: str
    address: int
    width: int
    access: str
    description: str
    bit_width: int | None = None
    group: str = ""
    unit: str = ""
    momentary: bool = False

    @property
    def readable(self) -> bool:
        return self.access in {"r", "rw"}

    @property
    def writable(self) -> bool:
        return self.access in {"w", "rw"}

    @property
    def value_mask(self) -> int:
        return (1 << (self.bit_width or self.width * 8)) - 1


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    host: str
    rbcp_port: int
    tcp_port: int
    timeout_s: float
    retries: int
    spaces: tuple[AddressSpace, ...]
    registers: dict[str, RegisterDefinition]

    def register(self, name: str) -> RegisterDefinition:
        try:
            return self.registers[name]
        except KeyError as exc:
            raise RegisterLookupError(f"unknown register: {name}") from exc

    def space_for(self, address: int, length: int) -> AddressSpace:
        for space in self.spaces:
            if space.contains(address, length):
                return space
        raise AddressRangeError(
            f"RBCP access 0x{address:08X}..0x{address + length - 1:08X} "
            "does not fit in an allowed address space"
        )

    def validate_access(self, address: int, length: int, *, write: bool) -> None:
        if not 1 <= length <= 0xFF:
            raise AddressRangeError("RBCP access length must be in the range 1..255")
        space = self.space_for(address, length)
        if write and not space.writable:
            raise AddressRangeError(f"address space '{space.name}' is read-only")


def _required_int(table: dict[str, Any], key: str) -> int:
    value = table.get(key)
    if not isinstance(value, int):
        raise RbcpProtocolError(f"'{key}' must be an integer")
    return value


def _parse_space(name: str, table: dict[str, Any]) -> AddressSpace:
    start = _required_int(table, "start")
    end = _required_int(table, "end")
    writable = table.get("writable", False)
    if not isinstance(writable, bool):
        raise RbcpProtocolError(f"spaces.{name}.writable must be a boolean")
    if not 0 <= start <= end <= 0xFFFFFFFF:
        raise RbcpProtocolError(f"spaces.{name} has an invalid address range")
    return AddressSpace(name=name, start=start, end=end, writable=writable)


def _parse_register(name: str, table: dict[str, Any]) -> RegisterDefinition:
    address = _required_int(table, "address")
    width = _required_int(table, "width")
    access = table.get("access", "r")
    description = table.get("description", "")
    group = table.get("group", "")
    unit = table.get("unit", "")
    momentary = table.get("momentary", False)
    bit_width = table.get("bit_width")

    if not 0 <= address <= 0xFFFFFFFF:
        raise RbcpProtocolError(f"register '{name}' has an invalid address")
    if not 1 <= width <= 0xFF:
        raise RbcpProtocolError(f"register '{name}' width must be in the range 1..255")
    if access not in {"r", "w", "rw"}:
        raise RbcpProtocolError(f"register '{name}' access must be r, w, or rw")
    if not all(isinstance(value, str) for value in (description, group, unit)):
        raise RbcpProtocolError(f"register '{name}' text fields must be strings")
    if not isinstance(momentary, bool):
        raise RbcpProtocolError(f"register '{name}' momentary must be a boolean")
    if bit_width is not None:
        if not isinstance(bit_width, int) or not 1 <= bit_width <= width * 8:
            raise RbcpProtocolError(
                f"register '{name}' bit_width must fit inside the register"
            )

    return RegisterDefinition(
        name=name,
        address=address,
        width=width,
        access=access,
        description=description,
        bit_width=bit_width,
        group=group,
        unit=unit,
        momentary=momentary,
    )


def load_profile(path: str | Path) -> DeviceProfile:
    config_path = Path(path)
    with config_path.open("rb") as stream:
        config = tomllib.load(stream)

    device = config.get("device")
    spaces_table = config.get("spaces")
    registers_table = config.get("registers")
    if not isinstance(device, dict):
        raise RbcpProtocolError("configuration is missing [device]")
    if not isinstance(spaces_table, dict) or not spaces_table:
        raise RbcpProtocolError("configuration is missing [spaces]")
    if not isinstance(registers_table, dict) or not registers_table:
        raise RbcpProtocolError("configuration is missing [registers]")

    host = device.get("host")
    if not isinstance(host, str) or not host:
        raise RbcpProtocolError("device.host must be a non-empty string")

    rbcp_port = _required_int(device, "rbcp_port")
    tcp_port = _required_int(device, "tcp_port")
    retries = _required_int(device, "retries")
    timeout_s = device.get("timeout_s")
    if not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
        raise RbcpProtocolError("device.timeout_s must be a positive number")
    if not 1 <= rbcp_port <= 65535 or not 1 <= tcp_port <= 65535:
        raise RbcpProtocolError("RBCP and TCP ports must be in the range 1..65535")
    if not 0 <= retries <= 10:
        raise RbcpProtocolError("device.retries must be in the range 0..10")

    spaces = tuple(
        _parse_space(name, table)
        for name, table in spaces_table.items()
        if isinstance(table, dict)
    )
    registers = {
        name: _parse_register(name, table)
        for name, table in registers_table.items()
        if isinstance(table, dict)
    }
    if len(spaces) != len(spaces_table) or len(registers) != len(registers_table):
        raise RbcpProtocolError("space and register entries must be TOML tables")

    profile = DeviceProfile(
        host=host,
        rbcp_port=rbcp_port,
        tcp_port=tcp_port,
        timeout_s=float(timeout_s),
        retries=retries,
        spaces=spaces,
        registers=registers,
    )

    for register in registers.values():
        try:
            profile.space_for(register.address, register.width)
        except AddressRangeError as exc:
            raise RbcpProtocolError(
                f"register '{register.name}' lies outside all address spaces"
            ) from exc

    return profile

