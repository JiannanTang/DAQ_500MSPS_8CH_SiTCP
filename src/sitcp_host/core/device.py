"""High-level operations over the device register catalog."""

from __future__ import annotations

from typing import Protocol

from sitcp_host.core.rbcp import RbcpReply
from sitcp_host.core.registers import DeviceProfile, RegisterDefinition
from sitcp_host.errors import RegisterError


class RbcpClient(Protocol):
    def read(self, address: int, length: int = 1) -> RbcpReply: ...

    def write(self, address: int, data: bytes) -> RbcpReply: ...


class RbcpDevice:
    """Validate register access and convert values to and from RBCP bytes."""

    def __init__(self, client: RbcpClient, profile: DeviceProfile) -> None:
        self.client = client
        self.profile = profile

    def read_register_bytes(self, name: str) -> bytes:
        register = self.profile.register(name)
        if not register.readable:
            raise RegisterError(f"register '{name}' is not readable")
        self.profile.validate_access(register.address, register.width, write=False)
        data = bytes(self.client.read(register.address, register.width).data)
        if len(data) != register.width:
            raise RegisterError(
                f"register '{name}' expected {register.width} bytes, "
                f"received {len(data)}"
            )
        return data

    def read_register(self, name: str) -> int:
        register = self.profile.register(name)
        data = self.read_register_bytes(name)
        return int.from_bytes(data, "little") & register.value_mask

    def write_register(
        self,
        name: str,
        value: int,
        *,
        verify: bool = False,
    ) -> None:
        register = self._writable_register(name)
        self._check_value(register, value)
        data = value.to_bytes(register.width, "little")
        self.profile.validate_access(register.address, register.width, write=True)
        self.client.write(register.address, data)

        if verify:
            if not register.readable:
                raise RegisterError(f"register '{name}' cannot be verified by readback")
            actual = self.read_register(name)
            if actual != value:
                raise RegisterError(
                    f"register '{name}' readback mismatch: "
                    f"wrote {value}, read {actual}"
                )

    def pulse_register(self, name: str, value: int = 1) -> None:
        register = self._writable_register(name)
        if not register.momentary:
            raise RegisterError(
                f"register '{name}' is not marked as a momentary control"
            )
        self._check_value(register, value)
        self.write_register(name, value)
        self.write_register(name, 0)

    def read_bytes(self, address: int, length: int = 1) -> bytes:
        self.profile.validate_access(address, length, write=False)
        data = bytes(self.client.read(address, length).data)
        if len(data) != length:
            raise RegisterError(
                f"requested {length} bytes from 0x{address:08X}, received {len(data)}"
            )
        return data

    def write_bytes(self, address: int, data: bytes) -> None:
        payload = bytes(data)
        if not payload:
            raise RegisterError("write data must not be empty")
        self.profile.validate_access(address, len(payload), write=True)
        self.client.write(address, payload)

    def _writable_register(self, name: str) -> RegisterDefinition:
        register = self.profile.register(name)
        if not register.writable:
            raise RegisterError(f"register '{name}' is not writable")
        return register

    @staticmethod
    def _check_value(register: RegisterDefinition, value: int) -> None:
        if not 0 <= value <= register.value_mask:
            raise RegisterError(
                f"value {value} does not fit in register '{register.name}' "
                f"({register.bit_width or register.width * 8} bits)"
            )

