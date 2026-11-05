"""Raw address read panel for protocol debugging."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sitcp_host.gui.i18n import tx
from sitcp_host.gui.widgets.controls import NoWheelSpinBox


class RawAccessPanel(QWidget):
    read_requested = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("原始寄存器读取")
        title.setObjectName("SectionTitle")
        root.addWidget(title)
        note = QLabel(
            "按固件允许的地址空间直接读取字节，用于核对端序和调试协议。"
            "当前页面只允许读，不提供任意地址写入。"
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        root.addWidget(note)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("地址"))
        self.address_edit = QLineEdit("0x0108")
        self.address_edit.setMaximumWidth(170)
        controls.addWidget(self.address_edit)
        controls.addWidget(QLabel("长度"))
        self.length_spin = NoWheelSpinBox()
        self.length_spin.setRange(1, 255)
        self.length_spin.setValue(4)
        self.length_spin.setMaximumWidth(90)
        controls.addWidget(self.length_spin)
        self.read_button = QPushButton("读取")
        self.read_button.clicked.connect(self._emit_read)
        controls.addWidget(self.read_button)
        controls.addStretch(1)
        root.addLayout(controls)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("读取结果会显示在这里")
        root.addWidget(self.output, 1)
        self.set_connected(False)

    def set_connected(self, connected: bool) -> None:
        self.read_button.setEnabled(connected)

    def _emit_read(self) -> None:
        try:
            address = int(self.address_edit.text().strip(), 0)
        except ValueError:
            self.show_error(
                tx("地址格式无效，请使用十进制或 0x 前缀的十六进制")
            )
            return
        if not 0 <= address <= 0xFFFFFFFF:
            self.show_error(tx("地址必须是 32 位无符号整数"))
            return
        length = self.length_spin.value()
        self.output.appendPlainText(
            f"[{datetime.now().strftime('%H:%M:%S')}] "
            f"READ 0x{address:08X}, {length} byte(s)"
        )
        self.read_requested.emit(address, length)

    def show_result(self, address: int, data: bytes) -> None:
        little = int.from_bytes(data, "little")
        big = int.from_bytes(data, "big")
        self.output.appendPlainText(
            f"  raw   : {data.hex(' ')}\n"
            f"  uintLE: {little} (0x{little:0{len(data) * 2}X})\n"
            f"  uintBE: {big} (0x{big:0{len(data) * 2}X})\n"
            f"  @0x{address:08X}"
        )

    def show_error(self, message: str) -> None:
        self.output.appendPlainText(
            f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {message}"
        )

