"""Main application window and worker coordination."""

from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import (
    QMetaObject,
    QSettings,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sitcp_host.core.models import StatusSnapshot
from sitcp_host.core.registers import DeviceProfile
from sitcp_host.core.storage import RecordingInfo, RecordingSummary
from sitcp_host.gui.data_worker import DataBatch, TcpAcquisitionWorker
from sitcp_host.gui.i18n import language, set_language, translate_widget_tree, tx
from sitcp_host.gui.theme import style_for_theme
from sitcp_host.gui.widgets import (
    ConnectionBar,
    DataPanel,
    RawAccessPanel,
    RegisterPanel,
    StatusPanel,
)
from sitcp_host.gui.widgets.controls import NoWheelComboBox
from sitcp_host.gui.worker import RbcpWorker


class MainWindow(QMainWindow):
    connect_requested = Signal(str, int, float, int)
    disconnect_requested = Signal()
    status_requested = Signal()
    register_read_requested = Signal(str)
    register_write_requested = Signal(str, int)
    raw_read_requested = Signal(int, int)
    config_sequence_requested = Signal()
    software_trigger_requested = Signal()

    def __init__(self, profile: DeviceProfile) -> None:
        super().__init__()
        self.setWindowTitle("DAQ_500MSPS_8CH_SiTCP")
        self.resize(1260, 820)
        self.setMinimumSize(980, 680)
        settings = self._settings()
        saved_language = str(settings.value("language", "zh"))
        set_language(saved_language if saved_language in {"zh", "en"} else "zh")
        self._language = language()
        saved_theme = str(settings.value("theme", "dark"))
        self._theme = saved_theme if saved_theme in {"dark", "light"} else "dark"
        self.setStyleSheet(style_for_theme(self._theme))
        self._profile = profile
        self._connected = False
        self._status_pending = False
        self._connected_host = ""
        self._data_worker: TcpAcquisitionWorker | None = None
        self._data_failed = False
        self._trigger_mode: int | None = None
        self._cfg_running = False
        self._software_trigger_pending = False
        self._software_trigger_count = 0
        self._last_auto_trigger_error = 0.0

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("DAQ_500MSPS_8CH_SiTCP")
        title.setObjectName("Title")
        subtitle = QLabel("8 通道 · 500 MSPS ADC · SiTCP 硬件 TCP")
        subtitle.setObjectName("Subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.language_combo = NoWheelComboBox()
        self.language_combo.setObjectName("LanguageSelector")
        self.language_combo.addItems(("中文", "English"))
        self.language_combo.setCurrentIndex(1 if self._language == "en" else 0)
        self.language_combo.setMaximumWidth(105)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        header.addWidget(self.language_combo)
        self.theme_button = QPushButton()
        self.theme_button.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_button)
        badge = QLabel(f"RBCP UDP {profile.rbcp_port}  ·  数据端口可配置")
        badge.setObjectName("Muted")
        header.addWidget(badge)
        layout.addLayout(header)

        self.connection_bar = ConnectionBar(profile)
        layout.addWidget(self.connection_bar)

        self.tabs = QTabWidget()
        self.status_panel = StatusPanel()
        self.data_panel = DataPanel(profile.tcp_port)
        self.register_panel = RegisterPanel(profile)
        self.raw_panel = RawAccessPanel()
        self.tabs.addTab(self.status_panel, "运行状态")
        self.tabs.addTab(self.data_panel, "实时采集")
        self.tabs.addTab(self.register_panel, "配置寄存器")
        self.tabs.addTab(self.raw_panel, "原始访问")
        layout.addWidget(self.tabs, 1)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_dock = QDockWidget("通信日志", self)
        self.log_dock.setObjectName("LogDock")
        self.log_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.log_dock.setWidget(self.log_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.log_dock)
        self.resizeDocks([self.log_dock], [360], Qt.Orientation.Horizontal)
        self.log_dock.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        self.statusBar().showMessage(tx("等待连接设备"))

        self._thread = QThread(self)
        self._worker = RbcpWorker(profile)
        self._worker.moveToThread(self._thread)
        self._thread.start()

        self.connect_requested.connect(self._worker.connect_device)
        self.disconnect_requested.connect(self._worker.disconnect_device)
        self.status_requested.connect(self._worker.read_status)
        self.register_read_requested.connect(self._worker.read_register)
        self.register_write_requested.connect(self._worker.write_register)
        self.raw_read_requested.connect(self._worker.read_raw)
        self.config_sequence_requested.connect(self._worker.run_cfg_sequence)
        self.software_trigger_requested.connect(self._worker.pulse_software_trigger)

        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.connection_failed.connect(self._on_connection_failed)
        self._worker.operation_failed.connect(self._on_operation_failed)
        self._worker.status_ready.connect(self._on_status_ready)
        self._worker.register_value_ready.connect(self._on_register_value)
        self._worker.write_completed.connect(self._on_write_completed)
        self._worker.raw_value_ready.connect(self._on_raw_value)
        self._worker.cfg_step_completed.connect(self._on_cfg_step_completed)
        self._worker.cfg_sequence_finished.connect(self._on_cfg_sequence_finished)
        self._worker.cfg_sequence_failed.connect(self._on_cfg_sequence_failed)
        self._worker.software_trigger_completed.connect(
            self._on_software_trigger_completed
        )
        self._worker.software_trigger_failed.connect(
            self._on_software_trigger_failed
        )

        self.connection_bar.connect_requested.connect(self._on_connect_requested)
        self.connection_bar.disconnect_requested.connect(self._on_disconnect_requested)
        self.status_panel.refresh_requested.connect(self._request_status)
        self.data_panel.start_requested.connect(self._on_start_data)
        self.data_panel.stop_requested.connect(self._on_stop_data)
        self.data_panel.save_start_requested.connect(self._on_start_recording)
        self.data_panel.save_stop_requested.connect(self._on_stop_recording)
        self.data_panel.trigger_buffer_clear_requested.connect(
            self._on_trigger_buffer_clear
        )
        self.data_panel.pause_plots_changed.connect(
            self._on_pause_plots_changed
        )
        self.register_panel.read_all_requested.connect(self._on_read_all)
        self.register_panel.read_requested.connect(self._on_read_register)
        self.register_panel.write_requested.connect(self._on_write_register)
        self.register_panel.cfg_sequence_requested.connect(
            self._on_cfg_sequence_requested
        )
        self.raw_panel.read_requested.connect(self._on_raw_read)

        self._software_trigger_timer = QTimer(self)
        self._software_trigger_timer.setInterval(100)
        self._software_trigger_timer.timeout.connect(self._on_software_trigger_tick)

        self._apply_theme(self._theme, persist=False)
        self._apply_language(self._language, persist=False)
        self._restore_window_state()

    @Slot(str, int, float, int)
    def _on_connect_requested(
        self,
        host: str,
        port: int,
        timeout_s: float,
        retries: int,
    ) -> None:
        self.connection_bar.set_connecting()
        self.statusBar().showMessage(tx(f"正在连接 {host}:{port} ..."))
        self._log(f"CONNECT {host}:{port}, timeout={timeout_s:.1f}s, retries={retries}")
        self.connect_requested.emit(host, port, timeout_s, retries)

    @Slot()
    def _on_disconnect_requested(self) -> None:
        self.connection_bar.set_connecting()
        self.connection_bar.state_label.setText("● 正在断开")
        self.disconnect_requested.emit()

    @Slot(str, int)
    def _on_connected(self, host: str, port: int) -> None:
        self._connected = True
        self._connected_host = host
        self._trigger_mode = None
        self.connection_bar.set_connected(host, port)
        self.status_panel.set_connected(True)
        self.data_panel.set_control_connected(True, host)
        self.register_panel.set_connected(True)
        self.raw_panel.set_connected(True)
        self.statusBar().showMessage(tx(f"已连接 {host}:{port}"))
        self._log(f"CONNECTED {host}:{port}")
        self._request_status()
        self.register_read_requested.emit("trigger_mode")

    @Slot()
    def _on_disconnected(self) -> None:
        self._set_offline("未连接")
        self._log("DISCONNECTED")

    @Slot(str)
    def _on_connection_failed(self, message: str) -> None:
        self._set_offline("连接失败")
        self.statusBar().showMessage(tx("连接失败"))
        self._log(f"CONNECT ERROR: {message}")

    @Slot(str, str)
    def _on_operation_failed(self, operation: str, message: str) -> None:
        if operation == "status":
            self._status_pending = False
            self.status_panel.finish_refresh()
        elif operation == "raw-read":
            self.raw_panel.show_error(message)
        elif ":" in operation:
            _action, name = operation.split(":", 1)
            self.register_panel.mark_error(name)
        self._log(f"{operation.upper()} ERROR: {message}")
        self.statusBar().showMessage(tx(f"{operation} 失败：{message}"), 6000)

    @Slot(object)
    def _on_status_ready(self, snapshot: StatusSnapshot) -> None:
        self._status_pending = False
        self.status_panel.update_snapshot(snapshot)
        self.statusBar().showMessage(
            tx(
                f"状态已更新，温度原始值 0x{snapshot.temperature_raw:04X}"
            ),
            2500,
        )

    @Slot(str, int, bytes)
    def _on_register_value(self, name: str, value: int, raw: bytes) -> None:
        self.register_panel.update_value(name, value, raw)
        self._log(f"READ {name}=0x{value:X}, raw={raw.hex(' ')}")
        if name == "trigger_mode":
            self._trigger_mode = value
            self._update_software_trigger_timer()

    @Slot(str, int)
    def _on_write_completed(self, name: str, value: int) -> None:
        self.register_panel.mark_pending(name)
        self._log(f"WRITE {name}=0x{value:X}")
        self._log(f"READBACK REQUEST {name}")
        self.register_read_requested.emit(name)
        self.statusBar().showMessage(tx(f"已写入 {name}=0x{value:X}"), 3000)

    @Slot(int, bytes)
    def _on_raw_value(self, address: int, data: bytes) -> None:
        self.raw_panel.show_result(address, data)
        self._log(f"RAW READ 0x{address:08X}: {data.hex(' ')}")

    @Slot()
    def _on_start_data(self) -> None:
        if (
            not self._connected
            or not self._connected_host
            or self._data_worker is not None
        ):
            return

        tcp_port = self.data_panel.selected_tcp_port()
        worker = TcpAcquisitionWorker(self._connected_host, tcp_port)
        worker.set_pause_plots_when_recording(
            self.data_panel.pause_plots_when_recording()
        )
        worker.stream_started.connect(self._on_data_started)
        worker.batch_ready.connect(self._on_data_batch)
        worker.stream_error.connect(self._on_data_error)
        worker.finished.connect(self._on_data_thread_finished)
        worker.recording_started.connect(self._on_recording_started)
        worker.recording_stopped.connect(self._on_recording_stopped)
        worker.recording_error.connect(self._on_recording_error)
        self._data_worker = worker
        self._data_failed = False
        self.data_panel.clear_charts()
        self.data_panel.mark_starting()
        self._log(
            f"DATA CONNECT {self._connected_host}:{tcp_port}"
        )
        worker.start()

    @Slot()
    def _on_stop_data(self) -> None:
        if self._data_worker is None:
            return
        self.data_panel.mark_stopping()
        self._log("DATA STOP requested")
        self._data_worker.stop()

    @Slot(str, int)
    def _on_data_started(self, host: str, port: int) -> None:
        self.data_panel.mark_active()
        self._log(f"DATA CONNECTED {host}:{port}")
        self.statusBar().showMessage(tx(f"正在接收 {host}:{port} 数据流"))

    @Slot(object)
    def _on_data_batch(self, batch: DataBatch) -> None:
        self.data_panel.update_batch(batch)

    @Slot(str)
    def _on_data_error(self, message: str) -> None:
        self._data_failed = True
        self.data_panel.show_error(message)
        self._log(f"DATA ERROR: {message}")
        self.statusBar().showMessage(tx(f"数据流错误：{message}"), 6000)

    @Slot()
    def _on_data_thread_finished(self) -> None:
        self._data_worker = None
        if not self._data_failed:
            self.data_panel.mark_stopped()
        self._log("DATA STOPPED")

    @Slot(str, str)
    def _on_start_recording(self, directory: str, filename: str) -> None:
        if self._data_worker is None:
            return
        requested = filename or "<auto>"
        self._log(f"RECORD START requested: {directory}\\{requested}")
        self._data_worker.start_recording(directory, filename)

    @Slot()
    def _on_stop_recording(self) -> None:
        if self._data_worker is None:
            return
        self._log("RECORD STOP requested")
        self._data_worker.stop_recording()

    @Slot(int)
    def _on_trigger_buffer_clear(self, value: int) -> None:
        self._on_write_register("trigger_buffer_clear", value)

    @Slot(bool)
    def _on_pause_plots_changed(self, paused: bool) -> None:
        if self._data_worker is not None:
            self._data_worker.set_pause_plots_when_recording(paused)

    @Slot(object)
    def _on_recording_started(self, info: RecordingInfo) -> None:
        self.data_panel.recording_started(info)
        self._log(f"RECORDING {info.binary_path}")
        self.statusBar().showMessage(tx(f"正在保存：{info.binary_path.name}"))

    @Slot(object)
    def _on_recording_stopped(self, summary: RecordingSummary) -> None:
        self.data_panel.recording_stopped(summary)
        if summary.error is None:
            self._log(
                f"RECORD SAVED {summary.binary_path} "
                f"bytes={summary.bytes_written} frames={summary.frames_written}"
            )
            self.statusBar().showMessage(
                tx(f"已保存：{summary.binary_path.name}"),
                5000,
            )
        else:
            self._log(
                f"RECORD FAILED {summary.binary_path}: {summary.error}"
            )
            self.statusBar().showMessage(
                tx(f"存盘异常：{summary.error}"),
                8000,
            )

    @Slot(str)
    def _on_recording_error(self, message: str) -> None:
        self.data_panel.recording_error(message)
        self._log(f"RECORD ERROR: {message}")
        self.statusBar().showMessage(tx(f"存盘错误：{message}"), 6000)

    @Slot()
    def _request_status(self) -> None:
        if not self._connected or self._status_pending:
            return
        self._status_pending = True
        self.status_requested.emit()

    @Slot(list)
    def _on_read_all(self, names: list[str]) -> None:
        if not self._connected:
            return
        for name in names:
            self.register_read_requested.emit(name)
        self._log(f"READ ALL: queued {len(names)} configuration registers")

    @Slot(str)
    def _on_read_register(self, name: str) -> None:
        if not self._connected:
            return
        self._log(f"READ REQUEST {name}")
        self.register_panel.mark_pending(name)
        self.register_read_requested.emit(name)

    @Slot(str, int)
    def _on_write_register(self, name: str, value: int) -> None:
        if not self._connected:
            return
        self._log(f"WRITE REQUEST {name}=0x{value:X}")
        self.register_write_requested.emit(name, value)

    @Slot()
    def _on_cfg_sequence_requested(self) -> None:
        if not self._connected or self._cfg_running:
            return
        self._cfg_running = True
        self._software_trigger_timer.stop()
        self._software_trigger_pending = False
        self.register_panel.set_cfg_running(True)
        self.register_panel.set_cfg_progress("准备执行")
        self._log("CFG sequence START")
        self.config_sequence_requested.emit()

    @Slot(int, int, str)
    def _on_cfg_step_completed(self, index: int, total: int, label: str) -> None:
        self.register_panel.set_cfg_progress(
            f"{index}/{total} {label} {tx('完成')}"
        )
        self._log(f"CFG STEP {index}/{total}: {label}")
        self.statusBar().showMessage(
            tx(f"CFG {index}/{total}：{label} 完成"),
            3000,
        )

    @Slot()
    def _on_cfg_sequence_finished(self) -> None:
        self._cfg_running = False
        self.register_panel.set_cfg_running(False)
        self.register_panel.set_cfg_progress("完成")
        self._log("CFG sequence COMPLETE")
        self.statusBar().showMessage(tx("一键 CFG 完成"), 5000)
        self.register_read_requested.emit("trigger_mode")
        self._request_status()

    @Slot(str, str)
    def _on_cfg_sequence_failed(self, label: str, message: str) -> None:
        self._cfg_running = False
        self.register_panel.set_cfg_running(False)
        self.register_panel.set_cfg_progress(f"{label} 失败")
        self._log(f"CFG sequence FAILED at {label}: {message}")
        self.statusBar().showMessage(tx(f"CFG 失败：{label}，{message}"), 8000)
        self.register_read_requested.emit("trigger_mode")

    @Slot()
    def _on_software_trigger_tick(self) -> None:
        if (
            not self._connected
            or self._cfg_running
            or self._trigger_mode != 4
            or self._software_trigger_pending
        ):
            return
        self._software_trigger_pending = True
        self.software_trigger_requested.emit()

    @Slot()
    def _on_software_trigger_completed(self) -> None:
        self._software_trigger_pending = False
        self._software_trigger_count += 1
        self.statusBar().showMessage(
            tx(
                f"软件触发模式：已自动触发 {self._software_trigger_count} 次"
            )
        )

    @Slot(str)
    def _on_software_trigger_failed(self, message: str) -> None:
        self._software_trigger_pending = False
        now = time.monotonic()
        if now - self._last_auto_trigger_error >= 1.0:
            self._last_auto_trigger_error = now
            self._log(f"AUTO SOFTWARE TRIGGER ERROR: {message}")
        self.statusBar().showMessage(tx(f"软件触发失败：{message}"), 3000)

    def _update_software_trigger_timer(self) -> None:
        should_run = (
            self._connected
            and self._trigger_mode == 4
            and not self._cfg_running
        )
        was_active = self._software_trigger_timer.isActive()
        if should_run and not was_active:
            self._software_trigger_pending = False
            self._software_trigger_count = 0
            self._software_trigger_timer.start()
            self._log("AUTO SOFTWARE TRIGGER enabled, interval=100ms")
        elif not should_run and was_active:
            self._software_trigger_timer.stop()
            self._software_trigger_pending = False
            self._log("AUTO SOFTWARE TRIGGER disabled")

    @Slot(int, int)
    def _on_raw_read(self, address: int, length: int) -> None:
        if not self._connected:
            return
        self.raw_read_requested.emit(address, length)

    def _set_offline(self, reason: str) -> None:
        if self._data_worker is not None:
            self._data_worker.stop()
        self._connected = False
        self._connected_host = ""
        self._status_pending = False
        self.connection_bar.set_offline(reason)
        self.status_panel.set_connected(False)
        self._software_trigger_timer.stop()
        self._software_trigger_pending = False
        self._trigger_mode = None
        self._cfg_running = False
        self.register_panel.set_cfg_running(False)
        self.register_panel.set_cfg_progress("已断开")
        self.data_panel.set_control_connected(False)
        self.register_panel.set_connected(False)
        self.raw_panel.set_connected(False)
        self.statusBar().showMessage(tx(reason))

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_view.appendPlainText(f"[{timestamp}] {message}")

    def _settings(self) -> QSettings:
        return QSettings("SiTCP", "Host")

    def _toggle_theme(self) -> None:
        self._apply_theme("light" if self._theme == "dark" else "dark")

    def _on_language_changed(self, index: int) -> None:
        self._apply_language("en" if index == 1 else "zh")

    def _apply_language(self, language_code: str, *, persist: bool = True) -> None:
        self._language = "en" if language_code == "en" else "zh"
        set_language(self._language)
        translate_widget_tree(self)
        self.theme_button.setText(
            tx("亮色主题" if self._theme == "dark" else "暗色主题")
        )
        self.statusBar().showMessage(tx("就绪"))
        self.language_combo.blockSignals(True)
        self.language_combo.setCurrentIndex(1 if self._language == "en" else 0)
        self.language_combo.blockSignals(False)
        if persist:
            self._settings().setValue("language", self._language)

    def _apply_theme(self, theme: str, *, persist: bool = True) -> None:
        self._theme = "light" if theme == "light" else "dark"
        self.setStyleSheet(style_for_theme(self._theme))
        self.data_panel.apply_theme(self._theme)
        self.theme_button.setText(
            tx("亮色主题" if self._theme == "dark" else "暗色主题")
        )
        if persist:
            self._settings().setValue("theme", self._theme)

    def _restore_window_state(self) -> None:
        settings = self._settings()
        geometry = settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = settings.value("window_state")
        if state is not None:
            self.restoreState(state)

    def closeEvent(self, event: QCloseEvent) -> None:
        settings = self._settings()
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("window_state", self.saveState())
        self.status_panel.set_connected(False)
        self._software_trigger_timer.stop()
        if self._data_worker is not None:
            self._data_worker.stop()
            self._data_worker.wait(12000)
        if self._thread.isRunning():
            try:
                QMetaObject.invokeMethod(
                    self._worker,
                    "shutdown",
                    Qt.ConnectionType.BlockingQueuedConnection,
                )
            finally:
                self._thread.quit()
                self._thread.wait(3000)
        super().closeEvent(event)

