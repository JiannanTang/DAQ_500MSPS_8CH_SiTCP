"""Lossless raw-frame storage with a bounded background writer."""

from __future__ import annotations

import json
import os
import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sitcp_host.errors import StorageError

_INVALID_FILENAME_CHARS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def _normalize_capture_stem(filename: str | None) -> str | None:
    if filename is None:
        return None
    text = filename.strip()
    if not text:
        return None
    if Path(text).name != text or any(char in _INVALID_FILENAME_CHARS for char in text):
        raise StorageError("文件名不能包含路径分隔符或 Windows 非法字符")

    lowered = text.lower()
    for suffix in (".bin", ".json", ".part"):
        if lowered.endswith(suffix):
            text = text[: -len(suffix)]
            break
    text = text.rstrip(" .")
    if not text:
        raise StorageError("文件名不能为空")
    if len(text) > 120:
        raise StorageError("文件名过长，请控制在 120 个字符以内")
    if text.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        raise StorageError("该文件名是 Windows 保留名称")
    return text


@dataclass(frozen=True, slots=True)
class RecordingInfo:
    binary_path: Path
    metadata_path: Path
    started_at: datetime


@dataclass(frozen=True, slots=True)
class RecordingSummary:
    binary_path: Path
    metadata_path: Path
    bytes_written: int
    frames_written: int
    started_at: datetime
    ended_at: datetime
    duration_s: float
    channel_frames: tuple[int, ...]
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _WriteBatch:
    data: bytes
    frame_count: int
    channel_counts: tuple[int, ...]


class RawFrameWriter:
    """Write complete frame bytes through a bounded queue and worker thread."""

    def __init__(
        self,
        directory: str | Path,
        *,
        source_host: str,
        source_port: int,
        filename: str | None = None,
        queue_size: int = 512,
    ) -> None:
        self.directory = Path(directory).expanduser().resolve()
        self.source_host = source_host
        self.source_port = source_port
        self._requested_stem = _normalize_capture_stem(filename)
        self._queue: queue.Queue[_WriteBatch | None] = queue.Queue(
            maxsize=queue_size
        )
        self._thread: threading.Thread | None = None
        self._stream = None
        self._error: Exception | None = None
        self._bytes_written = 0
        self._frames_written = 0
        self._channel_frames = [0] * 8
        self._started_at = datetime.now().astimezone()
        self._ended_at: datetime | None = None
        self._paths: tuple[Path, Path, Path] | None = None
        self._closed = False

    @property
    def info(self) -> RecordingInfo | None:
        if self._paths is None:
            return None
        binary_path, metadata_path, _part_path = self._paths
        return RecordingInfo(binary_path, metadata_path, self._started_at)

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    @property
    def frames_written(self) -> int:
        return self._frames_written

    @property
    def error(self) -> Exception | None:
        return self._error

    def start(self) -> RecordingInfo:
        if self._thread is not None:
            raise StorageError("raw writer has already been started")

        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(f"cannot create capture directory: {exc}") from exc
        binary_path, metadata_path, part_path = self._allocate_paths()
        try:
            self._stream = part_path.open("wb", buffering=1024 * 1024)
        except OSError as exc:
            raise StorageError(f"cannot create capture file: {exc}") from exc

        self._paths = (binary_path, metadata_path, part_path)
        self._thread = threading.Thread(
            target=self._write_loop,
            name=f"raw-writer-{binary_path.name}",
            daemon=True,
        )
        self._thread.start()
        return RecordingInfo(binary_path, metadata_path, self._started_at)

    def write_frame(self, frame_bytes: bytes) -> None:
        payload = bytes(frame_bytes)
        if len(payload) < 16:
            raise StorageError("raw frame is shorter than its two 64-bit headers")
        channel = (payload[0] >> 4) & 0xF
        channel_counts = [0] * 8
        if channel < len(channel_counts):
            channel_counts[channel] = 1
        self.write_batch(
            payload,
            frame_count=1,
            channel_counts=tuple(channel_counts),
        )

    def write_batch(
        self,
        data: bytes | bytearray | memoryview,
        *,
        frame_count: int,
        channel_counts: tuple[int, ...],
    ) -> None:
        if self._closed:
            raise StorageError("raw writer is already closed")
        if self._thread is None:
            raise StorageError("raw writer has not been started")

        payload = bytes(data)
        if frame_count < 0 or len(channel_counts) != 8:
            raise StorageError("invalid raw write-batch accounting")
        if frame_count and not payload:
            raise StorageError("raw write batch declares frames without data")
        while True:
            if not self._thread.is_alive():
                self._raise_thread_error()
            try:
                self._queue.put(
                    _WriteBatch(payload, frame_count, tuple(channel_counts)),
                    timeout=0.1,
                )
                return
            except queue.Full:
                continue

    def stop(self, error: str | None = None) -> RecordingSummary:
        if self._paths is None or self._thread is None:
            raise StorageError("raw writer has not been started")
        if self._closed:
            raise StorageError("raw writer is already closed")

        while True:
            try:
                self._queue.put(None, timeout=0.1)
                break
            except queue.Full:
                if not self._thread.is_alive():
                    self._raise_thread_error()

        self._thread.join(timeout=10.0)
        if self._thread.is_alive():
            self._error = StorageError("raw writer did not stop within 10 seconds")

        binary_path, metadata_path, part_path = self._paths
        thread_error = self._error
        failure = error
        if thread_error is not None:
            failure = f"{error + ': ' if error else ''}{thread_error}"
        elif failure is None and self._stream is not None:
            try:
                self._stream.flush()
                os.fsync(self._stream.fileno())
            except OSError as exc:
                failure = f"cannot flush capture file: {exc}"

        if self._stream is not None:
            try:
                self._stream.close()
            except OSError as exc:
                failure = failure or f"cannot close capture file: {exc}"

        final_binary = binary_path
        if failure is None:
            try:
                part_path.replace(binary_path)
            except OSError as exc:
                failure = f"cannot finalize capture file: {exc}"
        else:
            final_binary = part_path

        self._ended_at = datetime.now().astimezone()
        summary = RecordingSummary(
            binary_path=final_binary,
            metadata_path=metadata_path,
            bytes_written=self._bytes_written,
            frames_written=self._frames_written,
            started_at=self._started_at,
            ended_at=self._ended_at,
            duration_s=max(
                (self._ended_at - self._started_at).total_seconds(),
                0.0,
            ),
            channel_frames=tuple(self._channel_frames),
            error=failure,
        )
        self._write_metadata(summary)
        self._closed = True
        return summary

    def _write_loop(self) -> None:
        if self._stream is None:
            self._error = StorageError("capture stream is not open")
            return
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                self._stream.write(item.data)
                self._bytes_written += len(item.data)
                self._frames_written += item.frame_count
                for channel, count in enumerate(item.channel_counts):
                    self._channel_frames[channel] += count
            self._stream.flush()
        except (OSError, ValueError) as exc:
            self._error = exc

    def _raise_thread_error(self) -> None:
        if self._error is not None:
            raise StorageError(f"raw writer failed: {self._error}") from self._error
        raise StorageError("raw writer stopped unexpectedly")

    def _allocate_paths(self) -> tuple[Path, Path, Path]:
        timestamp = self._started_at.strftime("%Y%m%d_%H%M%S")
        host = self.source_host.replace(".", "-").replace(":", "-")
        stem = self._requested_stem or f"{timestamp}_{host}"
        suffix = 0
        while True:
            candidate = stem if suffix == 0 else f"{stem}_{suffix:03d}"
            binary_path = self.directory / f"{candidate}.bin"
            metadata_path = self.directory / f"{candidate}.json"
            part_path = self.directory / f"{candidate}.bin.part"
            if not (
                binary_path.exists()
                or metadata_path.exists()
                or part_path.exists()
            ):
                return binary_path, metadata_path, part_path
            suffix += 1

    def _write_metadata(self, summary: RecordingSummary) -> None:
        metadata = {
            "schema_version": 1,
            "state": "complete" if summary.error is None else "error",
            "source": {
                "host": self.source_host,
                "tcp_port": self.source_port,
            },
            "timing": {
                "started_at": summary.started_at.isoformat(),
                "ended_at": summary.ended_at.isoformat(),
                "duration_s": summary.duration_s,
            },
            "storage": {
                "binary_file": summary.binary_path.name,
                "bytes_written": summary.bytes_written,
                "frames_written": summary.frames_written,
                "channel_frames": list(summary.channel_frames),
                "byte_order": "big-endian",
            },
            "frame_format": {
                "header_bytes": 16,
                "header_words": 2,
                "frame_bytes_formula": "16 + length * 8",
                "samples_per_word": 4,
                "sample_count_formula": "length * 4",
                "adc_bits": 14,
                "adc_encoding": "offset-binary",
                "adc_center": 8192,
            },
            "error": summary.error,
        }
        part_path = summary.metadata_path.with_suffix(".json.part")
        try:
            with part_path.open("w", encoding="utf-8") as stream:
                json.dump(metadata, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            part_path.replace(summary.metadata_path)
        except OSError:
            pass

