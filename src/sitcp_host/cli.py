"""Command-line probe for bringing up SiTCP RBCP communication."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sitcp_host.config import default_config_path
from sitcp_host.core.device import RbcpDevice
from sitcp_host.core.registers import DeviceProfile, load_profile
from sitcp_host.errors import RegisterError, SitcpError
from sitcp_host.transport.rbcp_udp import RbcpUdpClient

SMOKE_SCRATCH_ADDRESS = 0x007F


def _parse_number(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise ValueError(
            f"invalid number '{value}'; use decimal or a 0x-prefixed value"
        ) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read and write SiTCP registers using RBCP over UDP"
    )
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--host", help="override the configured device IPv4 address")
    parser.add_argument("--port", type=int, help="override the configured RBCP port")
    parser.add_argument("--timeout", type=float, help="ACK timeout in seconds")
    parser.add_argument("--retries", type=int, help="number of ACK timeout retries")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="list the configured register catalog")

    read_parser = subparsers.add_parser("read", help="read a named or raw register")
    read_parser.add_argument("selector", help="register name or 32-bit address")
    read_parser.add_argument(
        "--length",
        type=int,
        default=1,
        help="byte length for a raw address (default: 1)",
    )

    write_parser = subparsers.add_parser("write", help="write a named register")
    write_parser.add_argument("name")
    write_parser.add_argument("value", type=_parse_number)
    write_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm this explicit register write",
    )

    pulse_parser = subparsers.add_parser(
        "pulse",
        help="write a momentary control register and then return it to zero",
    )
    pulse_parser.add_argument("name")
    pulse_parser.add_argument("--value", type=_parse_number, default=1)
    pulse_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm this momentary-control operation",
    )

    subparsers.add_parser(
        "status",
        help="read temperature and JESD204B state registers",
    )

    smoke_parser = subparsers.add_parser(
        "smoke",
        help="read status and verify one restorable scratch-register write",
    )
    smoke_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm the temporary scratch-register write",
    )
    return parser


def _make_client(args: argparse.Namespace, profile: DeviceProfile) -> RbcpUdpClient:
    return RbcpUdpClient(
        args.host or profile.host,
        port=profile.rbcp_port if args.port is None else args.port,
        timeout_s=profile.timeout_s if args.timeout is None else args.timeout,
        retries=profile.retries if args.retries is None else args.retries,
    )


def _list_registers(profile: DeviceProfile) -> None:
    for space in profile.spaces:
        mode = "read/write" if space.writable else "read-only"
        print(
            f"[{space.name}] 0x{space.start:08X}..0x{space.end:08X} ({mode})"
        )
    print()
    for register in profile.registers.values():
        marker = " pulse" if register.momentary else ""
        print(
            f"{register.name:28s} 0x{register.address:08X} "
            f"{register.width:2d} byte(s) {register.access:2s}{marker} "
            f"{register.description}"
        )


def _read_selector(
    device: RbcpDevice,
    profile: DeviceProfile,
    selector: str,
    length: int,
) -> None:
    if selector in profile.registers:
        value = device.read_register(selector)
        raw = device.read_register_bytes(selector)
        register = profile.register(selector)
        print(
            f"{selector} @ 0x{register.address:08X} = {value} "
            f"(0x{value:0{register.width * 2}X}, raw={raw.hex(' ')})"
        )
        return

    address = _parse_number(selector)
    raw = device.read_bytes(address, length)
    value = int.from_bytes(raw, "little")
    print(
        f"0x{address:08X} ({length} bytes) = {value} "
        f"(0x{value:0{length * 2}X}, raw={raw.hex(' ')})"
    )


def _run_smoke(device: RbcpDevice, profile: DeviceProfile) -> None:
    for name in ("temperature", "jesd_sync_state", "jesd_reset_state"):
        value = device.read_register(name)
        register = profile.register(name)
        print(f"{name:20s} = {value} (0x{value:0{register.width * 2}X})")

    original = device.read_bytes(SMOKE_SCRATCH_ADDRESS, 1)
    test_value = original[0] ^ 0xA5
    changed = bytes((test_value,))
    print(
        f"scratch 0x{SMOKE_SCRATCH_ADDRESS:08X}: original=0x{original[0]:02X}, "
        f"test=0x{test_value:02X}"
    )

    try:
        device.write_bytes(SMOKE_SCRATCH_ADDRESS, changed)
        observed = device.read_bytes(SMOKE_SCRATCH_ADDRESS, 1)
        if observed != changed:
            raise RegisterError(
                f"scratch write failed: wrote {changed.hex()}, "
                f"read {observed.hex()}"
            )
        print("scratch write/readback: OK")
    finally:
        device.write_bytes(SMOKE_SCRATCH_ADDRESS, original)
        restored = device.read_bytes(SMOKE_SCRATCH_ADDRESS, 1)
        if restored != original:
            raise RegisterError(
                f"scratch restore failed: expected {original.hex()}, "
                f"read {restored.hex()}"
            )
        print(f"scratch restore: OK (0x{restored[0]:02X})")


def _run(args: argparse.Namespace, profile: DeviceProfile) -> int:
    if args.command == "list":
        _list_registers(profile)
        return 0

    if args.command in {"write", "pulse", "smoke"} and not args.yes:
        raise SitcpError("register write requires --yes")

    with _make_client(args, profile) as client:
        device = RbcpDevice(client, profile)

        if args.command == "read":
            _read_selector(device, profile, args.selector, args.length)
        elif args.command == "write":
            register = profile.register(args.name)
            if register.momentary:
                raise SitcpError(
                    f"'{args.name}' is a momentary control; use the pulse command"
                )
            device.write_register(args.name, args.value, verify=True)
            print(f"wrote {args.name}=0x{args.value:X} and verified readback")
        elif args.command == "pulse":
            device.pulse_register(args.name, args.value)
            print(f"pulsed {args.name} with 0x{args.value:X}, then restored 0")
        elif args.command == "status":
            for name in (
                "temperature",
                "jesd_sync_state",
                "jesd_reset_state",
            ):
                value = device.read_register(name)
                register = profile.register(name)
                print(f"{name:20s} = {value} (0x{value:0{register.width * 2}X})")
        elif args.command == "smoke":
            _run_smoke(device, profile)
        else:
            raise AssertionError(f"unhandled command: {args.command}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        profile = load_profile(args.config)
        return _run(args, profile)
    except (OSError, SitcpError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

