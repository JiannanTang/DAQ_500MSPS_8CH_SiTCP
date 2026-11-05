"""Connection parameter and state widget."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sitcp_host.core.registers import DeviceProfile
from sitcp_host.gui.i18n import tx
from sitcp_host.gui.widgets.controls import NoWheelDoubleSpinBox, NoWheelSpinBox


class ConnectionBar(QFrame):
    connect_requested = Signal(str, int, float, int)
    disconnect_requested = Signal()

    def __init__(self, profile: DeviceProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(14)

        labels = QVBoxLayout()
        labels.setSpacing(2)
        self.endpoint_label = QLabel("设备连接")
        self.endpoint_label.setObjectName("SectionTitle")
        self.state_label = QLabel("● 未连接")
        self.state_label.setObjectName("StateOffline")
        labels.addWidget(self.endpoint_label)
        labels.addWidget(self.state_label)
        layout.addLayout(labels)
        layout.addSpacing(20)

        self.host_edit = QLineEdit(profile.host)
        self.host_edit.setPlaceholderText("192.168.10.16")
        self.host_edit.setMinimumWidth(155)
        layout.addWidget(QLabel("IP"))
        layout.addWidget(self.host_edit)

        self.port_spin = NoWheelSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(profile.rbcp_port)
        self.port_spin.setMaximumWidth(95)
        layout.addWidget(QLabel("RBCP"))
        layout.addWidget(self.port_spin)

        self.timeout_spin = NoWheelDoubleSpinBox()
        self.timeout_spin.setRange(0.1, 10.0)
        self.timeout_spin.setSingleStep(0.1)
        self.timeout_spin.setDecimals(1)
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setValue(profile.timeout_s)
        self.timeout_spin.setMaximumWidth(95)
        layout.addWidget(QLabel("超时"))
        layout.addWidget(self.timeout_spin)

        self.retry_spin = NoWheelSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(profile.retries)
        self.retry_spin.setMaximumWidth(65)
        layout.addWidget(QLabel("重试"))
        layout.addWidget(self.retry_spin)

        layout.addStretch(1)
        self.connect_button = QPushButton("连接")
        self.connect_button.setObjectName("Primary")
        self.connect_button.setMinimumWidth(108)
        self.connect_button.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self.connect_button)

        self._connected = False
        self._busy = False

    def _on_connect_clicked(self) -> None:
        if self._connected:
            self.disconnect_requested.emit()
            return
        host = self.host_edit.text().strip()
        if not host:
            self.set_offline("请输入设备 IP")
            return
        self.connect_requested.emit(
            host,
            self.port_spin.value(),
            self.timeout_spin.value(),
            self.retry_spin.value(),
        )

    def set_connecting(self) -> None:
        self._busy = True
        self._connected = False
        self.state_label.setText(tx("● 正在连接"))
        self.state_label.setObjectName("StateBusy")
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)
        self.connect_button.setText(tx("连接中..."))
        self.connect_button.setEnabled(False)
        self._set_fields_enabled(False)

    def set_connected(self, host: str, port: int) -> None:
        self._busy = False
        self._connected = True
        self.endpoint_label.setText(f"{host}:{port}")
        self.state_label.setText(tx("● 已连接"))
        self.state_label.setObjectName("StateOnline")
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)
        self.connect_button.setText(tx("断开"))
        self.connect_button.setObjectName("Danger")
        self.connect_button.style().unpolish(self.connect_button)
        self.connect_button.style().polish(self.connect_button)
        self.connect_button.setEnabled(True)
        self._set_fields_enabled(False)

    def set_offline(self, message: str = "未连接") -> None:
        self._busy = False
        self._connected = False
        self.endpoint_label.setText(tx("设备连接"))
        self.state_label.setText(f"● {tx(message)}")
        self.state_label.setObjectName("StateOffline")
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)
        self.connect_button.setText(tx("连接"))
        self.connect_button.setObjectName("Primary")
        self.connect_button.style().unpolish(self.connect_button)
        self.connect_button.style().polish(self.connect_button)
        self.connect_button.setEnabled(True)
        self._set_fields_enabled(True)

    def _set_fields_enabled(self, enabled: bool) -> None:
        for widget in (
            self.host_edit,
            self.port_spin,
            self.timeout_spin,
            self.retry_spin,
        ):
            widget.setEnabled(enabled)

