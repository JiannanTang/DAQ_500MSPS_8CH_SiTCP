"""Live ADC acquisition controls, eight channel plots, and raw recording."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QMargins, QPointF, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from sitcp_host.core.conversions import (
    ADC_VOLTAGE_CODE_SPAN,
    ADC_VOLTAGE_FULL_SCALE_MV,
)
from sitcp_host.core.storage import RecordingInfo, RecordingSummary
from sitcp_host.config import default_capture_directory
from sitcp_host.gui.data_worker import DataBatch
from sitcp_host.gui.i18n import tx
from sitcp_host.gui.theme import chart_palette
from sitcp_host.gui.widgets.controls import NoWheelComboBox, NoWheelSpinBox

ADC_SAMPLE_INTERVAL_NS = 2.0


class _StatCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(1)
        label = QLabel(title)
        label.setObjectName("Muted")
        self.value = QLabel("--")
        self.value.setObjectName("MetricValue")
        layout.addWidget(label)
        layout.addWidget(self.value)


class _ChannelPlot(QFrame):
    def __init__(self, channel: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.channel = channel
        self._theme = "dark"

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(3)

        header = QHBoxLayout()
        title = QLabel(f"CH{channel}")
        title.setObjectName("SectionTitle")
        self.state = QLabel("等待数据")
        self.state.setObjectName("Muted")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.state)
        root.addLayout(header)

        self.meta = QLabel("尚无触发数据")
        self.meta.setObjectName("MetricDetail")
        root.addWidget(self.meta)

        self.chart = QChart()
        self.chart.setMargins(QMargins(2, 2, 2, 2))
        self.chart.legend().hide()
        self.chart.setBackgroundBrush(QColor("#111A24"))
        self.chart.setPlotAreaBackgroundBrush(QColor("#111A24"))
        self.chart.setPlotAreaBackgroundVisible(True)
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)

        self.x_axis = QValueAxis()
        self.x_axis.setTitleText("Time (ns)")
        self.x_axis.setRange(0, 55 * ADC_SAMPLE_INTERVAL_NS)
        self.x_axis.setTickCount(6)
        self.x_axis.setLabelFormat("%.0f")
        self.x_axis.setLabelsColor(QColor("#7D93A9"))
        self.x_axis.setGridLineColor(QColor("#223143"))

        self.y_axis = QValueAxis()
        self.y_axis.setRange(-100, 100)
        self.y_axis.setTickCount(5)
        self.y_axis.setLabelsColor(QColor("#7D93A9"))
        self.y_axis.setGridLineColor(QColor("#223143"))

        self.series = QLineSeries()
        pen = QPen(QColor(chart_palette("dark")["channels"][channel]))
        pen.setWidthF(1.4)
        self.series.setPen(pen)
        self.chart.addSeries(self.series)
        self.chart.addAxis(self.x_axis, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.y_axis, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.x_axis)
        self.series.attachAxis(self.y_axis)

        view = QChartView(self.chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setMinimumHeight(165)
        root.addWidget(view, 1)
        self.apply_theme("dark")

    def update_frame(self, frame, display_mode: str) -> None:
        if display_mode == "voltage":
            samples = (
                frame.samples.astype(float)
                * ADC_VOLTAGE_FULL_SCALE_MV
                / ADC_VOLTAGE_CODE_SPAN
            )
            self.y_axis.setTitleText("mV")
            self.y_axis.setLabelFormat("%.1f")
        else:
            samples = frame.samples
            self.y_axis.setTitleText("code")
            self.y_axis.setLabelFormat("%.0f")
        self.series.replace(
            [
                QPointF(index * ADC_SAMPLE_INTERVAL_NS, float(value))
                for index, value in enumerate(samples.tolist())
            ]
        )
        if frame.sample_count > 1:
            self.x_axis.setRange(
                0,
                (frame.sample_count - 1) * ADC_SAMPLE_INTERVAL_NS,
            )
        if samples.size:
            minimum = float(samples.min())
            maximum = float(samples.max())
            span = max(maximum - minimum, 20)
            center = (minimum + maximum) / 2
            padding = span * 0.15
            self.y_axis.setRange(
                center - span / 2 - padding,
                center + span / 2 + padding,
            )
        self.state.setText(tx("已更新"))
        self.state.setObjectName("StateOnline")
        self._repolish(self.state)
        self.meta.setText(
            f"trig_id={frame.trig_id}  "
            f"time=0x{frame.trigger_time:016X}  "
            f"len={frame.length}  offset={frame.offset}"
        )

    def clear(self) -> None:
        self.series.clear()
        self.state.setText(tx("等待数据"))
        self.state.setObjectName("Muted")
        self._repolish(self.state)
        self.meta.setText(tx("尚无触发数据"))
        self.x_axis.setRange(0, 55 * ADC_SAMPLE_INTERVAL_NS)
        self.y_axis.setRange(-100, 100)
        self.y_axis.setTitleText("code")
        self.y_axis.setLabelFormat("%.0f")

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        palette = chart_palette(theme)
        color = QColor(str(palette["background"]))
        self.chart.setBackgroundBrush(color)
        self.chart.setPlotAreaBackgroundBrush(color)
        for axis in (self.x_axis, self.y_axis):
            axis.setLabelsColor(QColor(str(palette["axis"])))
            axis.setTitleBrush(QColor(str(palette["axis"])))
            axis.setGridLineColor(QColor(str(palette["grid"])))
        pen = QPen(QColor(str(palette["channels"][self.channel])))
        pen.setWidthF(1.4)
        self.series.setPen(pen)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)


class DataPanel(QWidget):
    start_requested = Signal()
    stop_requested = Signal()
    save_start_requested = Signal(str, str)
    save_stop_requested = Signal()
    trigger_buffer_clear_requested = Signal(int)
    pause_plots_changed = Signal(bool)

    def __init__(
        self,
        default_tcp_port: int = 24,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._control_connected = False
        self._active = False
        self._starting = False
        self._stopping = False
        self._recording = False
        self._recording_pending = False
        self._theme = "dark"
        self._display_mode = "code"
        self._latest_frames: dict[int, object] = {}
        self._settings = QSettings("SiTCP", "Host")
        self._pause_plots_during_recording = self._settings.value(
            "pause_plots_when_recording",
            False,
            type=bool,
        )
        saved_directory = self._settings.value(
            "capture_directory",
            str(default_capture_directory()),
        )
        self._capture_directory = Path(str(saved_directory))

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(9)

        acquisition_row = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("实时采集")
        title.setObjectName("SectionTitle")
        self.endpoint_label = QLabel("TCP 数据流未配置")
        self.endpoint_label.setObjectName("Muted")
        heading.addWidget(title)
        heading.addWidget(self.endpoint_label)
        acquisition_row.addLayout(heading)

        acquisition_row.addSpacing(18)
        acquisition_row.addWidget(QLabel("TCP 端口"))
        self.tcp_port_spin = NoWheelSpinBox()
        self.tcp_port_spin.setRange(1, 65535)
        saved_tcp_port = self._settings.value("data_tcp_port", default_tcp_port)
        try:
            self.tcp_port_spin.setValue(int(saved_tcp_port))
        except (TypeError, ValueError):
            self.tcp_port_spin.setValue(default_tcp_port)
        self.tcp_port_spin.setMaximumWidth(95)
        self.tcp_port_spin.valueChanged.connect(
            lambda value: self._settings.setValue("data_tcp_port", value)
        )
        acquisition_row.addWidget(self.tcp_port_spin)

        acquisition_row.addWidget(QLabel("显示"))
        self.display_combo = NoWheelComboBox()
        self.display_combo.addItems(("码值", "电压 (mV)"))
        self.display_combo.setMaximumWidth(115)
        self.display_combo.currentIndexChanged.connect(self._on_display_mode_changed)
        acquisition_row.addWidget(self.display_combo)
        acquisition_row.addStretch(1)

        self.state_label = QLabel("● 未采集")
        self.state_label.setObjectName("StateOffline")
        acquisition_row.addWidget(self.state_label)
        self.start_button = QPushButton("开始采集")
        self.start_button.setObjectName("Primary")
        self.start_button.clicked.connect(self.start_requested)
        acquisition_row.addWidget(self.start_button)
        self.stop_button = QPushButton("停止采集")
        self.stop_button.clicked.connect(self.stop_requested)
        acquisition_row.addWidget(self.stop_button)
        root.addLayout(acquisition_row)

        recording_row = QHBoxLayout()
        self.choose_directory_button = QPushButton("选择目录")
        self.choose_directory_button.clicked.connect(self._choose_directory)
        recording_row.addWidget(self.choose_directory_button)
        recording_row.addWidget(QLabel("文件名"))
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("留空自动命名")
        self.filename_edit.setMaximumWidth(190)
        recording_row.addWidget(self.filename_edit)
        self.directory_label = QLabel(str(self._capture_directory))
        self.directory_label.setObjectName("Muted")
        self.directory_label.setMinimumWidth(120)
        self.directory_label.setToolTip(str(self._capture_directory))
        recording_row.addWidget(self.directory_label, 1)
        self.pause_plot_button = QPushButton("存盘时暂停波形")
        self.pause_plot_button.setCheckable(True)
        self.pause_plot_button.setChecked(self._pause_plots_during_recording)
        self.pause_plot_button.setToolTip(
            "勾选后，存盘期间暂停曲线刷新；TCP 接收和原始数据写入继续运行。"
        )
        self.pause_plot_button.toggled.connect(self._on_pause_plots_toggled)
        recording_row.addWidget(self.pause_plot_button)
        self.plot_state_label = QLabel("波形：实时")
        self.plot_state_label.setObjectName("Muted")
        recording_row.addWidget(self.plot_state_label)
        recording_row.addStretch(1)
        self.record_button = QPushButton("开始存盘")
        self.record_button.setObjectName("Primary")
        self.record_button.clicked.connect(self._on_record_clicked)
        recording_row.addWidget(self.record_button)
        self.trigger_clear_button = QPushButton("清空触发缓存")
        self.trigger_clear_button.setObjectName("Danger")
        self.trigger_clear_button.setToolTip(
            "切换触发模式或修改通道触发长度后，清空固件触发模块缓存。"
        )
        self.trigger_clear_button.pressed.connect(
            lambda: self.trigger_buffer_clear_requested.emit(1)
        )
        self.trigger_clear_button.released.connect(
            lambda: self.trigger_buffer_clear_requested.emit(0)
        )
        recording_row.addWidget(self.trigger_clear_button)
        self.recording_state_label = QLabel("未存盘")
        self.recording_state_label.setObjectName("Muted")
        recording_row.addWidget(self.recording_state_label)
        root.addLayout(recording_row)

        stats = QGridLayout()
        stats.setHorizontalSpacing(8)
        self.rate_card = _StatCard("吞吐率")
        self.frame_rate_card = _StatCard("帧率")
        self.sample_rate_card = _StatCard("采样率")
        self.count_card = _StatCard("累计帧")
        self.file_card = _StatCard("本次存盘")
        for column, card in enumerate(
            (
                self.rate_card,
                self.frame_rate_card,
                self.sample_rate_card,
                self.count_card,
                self.file_card,
            )
        ):
            stats.addWidget(card, 0, column)
            stats.setColumnStretch(column, 1)
        root.addLayout(stats)

        self.channel_label = QLabel("通道帧计数：尚未收到数据")
        self.channel_label.setObjectName("Muted")
        root.addWidget(self.channel_label)
        self.trigger_label = QLabel("最近触发：--")
        self.trigger_label.setObjectName("Muted")
        root.addWidget(self.trigger_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 4, 0)
        grid.setSpacing(9)
        self.plots: dict[int, _ChannelPlot] = {}
        self.series: dict[int, QLineSeries] = {}
        for channel in range(8):
            plot = _ChannelPlot(channel)
            self.plots[channel] = plot
            self.series[channel] = plot.series
            grid.addWidget(plot, channel // 2, channel % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for row in range(4):
            grid.setRowStretch(row, 1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        warning = QLabel(
            "波形可选择显示码值（原始值减 8192）或电压 mV，"
            "电压公式为 (code-8192) × 1800 / 16384。"
            "存盘保存完整帧的原始字节；协议没有同步字，因此文件也从完整帧边界开始。"
        )
        warning.setObjectName("Muted")
        warning.setWordWrap(True)
        root.addWidget(warning)
        self.apply_theme("dark")
        self._refresh_plot_state(False)
        self._refresh_buttons()

    def set_control_connected(
        self,
        connected: bool,
        host: str = "",
    ) -> None:
        self._control_connected = connected
        if connected:
            self.endpoint_label.setText(tx(f"数据端点 {host}"))
        else:
            self.endpoint_label.setText(tx("TCP 数据流未配置"))
            self._active = False
            self._starting = False
            self._stopping = False
        self._refresh_buttons()

    def mark_starting(self) -> None:
        self._starting = True
        self._active = False
        self._stopping = False
        self._set_acquisition_state(tx("● 正在连接数据流"), "StateBusy")
        self._refresh_buttons()

    def mark_active(self) -> None:
        self._starting = False
        self._active = True
        self._stopping = False
        self._set_acquisition_state(tx("● 正在采集"), "StateOnline")
        self._refresh_buttons()

    def mark_stopping(self) -> None:
        self._stopping = True
        self._starting = False
        self._set_acquisition_state(tx("● 正在停止"), "StateBusy")
        self._refresh_buttons()

    def mark_stopped(self) -> None:
        self._active = False
        self._starting = False
        self._stopping = False
        self._recording = False
        self._recording_pending = False
        self._set_acquisition_state(tx("● 已停止"), "StateOffline")
        self.rate_card.value.setText("--")
        self.frame_rate_card.value.setText("--")
        self.sample_rate_card.value.setText("--")
        self._refresh_buttons()

    def update_batch(self, batch: DataBatch) -> None:
        stats = batch.stats
        self.rate_card.value.setText(f"{stats.bytes_per_second / 1_000_000:.2f} MB/s")
        self.frame_rate_card.value.setText(f"{stats.frames_per_second:.1f} /s")
        self.sample_rate_card.value.setText(
            f"{stats.samples_per_second / 1_000_000:.2f} MS/s"
        )
        self.count_card.value.setText(f"{stats.frames_total:,}")
        if stats.recording_active:
            self.file_card.value.setText(
                f"{stats.recording_bytes / 1_000_000:.2f} MB"
            )
        self.channel_label.setText(
            tx(
                "通道帧计数："
            + "  ".join(
                f"CH{channel}={count}"
                for channel, count in enumerate(stats.channel_frames)
            )
            )
        )

        if batch.latest_frames:
            latest = max(
                batch.latest_frames.values(),
                key=lambda frame: frame.trigger_time,
            )
            self.trigger_label.setText(
                tx(
                    f"最近触发：trig_id={latest.trig_id}  "
                f"time=0x{latest.trigger_time:016X}  "
                f"threshold={latest.threshold}  "
                f"length={latest.length}  offset={latest.offset}"
                )
            )
            for channel, frame in sorted(batch.latest_frames.items()):
                self._latest_frames[channel] = frame
            if not (
                self._pause_plots_during_recording
                and stats.recording_active
            ):
                for channel, frame in sorted(batch.latest_frames.items()):
                    self.plots[channel].update_frame(frame, self._display_mode)
            self._refresh_plot_state(stats.recording_active)

    def recording_started(self, info: RecordingInfo) -> None:
        self._recording = True
        self._recording_pending = False
        self.recording_state_label.setText(
            tx(f"正在保存：{info.binary_path.name}")
        )
        self.recording_state_label.setToolTip(str(info.binary_path))
        self._refresh_plot_state(True)
        self._refresh_buttons()

    def recording_stopped(self, summary: RecordingSummary) -> None:
        self._recording = False
        self._recording_pending = False
        state = "已保存" if summary.error is None else "保存异常"
        self.recording_state_label.setText(
            tx(
                f"{state}：{summary.binary_path.name} "
            f"({summary.bytes_written / 1_000_000:.2f} MB, "
            f"{summary.frames_written} 帧)"
            )
        )
        self.recording_state_label.setToolTip(str(summary.binary_path))
        self.file_card.value.setText(
            f"{summary.bytes_written / 1_000_000:.2f} MB"
        )
        for channel, frame in self._latest_frames.items():
            self.plots[channel].update_frame(frame, self._display_mode)
        self._refresh_plot_state(False)
        self._refresh_buttons()

    def recording_error(self, message: str) -> None:
        self._recording = False
        self._recording_pending = False
        self.recording_state_label.setText(tx(f"存盘错误：{message}"))
        for channel, frame in self._latest_frames.items():
            self.plots[channel].update_frame(frame, self._display_mode)
        self._refresh_plot_state(False)
        self._refresh_buttons()

    def show_error(self, message: str) -> None:
        self._active = False
        self._starting = False
        self._stopping = False
        self._set_acquisition_state(tx("● 数据流错误"), "StateOffline")
        self.channel_label.setText(tx(f"采集错误：{message}"))
        self._refresh_plot_state(False)
        self._refresh_buttons()

    def clear_charts(self) -> None:
        for plot in self.plots.values():
            plot.clear()
        self._latest_frames.clear()
        self.channel_label.setText(tx("通道帧计数：尚未收到数据"))
        self.trigger_label.setText(tx("最近触发：--"))
        self.file_card.value.setText("--")
        self.recording_state_label.setText(tx("未存盘"))
        self.recording_state_label.setToolTip("")
        self._refresh_plot_state(False)

    def _on_record_clicked(self) -> None:
        if self._recording or self._recording_pending:
            self.save_stop_requested.emit()
            self.recording_state_label.setText(tx("正在结束存盘..."))
            self.recording_state_label.setToolTip("")
            self._recording_pending = True
            self._refresh_buttons()
            return
        if not self._active:
            return
        self._recording_pending = True
        self.recording_state_label.setText(tx("正在创建存盘文件..."))
        self.recording_state_label.setToolTip("")
        self.save_start_requested.emit(
            str(self._capture_directory),
            self.filename_edit.text().strip(),
        )
        self._refresh_buttons()

    def _choose_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            tx("选择原始数据保存目录"),
            str(self._capture_directory),
        )
        if directory:
            self._capture_directory = Path(directory)
            self.directory_label.setText(str(self._capture_directory))
            self.directory_label.setToolTip(str(self._capture_directory))
            self._settings.setValue(
                "capture_directory",
                str(self._capture_directory),
            )

    def _set_acquisition_state(self, text: str, style_name: str) -> None:
        self.state_label.setText(text)
        self.state_label.setObjectName(style_name)
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)

    def _on_display_mode_changed(self, index: int) -> None:
        self._display_mode = "voltage" if index == 1 else "code"
        for channel, frame in self._latest_frames.items():
            self.plots[channel].update_frame(frame, self._display_mode)

    def _on_pause_plots_toggled(self, checked: bool) -> None:
        self._pause_plots_during_recording = checked
        self._settings.setValue("pause_plots_when_recording", checked)
        self.pause_plots_changed.emit(checked)
        if not checked:
            for channel, frame in self._latest_frames.items():
                self.plots[channel].update_frame(frame, self._display_mode)
        self._refresh_plot_state(self._recording)

    def _refresh_plot_state(self, recording_active: bool) -> None:
        if self._pause_plots_during_recording and recording_active:
            self.plot_state_label.setText(tx("波形：存盘中已暂停"))
        elif self._pause_plots_during_recording:
            self.plot_state_label.setText(tx("波形：实时（存盘时暂停）"))
        else:
            self.plot_state_label.setText(tx("波形：实时"))

    def selected_tcp_port(self) -> int:
        return self.tcp_port_spin.value()

    def pause_plots_when_recording(self) -> bool:
        return self._pause_plots_during_recording

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        for plot in self.plots.values():
            plot.apply_theme(theme)

    def _refresh_buttons(self) -> None:
        idle = not self._active and not self._starting and not self._stopping
        self.start_button.setEnabled(self._control_connected and idle)
        self.tcp_port_spin.setEnabled(self._control_connected and idle)
        self.stop_button.setEnabled(self._active and not self._stopping)
        self.choose_directory_button.setEnabled(
            not self._recording and not self._recording_pending
        )
        self.filename_edit.setEnabled(
            not self._recording and not self._recording_pending
        )
        self.record_button.setEnabled(self._active and not self._stopping)
        self.trigger_clear_button.setEnabled(self._control_connected)
        if self._recording or self._recording_pending:
            self.record_button.setText(tx("停止存盘"))
            self.record_button.setObjectName("Danger")
        else:
            self.record_button.setText(tx("开始存盘"))
            self.record_button.setObjectName("Primary")
        self.record_button.style().unpolish(self.record_button)
        self.record_button.style().polish(self.record_button)
