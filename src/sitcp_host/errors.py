"""Domain-specific exceptions for SiTCP communication."""


class SitcpError(Exception):
    """Base class for host application errors."""


class RbcpError(SitcpError):
    """Base class for RBCP protocol and transport errors."""


class RbcpProtocolError(RbcpError):
    """The local configuration or a received RBCP packet is invalid."""


class RbcpTimeoutError(RbcpError, TimeoutError):
    """No matching RBCP ACK was received before the deadline."""


class RbcpBusError(RbcpError):
    """SiTCP reported a bus error in an RBCP ACK."""


class RegisterError(SitcpError):
    """A register operation is invalid or unsafe."""


class RegisterLookupError(RegisterError):
    """A named register does not exist in the device profile."""


class AddressRangeError(RegisterError):
    """An RBCP access falls outside an allowed address space."""


class FrameProtocolError(SitcpError):
    """A TCP data frame is malformed or the stream is not frame-aligned."""


class StorageError(SitcpError):
    """Raw acquisition data could not be written safely."""

