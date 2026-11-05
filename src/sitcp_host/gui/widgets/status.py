"""Live device status cards and polling controls."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sitcp_host.core.conversions import xadc_temperature_celsius
from sitcp_host.core.models import StatusSnapshot
from sitcp_host.gui.i18n import tx
from sitcp_host.gui.widgets.controls import NoWheelSpinBox


class _MetricCard(QFrame):
    def __init__(
        self,
        title: str,
        detail: str,
        parent: QWidget | None = None,
        *,
        show_health: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(6)

        heading = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("Muted")
        heading.addWidget(title_label)
        heading.addStretch(1)
        self.health_label = QLabel("● --")
        self.health_label.setObjectName("Muted")
        self.health_label.setVisible(show_health)
        heading.addWidget(self.health_label)
        self.value_label = QLabel("--")
        self.value_label.setObjectName("MetricValue")
        self.detail_label = QLabel(detail)
        self.detail_label.setObjectName("MetricDetail")
        layout.addLayout(heading)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)

    def set_value(self, value: str, detail: str) -> None:
        self.value_label.setText(value)
        self.detail_label.setText(detail)

    def set_health(self, normal: bool | None) -> None:
        if normal is None:
            self.health_label.setText("● --")
            self.health_label.setObjectName("Muted")
        elif normal:
            self.health_label.setText(tx("● 正常"))
            self.health_label.setObjectName("StateOnline")
        else:
            self.health_label.setText(tx("● 异常"))
            self.health_label.setObjectName("StateOffline")
        self.health_label.style().unpolish(self.health_label)
        self.health_label.style().polish(self.health_label)


class StatusPanel(QWidget):
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._connected = False
        self._refreshing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("运行状态")
        title.setObjectName("SectionTitle")
        subtitle = QLabel("状态寄存器按原始值显示；尚无固件定义的编码和温度换算系数。")
        subtitle.setObjectName("Muted")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch(1)

        self.auto_refresh = QCheckBox("自动刷新")
        self.auto_refresh.setChecked(True)
        self.auto_refresh.toggled.connect(self._update_timer)
        header.addWidget(self.auto_refresh)

        self.interval_spin = NoWheelSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.setSingleStep(1)
        self.interval_spin.setSuffix(" s")
        self.interval_spin.setValue(5)
        self.interval_spin.valueChanged.connect(self._update_interval)
        header.addWidget(self.interval_spin)

        self.refresh_button = QPushButton("立即刷新")
        self.refresh_button.clicked.connect(self.request_refresh)
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        cards = QGridLayout()
        cards.setHorizontalSpacing(12)
        cards.setVerticalSpacing(12)
        self.temp_card = _MetricCard("芯片温度", "Xilinx XADC 12 bit 码值换算")
        self.sync_card = _MetricCard(
            "JESD204B 同步状态",
            "正常值 0x11",
            show_health=True,
        )
        self.reset_card = _MetricCard(
            "JESD204B 复位状态",
            "正常值 0x10",
            show_health=True,
        )
        cards.addWidget(self.temp_card, 0, 0)
        cards.addWidget(self.sync_card, 0, 1)
        cards.addWidget(self.reset_card, 0, 2)
        for column in range(3):
            cards.setColumnStretch(column, 1)
        root.addLayout(cards)

        info = QFrame()
        info.setObjectName("Card")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(18, 14, 18, 14)
        info_title = QLabel("状态读取说明")
        info_title.setObjectName("SectionTitle")
        info_text = QLabel(
            "每次刷新通过一个 RBCP 请求读取 0x0108-0x010B 共 4 字节："
            "温度占前 2 字节，随后是 JESD 同步状态和复位状态。"
        )
        info_text.setWordWrap(True)
        info_text.setObjectName("Muted")
        self.updated_label = QLabel("尚未读取")
        self.updated_label.setObjectName("MetricDetail")
        info_layout.addWidget(info_title)
        info_layout.addWidget(info_text)
        info_layout.addWidget(self.updated_label)
        root.addWidget(info)
        root.addStretch(1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.request_refresh)

    def request_refresh(self) -> None:
        if self._connected and not self._refreshing:
            self._refreshing = True
            self.refresh_button.setText(tx("刷新中..."))
            self.refresh_button.setEnabled(False)
            self.refresh_requested.emit()

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._refreshing = False
        self.refresh_button.setText(tx("立即刷新"))
        self.refresh_button.setEnabled(connected)
        if connected:
            self._update_timer()
        else:
            self._timer.stop()
            self.updated_label.setText(tx("设备离线"))
            self.sync_card.set_health(None)
            self.reset_card.set_health(None)

    def finish_refresh(self) -> None:
        self._refreshing = False
        self.refresh_button.setText(tx("立即刷新"))
        self.refresh_button.setEnabled(self._connected)

    def update_snapshot(self, snapshot: StatusSnapshot) -> None:
        self.temp_card.set_value(
            f"{xadc_temperature_celsius(snapshot.temperature_raw):.1f} °C",
            f"raw 0x{snapshot.temperature_raw:04X}",
        )
        self.sync_card.set_value(
            f"0x{snapshot.jesd_sync_state:02X}",
            f"decimal {snapshot.jesd_sync_state}",
        )
        self.reset_card.set_value(
            f"0x{snapshot.jesd_reset_state:02X}",
            f"decimal {snapshot.jesd_reset_state}",
        )
        self.sync_card.set_health(snapshot.jesd_sync_state == 0x11)
        self.reset_card.set_health(snapshot.jesd_reset_state == 0x10)
        self.updated_label.setText(
            tx(f"最近更新：{datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
        )
        self.finish_refresh()

    def _update_timer(self) -> None:
        if self._connected and self.auto_refresh.isChecked():
            self._timer.start(self.interval_spin.value() * 1000)
        else:
            self._timer.stop()

    def _update_interval(self) -> None:
        if self._timer.isActive():
            self._timer.start(self.interval_spin.value() * 1000)

