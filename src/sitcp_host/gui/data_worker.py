"""Background TCP acquisition worker for the FPGA ADC stream."""

from __future__ import annotations

import socket
import threading
import time
import queue
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from sitcp_host.core.framing import AdcFrame, FrameParser
from sitcp_host.core.storage import (
    RawFrameWriter,
    RecordingSummary,
)
from sitcp_host.errors import FrameProtocolError, StorageError
from sitcp_host.gui.i18n import tx
from sitcp_host.transport.tcp_data import TcpDataClient


@dataclass(frozen=True, slots=True)
class AcquisitionStats:
    bytes_total: int
    frames_total: int
    samples_total: int
    bytes_per_second: float
    frames_per_second: float
    samples_per_second: float
    channel_frames: tuple[int, ...]
    buffered_bytes: int
    recording_active: bool
    recording_bytes: int
    recording_path: str


@dataclass(frozen=True, slots=True)
class DataBatch:
    latest_frames: dict[int, AdcFrame]
    stats: AcquisitionStats


class TcpAcquisitionWorker(QThread):
    stream_started = Signal(str, int)
    batch_ready = Signal(object)
    stream_error = Signal(str)
    stream_finished = Signal()
    recording_started = Signal(object)
    recording_stopped = Signal(object)
    recording_error = Signal(str)

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self._stop_event = threading.Event()
        self._client: TcpDataClient | None = None
        self._socket_lock = threading.Lock()
        self._record_commands: queue.Queue[
            tuple[str, tuple[Path, str] | None]
        ] = queue.Queue()
        self._record_lock = threading.Lock()
        self._recorder: RawFrameWriter | None = None
        self._plot_pause_lock = threading.Lock()
        self._pause_plots_when_recording = False

    def stop(self) -> None:
        self.stop_recording()
        self._stop_event.set()
        with self._socket_lock:
            client = self._client
        if client is not None:
            client.close()

    def start_recording(
        self,
        directory: str | Path,
        filename: str = "",
    ) -> None:
        self._record_commands.put(("start", (Path(directory), filename)))

    def stop_recording(self) -> None:
        self._record_commands.put(("stop", None))

    def set_pause_plots_when_recording(self, paused: bool) -> None:
        with self._plot_pause_lock:
            self._pause_plots_when_recording = paused

    def _plots_should_decode(self, recording_active: bool) -> bool:
        with self._plot_pause_lock:
            paused = self._pause_plots_when_recording
        return not (recording_active and paused)

    def _current_recorder(self) -> RawFrameWriter | None:
        with self._record_lock:
            return self._recorder

    def _set_current_recorder(self, recorder: RawFrameWriter | None) -> None:
        with self._record_lock:
            self._recorder = recorder

    def _recording_fields(self) -> tuple[bool, int, str]:
        recorder = self._current_recorder()
        if recorder is None:
            return False, 0, ""
        info = recorder.info
        return (
            True,
            recorder.bytes_written,
            str(info.binary_path) if info is not None else "",
        )

    def run(self) -> None:
        client = TcpDataClient(self.host, self.port)
        with self._socket_lock:
            self._client = client

        parser = FrameParser()
        total_bytes = 0
        total_frames = 0
        total_samples = 0
        channel_frames = [0] * 8
        latest_frames: dict[int, AdcFrame] = {}
        last_emit = time.monotonic()
        last_bytes = 0
        last_frames = 0
        last_samples = 0
        stream_failure: str | None = None
        recorder: RawFrameWriter | None = None

        def service_recording_commands() -> None:
            nonlocal recorder
            while True:
                try:
                    command, payload = self._record_commands.get_nowait()
                except queue.Empty:
                    return

                if command == "start":
                    if recorder is not None:
                        self.recording_error.emit(
                            tx("已有存盘任务正在运行")
                        )
                        continue
                    if payload is None:
                        self.recording_error.emit(tx("存盘目录为空"))
                        continue
                    directory, filename = payload
                    try:
                        writer = RawFrameWriter(
                            directory,
                            source_host=self.host,
                            source_port=self.port,
                            filename=filename,
                        )
                        info = writer.start()
                    except (OSError, StorageError, ValueError) as exc:
                        self.recording_error.emit(str(exc))
                        continue
                    recorder = writer
                    self._set_current_recorder(writer)
                    self.recording_started.emit(info)
                elif command == "stop" and recorder is not None:
                    try:
                        summary = recorder.stop()
                    except StorageError as exc:
                        self.recording_error.emit(str(exc))
                    else:
                        self.recording_stopped.emit(summary)
                    recorder = None
                    self._set_current_recorder(None)

        def make_stats(elapsed: float) -> AcquisitionStats:
            recording_active, recording_bytes, recording_path = (
                self._recording_fields()
            )
            return AcquisitionStats(
                bytes_total=total_bytes,
                frames_total=total_frames,
                samples_total=total_samples,
                bytes_per_second=(total_bytes - last_bytes) / elapsed,
                frames_per_second=(total_frames - last_frames) / elapsed,
                samples_per_second=(total_samples - last_samples) / elapsed,
                channel_frames=tuple(channel_frames),
                buffered_bytes=parser.buffered_bytes,
                recording_active=recording_active,
                recording_bytes=recording_bytes,
                recording_path=recording_path,
            )

        try:
            client.connect()
            self.stream_started.emit(self.host, self.port)
            service_recording_commands()

            while not self._stop_event.is_set():
                service_recording_commands()
                timed_out = False
                try:
                    chunk = client.recv(65536)
                except socket.timeout:
                    chunk = b""
                    timed_out = True
                except OSError as exc:
                    if not self._stop_event.is_set():
                        stream_failure = f"TCP receive failed: {exc}"
                        self.stream_error.emit(stream_failure)
                    break

                if chunk:
                    total_bytes += len(chunk)
                    try:
                        scan = parser.scan(
                            chunk,
                            include_raw=recorder is not None,
                            decode_latest=self._plots_should_decode(
                                recorder is not None
                            ),
                        )
                    except FrameProtocolError as exc:
                        stream_failure = str(exc)
                        self.stream_error.emit(stream_failure)
                        break
                    total_frames += scan.frame_count
                    total_samples += scan.sample_count
                    for channel, count in enumerate(scan.channel_counts):
                        channel_frames[channel] += count
                    latest_frames.update(scan.latest_frames)
                    if (
                        recorder is not None
                        and scan.frame_count
                        and scan.raw_bytes
                    ):
                        try:
                            recorder.write_batch(
                                scan.raw_bytes,
                                frame_count=scan.frame_count,
                                channel_counts=scan.channel_counts,
                            )
                        except StorageError as exc:
                            self.recording_error.emit(str(exc))
                            try:
                                summary = recorder.stop(str(exc))
                            except StorageError as stop_exc:
                                self.recording_error.emit(str(stop_exc))
                            else:
                                self.recording_stopped.emit(summary)
                            recorder = None
                            self._set_current_recorder(None)

                now = time.monotonic()
                elapsed = now - last_emit
                if elapsed >= 0.1:
                    stats = make_stats(elapsed)
                    self.batch_ready.emit(DataBatch(dict(latest_frames), stats))
                    latest_frames.clear()
                    last_emit = now
                    last_bytes = total_bytes
                    last_frames = total_frames
                    last_samples = total_samples

                if not chunk:
                    if not timed_out:
                        break
                    if self._stop_event.wait(0.01):
                        break
        except OSError as exc:
            if not self._stop_event.is_set():
                stream_failure = f"cannot open data stream: {exc}"
                self.stream_error.emit(stream_failure)
        except Exception as exc:
            if not self._stop_event.is_set():
                stream_failure = f"unexpected acquisition error: {exc}"
                self.stream_error.emit(stream_failure)
        finally:
            service_recording_commands()
            if total_bytes > last_bytes or total_frames > last_frames:
                elapsed = max(time.monotonic() - last_emit, 1e-9)
                self.batch_ready.emit(
                    DataBatch(dict(latest_frames), make_stats(elapsed))
                )
            if recorder is not None:
                try:
                    summary: RecordingSummary = recorder.stop(stream_failure)
                except StorageError as exc:
                    self.recording_error.emit(str(exc))
                else:
                    self.recording_stopped.emit(summary)
                recorder = None
                self._set_current_recorder(None)
            client.close()
            with self._socket_lock:
                self._client = None
            self.stream_finished.emit()

