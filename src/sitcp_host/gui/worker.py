"""Qt worker that keeps all blocking RBCP network operations off the UI thread."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal, Slot

from sitcp_host.core.device import RbcpDevice
from sitcp_host.core.models import StatusSnapshot
from sitcp_host.core.registers import DeviceProfile
from sitcp_host.errors import SitcpError
from sitcp_host.gui.i18n import tx
from sitcp_host.transport.rbcp_udp import RbcpUdpClient


class RbcpWorker(QObject):
    connected = Signal(str, int)
    disconnected = Signal()
    connection_failed = Signal(str)
    operation_failed = Signal(str, str)
    status_ready = Signal(object)
    register_value_ready = Signal(str, int, bytes)
    write_completed = Signal(str, int)
    pulse_completed = Signal(str)
    raw_value_ready = Signal(int, bytes)
    cfg_step_completed = Signal(int, int, str)
    cfg_sequence_finished = Signal()
    cfg_sequence_failed = Signal(str, str)
    software_trigger_completed = Signal()
    software_trigger_failed = Signal(str)

    def __init__(self, profile: DeviceProfile) -> None:
        super().__init__()
        self._profile = profile
        self._client: RbcpUdpClient | None = None
        self._device: RbcpDevice | None = None

    @Slot(str, int, float, int)
    def connect_device(
        self,
        host: str,
        port: int,
        timeout_s: float,
        retries: int,
    ) -> None:
        self.shutdown()
        client: RbcpUdpClient | None = None
        try:
            client = RbcpUdpClient(
                host,
                port=port,
                timeout_s=timeout_s,
                retries=retries,
            )
            device = RbcpDevice(client, self._profile)
            device.read_register("jesd_sync_state")
        except (OSError, SitcpError, ValueError) as exc:
            if client is not None:
                client.close()
            self.connection_failed.emit(str(exc))
            return

        self._client = client
        self._device = device
        self.connected.emit(host, port)

    @Slot()
    def disconnect_device(self) -> None:
        self.shutdown()
        self.disconnected.emit()

    @Slot()
    def read_status(self) -> None:
        try:
            device = self._require_device()
            raw = device.read_bytes(0x0108, 4)
            if len(raw) != 4:
                raise SitcpError(
                    f"status block expected 4 bytes, received {len(raw)}"
                )
            snapshot = StatusSnapshot(
                temperature_raw=int.from_bytes(raw[0:2], "little"),
                jesd_sync_state=raw[2],
                jesd_reset_state=raw[3],
            )
        except (OSError, SitcpError, ValueError) as exc:
            self.operation_failed.emit("status", str(exc))
            return
        self.status_ready.emit(snapshot)

    @Slot(str)
    def read_register(self, name: str) -> None:
        try:
            device = self._require_device()
            raw = device.read_register_bytes(name)
            register = self._profile.register(name)
            value = int.from_bytes(raw, "little") & register.value_mask
        except (OSError, SitcpError, ValueError) as exc:
            self.operation_failed.emit(f"read:{name}", str(exc))
            return
        self.register_value_ready.emit(name, value, raw)

    @Slot(str, int)
    def write_register(self, name: str, value: int) -> None:
        try:
            device = self._require_device()
            device.write_register(name, value, verify=False)
        except (OSError, SitcpError, ValueError) as exc:
            self.operation_failed.emit(f"write:{name}", str(exc))
            return
        self.write_completed.emit(name, value)

    @Slot(str)
    def pulse_register(self, name: str) -> None:
        try:
            device = self._require_device()
            device.pulse_register(name, 1)
        except (OSError, SitcpError, ValueError) as exc:
            self.operation_failed.emit(f"pulse:{name}", str(exc))
            return
        self.pulse_completed.emit(name)

    @Slot(int, int)
    def read_raw(self, address: int, length: int) -> None:
        try:
            device = self._require_device()
            data = device.read_bytes(address, length)
        except (OSError, SitcpError, ValueError) as exc:
            self.operation_failed.emit("raw-read", str(exc))
            return
        self.raw_value_ready.emit(address, data)

    @Slot()
    def run_cfg_sequence(self) -> None:
        steps = (
            ("system_reset", "系统复位"),
            ("ad9528_reset", "AD9528 复位"),
            ("ad9528_configure", "配置 AD9528"),
            ("ad9694_configure", "配置 AD9694"),
            ("jesd204b_configure", "开始 JESD204B 同步"),
            ("jesd_status_read", "JESD 状态读取"),
        )
        current_label = "CFG"
        try:
            device = self._require_device()
            for index, (name, label) in enumerate(steps, start=1):
                current_label = label
                device.pulse_register(name, 1)
                self.cfg_step_completed.emit(index, len(steps), tx(label))
                if index < len(steps):
                    time.sleep(0.01)
        except (OSError, SitcpError, ValueError) as exc:
            self.cfg_sequence_failed.emit(tx(current_label), str(exc))
            return
        self.cfg_sequence_finished.emit()

    @Slot()
    def pulse_software_trigger(self) -> None:
        try:
            device = self._require_device()
            device.pulse_register("software_trigger", 1)
        except (OSError, SitcpError, ValueError) as exc:
            self.software_trigger_failed.emit(str(exc))
            return
        self.software_trigger_completed.emit()

    @Slot()
    def shutdown(self) -> None:
        if self._client is not None:
            self._client.close()
        self._client = None
        self._device = None

    def _require_device(self) -> RbcpDevice:
        if self._device is None:
            raise SitcpError("device is not connected")
        return self._device

