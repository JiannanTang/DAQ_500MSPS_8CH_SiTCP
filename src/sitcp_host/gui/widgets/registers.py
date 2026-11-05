"""Purpose-built trigger controls over the generic FPGA register catalog."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from sitcp_host.core.registers import DeviceProfile
from sitcp_host.gui.i18n import language, tx
from sitcp_host.gui.widgets.controls import NoWheelSpinBox

_GROUP_LABELS = {
    "trigger threshold": "触发阈值",
    "trigger length": "触发长度",
    "trigger offset": "触发偏移",
    "trigger control": "其他触发参数",
    "clock and ADC control": "时钟与 ADC",
    "JESD204B": "JESD204B",
}

_REGISTER_LABELS = {
    "trigger_channel": "触发通道",
    "external_trigger_delay": "外部触发延迟",
    "trigger_mode": "触发模式",
    "system_reset": "系统复位",
    "ad9528_reset": "AD9528 复位",
    "ad9528_configure": "配置 AD9528",
    "ad9694_configure": "配置 AD9694",
    "ad9694_powerdown": "AD9694 Power Down",
    "jesd204b_configure": "开始 JESD204B 同步",
    "jesd_status_read": "JESD 状态读取",
    "software_trigger": "软件触发",
    "channel_trigger_edge": "通道触发边沿",
    "trigger_spread_cycles": "符合触发展宽",
    "coincidence_channel_a": "符合通道 A",
    "coincidence_channel_b": "符合通道 B",
    "trigger_buffer_clear": "触发缓存清空",
}

_MODE_LABELS = (
    (0, "独立模式"),
    (1, "单通道广播"),
    (2, "双通道符合"),
    (3, "外部触发"),
    (4, "软件触发"),
)


def _channel_register(prefix: str, channel: int) -> str:
    return f"{prefix}_ch{channel}"


class RegisterPanel(QWidget):
    read_all_requested = Signal(list)
    read_requested = Signal(str)
    write_requested = Signal(str, int)
    cfg_sequence_requested = Signal()

    def __init__(self, profile: DeviceProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._profile = profile
        self._connected = False
        self._values: dict[str, int] = {}
        self._current_labels: dict[str, QLabel] = {}
        self._spins: dict[str, NoWheelSpinBox] = {}
        self._channel_state: dict[int, QLabel] = {}
        self._channel_by_register = {
            _channel_register(prefix, channel): channel
            for prefix in ("threshold", "trigger_length", "trigger_offset")
            for channel in range(8)
        }
        self._mode_buttons: dict[int, QPushButton] = {}
        self._momentary_buttons: dict[str, QPushButton] = {}
        self._toggle_buttons: dict[str, QPushButton] = {}
        self._bitmask_checks: dict[str, list[QCheckBox]] = {}
        self._cfg_running = False
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._enabled_controls: list[QWidget] = []

        self._registers = sorted(
            (
                register
                for register in profile.registers.values()
                if profile.space_for(register.address, register.width).name == "config"
            ),
            key=lambda register: (register.group, register.address),
        )
        channel_names = {
            _channel_register(prefix, channel)
            for prefix in ("threshold", "trigger_length", "trigger_offset")
            for channel in range(8)
        }
        handled = channel_names | {
            "trigger_mode",
            "software_trigger",
            "trigger_buffer_clear",
        }
        other_names = [
            register.name
            for register in self._registers
            if register.name not in handled
        ]

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("触发与设备配置")
        title.setObjectName("SectionTitle")
        subtitle = QLabel(
            "统一管理触发通道、触发模式、时钟、ADC 和 JESD 参数。"
        )
        subtitle.setObjectName("Muted")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch(1)
        self.cfg_progress_label = QLabel("CFG：待执行")
        self.cfg_progress_label.setObjectName("Muted")
        header.addWidget(self.cfg_progress_label)
        self.cfg_button = QPushButton("一键 CFG")
        self.cfg_button.setObjectName("Primary")
        self.cfg_button.clicked.connect(self._request_cfg_sequence)
        header.addWidget(self.cfg_button)
        self.read_all_button = QPushButton("读取全部寄存器")
        self.read_all_button.clicked.connect(self._read_all)
        header.addWidget(self.read_all_button)
        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(10)

        top_controls = QWidget()
        top_controls_layout = QHBoxLayout(top_controls)
        top_controls_layout.setContentsMargins(0, 0, 0, 0)
        top_controls_layout.setSpacing(10)
        clock_names = [
            name
            for name in other_names
            if profile.register(name).group == "clock and ADC control"
        ]
        jesd_names = [
            name
            for name in other_names
            if profile.register(name).group == "JESD204B"
        ]
        if clock_names:
            self.clock_card = self._build_other_card(
                "clock and ADC control",
                clock_names,
            )
            top_controls_layout.addWidget(self.clock_card, 1)
        if jesd_names:
            self.jesd_card = self._build_other_card("JESD204B", jesd_names)
            top_controls_layout.addWidget(self.jesd_card, 1)
        content_layout.addWidget(top_controls)

        content_layout.addWidget(self._build_mode_card())
        trigger_names = [
            name
            for name in other_names
            if profile.register(name).group == "trigger control"
        ]
        if trigger_names:
            content_layout.addWidget(
                self._build_other_card("trigger control", trigger_names)
            )
        content_layout.addWidget(self._build_all_channels_card())
        content_layout.addWidget(self._build_channel_grid())
        content_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self._enabled_controls.append(self.read_all_button)
        self._enabled_controls.append(self.cfg_button)
        self.set_connected(False)

    def _build_mode_card(self) -> QFrame:
        card, layout = self._card("触发模式")
        note = QLabel("五种模式互斥，选择后立即写入 trigger_mode 寄存器。")
        note.setObjectName("Muted")
        layout.addWidget(note)

        buttons = QHBoxLayout()
        for value, label in _MODE_LABELS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setMinimumHeight(36)
            self._mode_group.addButton(button, value)
            self._mode_buttons[value] = button
            buttons.addWidget(button)
            self._enabled_controls.append(button)
        self._mode_group.idClicked.connect(self._on_mode_clicked)
        layout.addLayout(buttons)
        self._current_labels["trigger_mode"] = QLabel("当前模式：--")
        self._current_labels["trigger_mode"].setObjectName("Muted")
        layout.addWidget(self._current_labels["trigger_mode"])
        return card

    def _build_all_channels_card(self) -> QFrame:
        card, layout = self._card("所有通道统一设置")
        note = QLabel("把同一组阈值、长度和偏移写入 CH0-CH7。")
        note.setObjectName("Muted")
        layout.addWidget(note)

        row = QHBoxLayout()
        self.all_threshold = self._make_spin(0x3FFF, decimal=True)
        self.all_length = self._make_spin(0xFF, decimal=True)
        self.all_offset = self._make_spin(0xFF, decimal=True)
        row.addWidget(QLabel("阈值 (0-16383)"))
        row.addWidget(self.all_threshold)
        row.addSpacing(12)
        row.addWidget(QLabel("长度 (0-255)"))
        row.addWidget(self.all_length)
        row.addSpacing(12)
        row.addWidget(QLabel("偏移 (0-255)"))
        row.addWidget(self.all_offset)
        apply_button = QPushButton("应用到所有通道")
        apply_button.setObjectName("Primary")
        apply_button.clicked.connect(self._apply_all_channels)
        row.addWidget(apply_button)
        self._enabled_controls.append(apply_button)

        layout.addLayout(row)
        return card

    def _build_channel_grid(self) -> QWidget:
        widget = QWidget()
        grid = QGridLayout(widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(9)
        grid.setVerticalSpacing(9)
        for channel in range(8):
            grid.addWidget(self._build_channel_card(channel), channel // 2, channel % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return widget

    def _build_channel_card(self, channel: int) -> QFrame:
        card, layout = self._card(f"CH{channel} 触发参数")
        state = QLabel("当前值未读取")
        state.setObjectName("MetricDetail")
        self._channel_state[channel] = state
        layout.addWidget(state)

        fields = QGridLayout()
        for row, (title, prefix, maximum) in enumerate(
            (
                ("阈值 (0-16383)", "threshold", 0x3FFF),
                ("长度 (0-255)", "trigger_length", 0xFF),
                ("偏移 (0-255)", "trigger_offset", 0xFF),
            )
        ):
            name = _channel_register(prefix, channel)
            spin = self._make_spin(maximum, decimal=True)
            self._spins[name] = spin
            fields.addWidget(QLabel(title), row, 0)
            fields.addWidget(spin, row, 1)
            self._enabled_controls.append(spin)
        layout.addLayout(fields)

        actions = QHBoxLayout()
        read_button = QPushButton("读取本通道")
        read_button.clicked.connect(lambda _checked=False, ch=channel: self._read_channel(ch))
        write_button = QPushButton("写入本通道")
        write_button.setObjectName("Primary")
        write_button.clicked.connect(
            lambda _checked=False, ch=channel: self._apply_channel(ch)
        )
        actions.addWidget(read_button)
        actions.addWidget(write_button)
        layout.addLayout(actions)
        self._enabled_controls.extend((read_button, write_button))
        return card

    def _build_other_card(self, group: str, names: list[str]) -> QFrame:
        card, layout = self._card(_GROUP_LABELS.get(group, group))
        momentary_names = [
            name for name in names if self._profile.register(name).momentary
        ]
        if momentary_names:
            pulse_grid = QGridLayout()
            pulse_grid.setHorizontalSpacing(8)
            pulse_grid.setVerticalSpacing(8)
            for index, name in enumerate(momentary_names):
                register = self._profile.register(name)
                button = QPushButton(_REGISTER_LABELS.get(name, name))
                button.setMinimumHeight(40)
                button.setObjectName(
                    "Danger"
                    if name in {
                        "system_reset",
                        "ad9528_reset",
                        "trigger_buffer_clear",
                    }
                    else "Primary"
                )
                button.setToolTip(
                    f"{register.description}"
                    f"{tx('；鼠标按下写入 1，抬起写入 0。')}"
                )
                button.pressed.connect(
                    lambda name=name: self.write_requested.emit(name, 1)
                )
                button.released.connect(
                    lambda name=name: self.write_requested.emit(name, 0)
                )
                self._momentary_buttons[name] = button
                self._enabled_controls.append(button)
                pulse_grid.addWidget(button, index // 2, index % 2)
            pulse_grid.setColumnStretch(0, 1)
            pulse_grid.setColumnStretch(1, 1)
            layout.addLayout(pulse_grid)

        for name in names:
            if self._profile.register(name).momentary:
                continue
            register = self._profile.register(name)
            if name in {"trigger_channel", "channel_trigger_edge"}:
                self._build_bitmask_row(layout, name)
                continue
            if name == "ad9694_powerdown":
                button = QPushButton("AD9694：正常工作")
                button.setCheckable(True)
                button.setMinimumHeight(38)
                button.setToolTip(
                    "两态开关：正常写入 0x0，Power Down 写入 0x3。"
                )
                button.clicked.connect(self._on_powerdown_clicked)
                self._toggle_buttons[name] = button
                self._enabled_controls.append(button)
                layout.addWidget(button)
                continue

            row = QHBoxLayout()
            maximum = register.value_mask
            label = QLabel(
                f"{_REGISTER_LABELS.get(name, name)} "
                f"(0x0-0x{maximum:X})"
            )
            label.setToolTip(register.description)
            label.setMinimumWidth(170)
            row.addWidget(label)

            current = QLabel("--")
            current.setObjectName("MetricDetail")
            current.setMinimumWidth(70)
            self._current_labels[name] = current
            row.addWidget(current)
            row.addStretch(1)

            spin = self._make_spin(maximum, decimal=False)
            spin.setToolTip(
                f"{register.description}{tx('；范围 0x0-0x')}{maximum:X}"
            )
            self._spins[name] = spin
            row.addWidget(spin)
            read_button = QPushButton("读取")
            read_button.clicked.connect(
                lambda _checked=False, name=name: self.read_requested.emit(name)
            )
            write_button = QPushButton("写入")
            write_button.clicked.connect(
                lambda _checked=False, name=name: self._write_value(name)
            )
            row.addWidget(read_button)
            row.addWidget(write_button)
            self._enabled_controls.extend((spin, read_button, write_button))
            layout.addLayout(row)

        return card

    def _build_bitmask_row(self, layout: QVBoxLayout, name: str) -> None:
        row = QHBoxLayout()
        label_text = (
            "触发通道边沿（勾选=上升沿）"
            if name == "channel_trigger_edge"
            else "触发通道（可多选）"
        )
        label = QLabel(label_text)
        label.setMinimumWidth(210)
        row.addWidget(label)

        checks: list[QCheckBox] = []
        for channel in range(8):
            checkbox = QCheckBox(f"CH{channel}")
            checks.append(checkbox)
            row.addWidget(checkbox)
            self._enabled_controls.append(checkbox)
        self._bitmask_checks[name] = checks

        row.addStretch(1)
        read_button = QPushButton("读取")
        read_button.clicked.connect(
            lambda _checked=False, name=name: self.read_requested.emit(name)
        )
        write_button = QPushButton("写入")
        write_button.clicked.connect(
            lambda _checked=False, name=name: self._write_value(name)
        )
        row.addWidget(read_button)
        row.addWidget(write_button)
        self._enabled_controls.extend((read_button, write_button))
        layout.addLayout(row)

    def _card(self, title_text: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        title = QLabel(title_text)
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        return frame, layout

    @staticmethod
    def _make_spin(maximum: int, *, decimal: bool) -> NoWheelSpinBox:
        spin = NoWheelSpinBox()
        spin.setRange(0, maximum)
        if not decimal:
            spin.setDisplayIntegerBase(16)
            spin.setPrefix("0x")
        spin.setMinimumWidth(105)
        return spin

    def update_value(self, name: str, value: int, raw: bytes) -> None:
        self._values[name] = value
        register = self._profile.register(name)
        formatted = f"0x{value:0{max((register.bit_width or 1) // 4, 1)}X}"

        current = self._current_labels.get(name)
        if current is not None:
            current.setText(tx(f"当前：{formatted}"))
            current.setToolTip(f"decimal={value}, raw={raw.hex(' ')}")

        spin = self._spins.get(name)
        if spin is not None and not spin.hasFocus():
            spin.setValue(value)

        if name in self._bitmask_checks:
            for channel, checkbox in enumerate(self._bitmask_checks[name]):
                checkbox.setChecked(bool(value & (1 << channel)))
        elif name == "trigger_mode":
            button = self._mode_buttons.get(value)
            if button is not None:
                button.setChecked(True)
        elif name == "ad9694_powerdown":
            button = self._toggle_buttons.get(name)
            if button is not None:
                button.setChecked(value != 0)
                button.setText(
                    tx("AD9694：Power Down" if value != 0 else "AD9694：正常工作")
                )
        elif (channel := self._channel_by_register.get(name)) is not None:
            self._refresh_channel_state(channel)

    def mark_pending(self, name: str) -> None:
        current = self._current_labels.get(name)
        if current is not None:
            current.setText(tx("读取中..."))
        if (channel := self._channel_by_register.get(name)) is not None:
            self._channel_state[channel].setText(tx("正在读取..."))

    def mark_error(self, name: str) -> None:
        current = self._current_labels.get(name)
        if current is not None:
            current.setText(tx("读取失败"))
        if (channel := self._channel_by_register.get(name)) is not None:
            self._channel_state[channel].setText(tx("读取失败"))

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._refresh_enabled()

    def set_cfg_running(self, running: bool) -> None:
        self._cfg_running = running
        self._refresh_enabled()

    def set_cfg_progress(self, text: str) -> None:
        prefix = "CFG: " if language() == "en" else "CFG："
        self.cfg_progress_label.setText(prefix + tx(text))

    def _refresh_enabled(self) -> None:
        enabled = self._connected and not self._cfg_running
        for control in self._enabled_controls:
            control.setEnabled(enabled)

    def _request_cfg_sequence(self) -> None:
        if self._connected and not self._cfg_running:
            self.cfg_sequence_requested.emit()

    def _on_mode_clicked(self, mode: int) -> None:
        if self._connected:
            self.write_requested.emit("trigger_mode", mode)

    def _write_value(self, name: str) -> None:
        if name in self._bitmask_checks:
            if self._connected:
                value = sum(
                    (1 << channel)
                    for channel, checkbox in enumerate(self._bitmask_checks[name])
                    if checkbox.isChecked()
                )
                self.write_requested.emit(name, value)
            return
        spin = self._spins.get(name)
        if spin is not None and self._connected:
            self.write_requested.emit(name, spin.value())

    def _on_powerdown_clicked(self, checked: bool) -> None:
        button = self._toggle_buttons["ad9694_powerdown"]
        button.setText(
            tx("AD9694：Power Down" if checked else "AD9694：正常工作")
        )
        self.write_requested.emit("ad9694_powerdown", 3 if checked else 0)

    def _apply_channel(self, channel: int) -> None:
        if not self._connected:
            return
        for prefix in ("threshold", "trigger_length", "trigger_offset"):
            name = _channel_register(prefix, channel)
            self.write_requested.emit(name, self._spins[name].value())

    def _apply_all_channels(self) -> None:
        if not self._connected:
            return
        for channel in range(8):
            self._spins[_channel_register("threshold", channel)].setValue(
                self.all_threshold.value()
            )
            self._spins[_channel_register("trigger_length", channel)].setValue(
                self.all_length.value()
            )
            self._spins[_channel_register("trigger_offset", channel)].setValue(
                self.all_offset.value()
            )
            self._apply_channel(channel)

    def _read_channel(self, channel: int) -> None:
        if not self._connected:
            return
        for prefix in ("threshold", "trigger_length", "trigger_offset"):
            name = _channel_register(prefix, channel)
            self.mark_pending(name)
            self.read_requested.emit(name)

    def _read_all(self) -> None:
        if not self._connected:
            return
        names = [register.name for register in self._registers]
        for name in names:
            self.mark_pending(name)
        self.read_all_requested.emit(names)

    def _refresh_channel_state(self, channel: int) -> None:
        values = []
        for prefix in ("threshold", "trigger_length", "trigger_offset"):
            name = _channel_register(prefix, channel)
            values.append(str(self._values[name]) if name in self._values else "--")
        self._channel_state[channel].setText(
            tx(f"阈值 {values[0]}  长度 {values[1]}  偏移 {values[2]}")
        )
