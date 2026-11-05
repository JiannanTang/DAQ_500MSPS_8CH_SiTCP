from __future__ import annotations

import os
import re
import socket
import tempfile
import threading
import unittest
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import (
        QAbstractButton,
        QApplication,
        QComboBox,
        QLabel,
        QTabWidget,
        QWidget,
    )

    from sitcp_host.core.models import StatusSnapshot
    from sitcp_host.core.registers import load_profile
    from sitcp_host.gui.main_window import MainWindow
    from sitcp_host.gui.data_worker import DataBatch, TcpAcquisitionWorker
    from sitcp_host.gui.i18n import set_language
    from sitcp_host.gui.widgets.data import DataPanel
    from sitcp_host.gui.widgets.controls import NoWheelSpinBox
    from sitcp_host.gui.widgets.registers import RegisterPanel
    from sitcp_host.gui.widgets.status import StatusPanel
    from sitcp_host.gui.worker import RbcpWorker
    from sitcp_host.testing.fake_rbcp import FakeRbcpServer

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False


@unittest.skipUnless(GUI_AVAILABLE, "PySide6 is not installed")
class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        config = Path(__file__).resolve().parents[1] / "config" / "registers.toml"
        cls.profile = load_profile(config)

    def setUp(self) -> None:
        set_language("zh")

    def test_window_constructs_and_shuts_down(self) -> None:
        window = MainWindow(self.profile)
        self.assertEqual(window.tabs.count(), 4)
        self.assertEqual(len(window.register_panel._registers), 40)
        window.close()
        self.app.processEvents()

    def test_worker_reads_status_from_fake_device(self) -> None:
        with FakeRbcpServer() as server:
            server.set_bytes(0x0108, b"\x34\x12\x02\x10")
            worker = RbcpWorker(self.profile)
            connected: list[tuple[str, int]] = []
            statuses: list[StatusSnapshot] = []
            failures: list[tuple[str, str]] = []
            writes: list[tuple[str, int]] = []
            values: list[tuple[str, int, bytes]] = []
            worker.connected.connect(
                lambda host, port: connected.append((host, port))
            )
            worker.status_ready.connect(statuses.append)
            worker.write_completed.connect(
                lambda name, value: writes.append((name, value))
            )
            worker.register_value_ready.connect(
                lambda name, value, raw: values.append((name, value, raw))
            )
            worker.operation_failed.connect(
                lambda operation, message: failures.append((operation, message))
            )

            worker.connect_device(server.host, server.port, 0.2, 1)
            worker.read_status()
            worker.write_register("trigger_mode", 2)
            worker.read_register("trigger_mode")
            worker.shutdown()

        self.assertEqual(connected, [(server.host, server.port)])
        self.assertEqual(failures, [])
        self.assertEqual(
            statuses,
            [StatusSnapshot(0x1234, 0x02, 0x10)],
        )
        self.assertEqual(writes, [("trigger_mode", 2)])
        self.assertEqual(values, [("trigger_mode", 2, b"\x02")])

    def test_tcp_worker_parses_a_stream_and_emits_batch(self) -> None:
        header0 = (
            (5 << 60)
            | (0x12345 << 32)
            | (7000 << 16)
            | (2 << 8)
            | 3
        )
        trigger_time = 0x1122334455667788
        samples = (0x2000, 0x2001, 0x1FFF, 0x2002, 0x1FFE, 0x2003, 0x2004, 0x1FFD)
        frame = (
            header0.to_bytes(8, "big")
            + trigger_time.to_bytes(8, "big")
            + b"".join(sample.to_bytes(2, "big") for sample in samples)
        )

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def serve() -> None:
            connection, _address = listener.accept()
            with connection:
                connection.sendall(frame)
            listener.close()

        server_thread = threading.Thread(target=serve, daemon=True)
        server_thread.start()

        worker = TcpAcquisitionWorker("127.0.0.1", port)
        batches: list[DataBatch] = []
        errors: list[str] = []
        worker.batch_ready.connect(batches.append)
        worker.stream_error.connect(errors.append)
        worker.run()
        server_thread.join(timeout=1.0)

        self.assertEqual(errors, [])
        self.assertEqual(len(batches), 1)
        received = batches[0].latest_frames[5]
        self.assertEqual(received.trig_id, 0x12345)
        self.assertEqual(received.threshold, 7000)
        self.assertEqual(received.samples.tolist(), [0, 1, -1, 2, -2, 3, 4, -3])

        panel = DataPanel()
        panel.update_batch(batches[0])
        self.assertEqual(len(panel.plots), 8)
        self.assertEqual(panel.series[5].count(), 8)
        self.assertEqual(panel.series[5].at(1).x(), 2.0)
        self.assertEqual(panel.plots[5].x_axis.max(), 14.0)
        self.assertEqual(panel.plots[5].x_axis.titleText(), "Time (ns)")
        original_tcp_port = panel.selected_tcp_port()
        panel.tcp_port_spin.setValue(12345)
        self.assertEqual(panel.selected_tcp_port(), 12345)
        panel.display_combo.setCurrentIndex(1)
        self.assertEqual(panel.plots[5].y_axis.labelFormat(), "%.1f")
        self.assertAlmostEqual(
            panel.series[5].at(1).y(),
            1800.0 / 16384.0,
            places=6,
        )
        panel.display_combo.setCurrentIndex(0)
        self.assertEqual(panel.plots[5].y_axis.labelFormat(), "%.0f")
        self.assertEqual(panel.series[5].at(1).y(), 1.0)
        panel.tcp_port_spin.setValue(original_tcp_port)

        original_pause = panel.pause_plot_button.isChecked()
        panel.pause_plot_button.setChecked(True)
        panel.series[5].clear()
        paused_stats = replace(batches[0].stats, recording_active=True)
        panel.update_batch(DataBatch(batches[0].latest_frames, paused_stats))
        self.assertEqual(panel.series[5].count(), 0)
        self.assertIn("已暂停", panel.plot_state_label.text())
        panel.update_batch(batches[0])
        self.assertEqual(panel.series[5].count(), 8)
        panel.pause_plot_button.setChecked(original_pause)

    def test_tcp_worker_records_raw_frame_bytes(self) -> None:
        header0 = (2 << 60) | (9 << 32) | (5000 << 16) | (2 << 8) | 1
        trigger_time = 0x1111222233334444
        samples = (0x2000, 0x2001, 0x1FFF, 0x2002, 0x1FFE, 0x2003, 0x2004, 0x1FFD)
        frame = (
            header0.to_bytes(8, "big")
            + trigger_time.to_bytes(8, "big")
            + b"".join(sample.to_bytes(2, "big") for sample in samples)
        )

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def serve() -> None:
            connection, _address = listener.accept()
            with connection:
                connection.sendall(frame)
            listener.close()

        server_thread = threading.Thread(target=serve, daemon=True)
        server_thread.start()

        with tempfile.TemporaryDirectory() as directory:
            worker = TcpAcquisitionWorker("127.0.0.1", port)
            worker.set_pause_plots_when_recording(True)
            summaries = []
            errors = []
            batches = []
            worker.recording_stopped.connect(summaries.append)
            worker.recording_error.connect(errors.append)
            worker.batch_ready.connect(batches.append)
            worker.start_recording(directory, "worker_capture.bin")
            worker.run()
            server_thread.join(timeout=1.0)

            self.assertEqual(errors, [])
            self.assertEqual(len(summaries), 1)
            summary = summaries[0]
            self.assertIsNone(summary.error)
            self.assertEqual(summary.frames_written, 1)
            self.assertEqual(summary.binary_path.read_bytes(), frame)
            self.assertEqual(summary.binary_path.name, "worker_capture.bin")
            self.assertEqual(batches[-1].latest_frames, {})

    def test_recording_filename_is_forwarded_from_ui(self) -> None:
        panel = DataPanel()
        panel.set_control_connected(True, "127.0.0.1")
        panel.mark_active()
        panel.filename_edit.setText("manual_capture")
        requests: list[tuple[str, str]] = []
        panel.save_start_requested.connect(
            lambda directory, filename: requests.append((directory, filename))
        )
        panel._on_record_clicked()
        self.assertEqual(requests[-1][1], "manual_capture")
        clear_values: list[int] = []
        panel.trigger_buffer_clear_requested.connect(clear_values.append)
        panel.trigger_clear_button.click()
        self.assertEqual(clear_values, [1, 0])

    def test_register_panel_pulse_and_exclusive_mode_controls(self) -> None:
        panel = RegisterPanel(self.profile)
        panel.set_connected(True)
        writes: list[tuple[str, int]] = []
        panel.write_requested.connect(lambda name, value: writes.append((name, value)))

        panel._momentary_buttons["system_reset"].click()
        self.assertEqual(
            writes,
            [("system_reset", 1), ("system_reset", 0)],
        )

        writes.clear()
        panel._mode_buttons[1].click()
        panel._mode_buttons[2].click()
        self.assertEqual(
            writes,
            [("trigger_mode", 1), ("trigger_mode", 2)],
        )
        self.assertFalse(panel._mode_buttons[1].isChecked())
        self.assertTrue(panel._mode_buttons[2].isChecked())
        panel.update_value("trigger_mode", 1, b"\x01")
        self.assertTrue(panel._mode_buttons[1].isChecked())
        self.assertFalse(panel._mode_buttons[2].isChecked())

        writes.clear()
        panel.all_threshold.setValue(100)
        panel.all_length.setValue(20)
        panel.all_offset.setValue(3)
        panel._apply_all_channels()
        self.assertEqual(len(writes), 24)
        self.assertEqual(writes[0], ("threshold_ch0", 100))
        self.assertEqual(writes[-1], ("trigger_offset_ch7", 3))

        writes.clear()
        powerdown = panel._toggle_buttons["ad9694_powerdown"]
        powerdown.click()
        self.assertEqual(writes, [("ad9694_powerdown", 3)])
        self.assertIn("Power Down", powerdown.text())
        powerdown.click()
        self.assertEqual(writes[-1], ("ad9694_powerdown", 0))
        self.assertIn("正常工作", powerdown.text())

        self.assertIn("ad9528_reset", panel._momentary_buttons)
        self.assertNotIn("trigger_buffer_clear", panel._momentary_buttons)
        self.assertNotIn("software_trigger", panel._momentary_buttons)
        self.assertEqual(len(panel._mode_buttons), 5)

        panel.update_value("trigger_channel", 0b10000101, b"\x85")
        panel.mark_pending("trigger_channel")
        panel.update_value("trigger_channel", 0b10000101, b"\x85")
        panel.update_value("coincidence_channel_a", 3, b"\x03")
        panel.update_value("coincidence_channel_b", 4, b"\x04")
        panel.mark_pending("coincidence_channel_a")
        panel.mark_pending("coincidence_channel_b")
        channel_checks = panel._bitmask_checks["trigger_channel"]
        self.assertEqual(
            [checkbox.isChecked() for checkbox in channel_checks],
            [True, False, True, False, False, False, False, True],
        )
        writes.clear()
        channel_checks[1].setChecked(True)
        panel._write_value("trigger_channel")
        self.assertEqual(writes, [("trigger_channel", 0b10000111)])

        panel.update_value("channel_trigger_edge", 0b01010101, b"\x55")
        edge_checks = panel._bitmask_checks["channel_trigger_edge"]
        self.assertEqual(
            [checkbox.isChecked() for checkbox in edge_checks],
            [True, False, True, False, True, False, True, False],
        )

    def test_cfg_sequence_and_software_trigger_worker_actions(self) -> None:
        with FakeRbcpServer() as server:
            worker = RbcpWorker(self.profile)
            steps: list[tuple[int, int, str]] = []
            finished: list[bool] = []
            failures: list[tuple[str, str]] = []
            trigger_done: list[bool] = []
            worker.cfg_step_completed.connect(
                lambda index, total, label: steps.append((index, total, label))
            )
            worker.cfg_sequence_finished.connect(lambda: finished.append(True))
            worker.cfg_sequence_failed.connect(
                lambda label, message: failures.append((label, message))
            )
            worker.software_trigger_completed.connect(
                lambda: trigger_done.append(True)
            )
            worker.connect_device(server.host, server.port, 0.2, 1)

            with patch("sitcp_host.gui.worker.time.sleep") as sleep:
                worker.run_cfg_sequence()
            worker.pulse_software_trigger()
            worker.shutdown()

        self.assertEqual(failures, [])
        self.assertEqual(finished, [True])
        self.assertEqual(
            [label for _index, _total, label in steps],
            [
                "系统复位",
                "AD9528 复位",
                "配置 AD9528",
                "配置 AD9694",
                "开始 JESD204B 同步",
                "JESD 状态读取",
            ],
        )
        self.assertEqual(trigger_done, [True])
        self.assertEqual(
            [
                call.args[0]
                for call in sleep.call_args_list
                if call.args and call.args[0] == 0.01
            ],
            [0.01, 0.01, 0.01, 0.01, 0.01],
        )

    def test_software_trigger_mode_starts_100ms_timer(self) -> None:
        window = MainWindow(self.profile)
        window._connected = True
        window._on_register_value("trigger_mode", 4, b"\x04")
        self.assertTrue(window._software_trigger_timer.isActive())
        self.assertEqual(window._software_trigger_timer.interval(), 100)
        self.assertTrue(window.register_panel._mode_buttons[4].isChecked())
        window._on_register_value("trigger_mode", 3, b"\x03")
        self.assertFalse(window._software_trigger_timer.isActive())
        window.close()
        self.app.processEvents()

    def test_status_panel_displays_temperature_in_celsius(self) -> None:
        panel = StatusPanel()
        self.assertEqual(panel.interval_spin.value(), 5)
        self.assertEqual(panel.interval_spin.suffix(), " s")
        panel.set_connected(True)
        self.assertEqual(panel._timer.interval(), 5000)
        panel.update_snapshot(StatusSnapshot(0x0AB5, 0x11, 0x10))
        self.assertIn("64.1 °C", panel.temp_card.value_label.text())
        self.assertEqual(panel.sync_card.health_label.text(), "● 正常")
        self.assertEqual(panel.reset_card.health_label.text(), "● 正常")
        panel.update_snapshot(StatusSnapshot(0x0AB5, 0x10, 0x11))
        self.assertEqual(panel.sync_card.health_label.text(), "● 异常")
        self.assertEqual(panel.reset_card.health_label.text(), "● 异常")

    def test_numeric_input_ignores_mouse_wheel(self) -> None:
        spin = NoWheelSpinBox()
        spin.setRange(0, 100)
        spin.setValue(50)
        event = QWheelEvent(
            QPointF(5, 5),
            QPointF(5, 5),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        spin.wheelEvent(event)
        self.assertEqual(spin.value(), 50)

    def test_light_and_dark_themes_apply_to_charts(self) -> None:
        window = MainWindow(self.profile)
        window._apply_theme("light", persist=False)
        self.assertEqual(window._theme, "light")
        self.assertEqual(window.theme_button.text(), "暗色主题")
        self.assertEqual(
            window.data_panel.plots[0].chart.backgroundBrush().color().name(),
            "#ffffff",
        )
        window._apply_theme("dark", persist=False)
        self.assertEqual(window._theme, "dark")
        self.assertEqual(window.theme_button.text(), "亮色主题")
        self.assertEqual(
            window.data_panel.plots[0].chart.backgroundBrush().color().name(),
            "#111a24",
        )
        window.close()
        self.app.processEvents()

    def test_language_switches_live_and_preserves_controls(self) -> None:
        window = MainWindow(self.profile)
        window._apply_language("en", persist=False)
        self.assertEqual(window.language_combo.currentIndex(), 1)
        self.assertEqual(window.tabs.tabText(0), "Live Status")
        self.assertEqual(window.tabs.tabText(1), "Live Acquisition")
        self.assertEqual(window.tabs.tabText(2), "Configuration")
        self.assertEqual(window.tabs.tabText(3), "Raw Access")
        self.assertEqual(window.connection_bar.connect_button.text(), "Connect")
        self.assertEqual(window.data_panel.start_button.text(), "Start Acquisition")
        self.assertEqual(window.register_panel.cfg_button.text(), "One-click CFG")

        window.register_panel.update_value(
            "coincidence_channel_a",
            3,
            b"\x03",
        )
        self.assertIn(
            "Current: 0x3",
            window.register_panel._current_labels["coincidence_channel_a"].text(),
        )
        window.data_panel.mark_active()
        self.assertEqual(window.data_panel.state_label.text(), "● Acquiring")
        leftovers = []
        for widget in (
            window.findChildren(QLabel)
            + window.findChildren(QAbstractButton)
            + window.findChildren(QComboBox)
        ):
            if widget.objectName() == "LanguageSelector":
                continue
            texts = (
                [widget.currentText()]
                if isinstance(widget, QComboBox)
                else [widget.text()]
            )
            leftovers.extend(
                text
                for text in texts
                if re.search(r"[\u4e00-\u9fff]", text or "")
            )
        for tabs in window.findChildren(QTabWidget):
            leftovers.extend(
                tabs.tabText(index)
                for index in range(tabs.count())
                if re.search(r"[\u4e00-\u9fff]", tabs.tabText(index))
            )
        leftovers.extend(
            widget.toolTip()
            for widget in window.findChildren(QWidget)
            if re.search(r"[\u4e00-\u9fff]", widget.toolTip() or "")
        )
        self.assertEqual(leftovers, [])

        window._apply_language("zh", persist=False)
        self.assertEqual(window.language_combo.currentIndex(), 0)
        self.assertEqual(window.tabs.tabText(0), "运行状态")
        self.assertEqual(window.tabs.tabText(2), "配置寄存器")
        self.assertEqual(window.connection_bar.connect_button.text(), "连接")
        window.close()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
