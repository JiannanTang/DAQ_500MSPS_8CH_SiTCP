"""Incremental parser for the FPGA 64-bit ADC data stream."""

from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from sitcp_host.errors import FrameProtocolError

HEADER_SIZE = 16
ADC_CHANNEL_COUNT = 8
ADC_SAMPLE_BITS = 14
ADC_OFFSET_BINARY_CENTER = 1 << (ADC_SAMPLE_BITS - 1)
ADC_RAW_MASK = (1 << ADC_SAMPLE_BITS) - 1
_HEADER_STRUCT = struct.Struct(">QQ")


@dataclass(frozen=True, slots=True)
class FrameHeader:
    channel: int
    trig_id: int
    threshold: int
    length: int
    offset: int
    trigger_time: int
    data_bytes: int
    frame_bytes: int


@dataclass(frozen=True, slots=True)
class AdcFrame:
    channel: int
    trig_id: int
    threshold: int
    length: int
    offset: int
    trigger_time: int
    raw_samples: NDArray[np.uint16]
    samples: NDArray[np.int16]
    wire_bytes: bytes

    @property
    def sample_count(self) -> int:
        return int(self.raw_samples.size)


@dataclass(frozen=True, slots=True)
class FrameScanBatch:
    frame_count: int
    sample_count: int
    channel_counts: tuple[int, ...]
    latest_frames: dict[int, AdcFrame]
    raw_bytes: bytes
    frames: tuple[AdcFrame, ...] = ()


def _parse_header_from_buffer(
    data: bytearray | bytes | memoryview,
    offset: int,
) -> FrameHeader:
    try:
        header0, trigger_time = _HEADER_STRUCT.unpack_from(data, offset)
    except struct.error as exc:
        raise FrameProtocolError(
            "data frame is shorter than two 64-bit headers"
        ) from exc

    channel = (header0 >> 60) & 0xF
    trig_id = (header0 >> 32) & 0x0FFFFFFF
    reserved = (header0 >> 30) & 0x3
    threshold = (header0 >> 16) & 0x3FFF
    length = (header0 >> 8) & 0xFF
    frame_offset = header0 & 0xFF

    if channel >= ADC_CHANNEL_COUNT:
        raise FrameProtocolError(f"invalid ADC channel id {channel}")
    if reserved != 0:
        raise FrameProtocolError(
            f"invalid reserved header bits 0b{reserved:02b}; stream may be unaligned"
        )

    data_bytes = length * 8
    return FrameHeader(
        channel=channel,
        trig_id=trig_id,
        threshold=threshold,
        length=length,
        offset=frame_offset,
        trigger_time=trigger_time,
        data_bytes=data_bytes,
        frame_bytes=HEADER_SIZE + data_bytes,
    )


def parse_header(data: bytes | bytearray | memoryview) -> FrameHeader:
    """Parse one 16-byte frame header and validate its fixed fields."""

    return _parse_header_from_buffer(data, 0)


def _decode_frame(
    data: bytes | bytearray | memoryview,
    offset: int,
    header: FrameHeader,
) -> AdcFrame:
    payload_start = offset + HEADER_SIZE
    frame_end = offset + header.frame_bytes
    payload = memoryview(data)[payload_start:frame_end]
    try:
        packed = np.frombuffer(payload, dtype=">u2")
        if packed.size != header.length * 4:
            raise FrameProtocolError(
                f"ADC payload expected {header.length * 4} samples, "
                f"decoded {packed.size}"
            )
        if np.any(packed & 0xC000):
            raise FrameProtocolError(
                "ADC payload has non-zero upper two bits; "
                "frame is malformed or unaligned"
            )

        raw_samples = (packed & ADC_RAW_MASK).astype(np.uint16, copy=True)
        raw_samples.setflags(write=False)
        samples = (
            raw_samples.astype(np.int16) - ADC_OFFSET_BINARY_CENTER
        ).astype(np.int16, copy=False)
        samples.setflags(write=False)
    finally:
        payload.release()

    return AdcFrame(
        channel=header.channel,
        trig_id=header.trig_id,
        threshold=header.threshold,
        length=header.length,
        offset=header.offset,
        trigger_time=header.trigger_time,
        raw_samples=raw_samples,
        samples=samples,
        wire_bytes=bytes(data[offset:frame_end]),
    )


def parse_frame(data: bytes | bytearray | memoryview) -> AdcFrame:
    """Parse one complete frame from exactly its header and ADC payload."""

    raw = memoryview(data)
    try:
        header = parse_header(raw)
        if len(raw) != header.frame_bytes:
            raise FrameProtocolError(
                f"frame length mismatch: header declares {header.frame_bytes} bytes, "
                f"received {len(raw)}"
            )
        return _decode_frame(raw, 0, header)
    finally:
        raw.release()


class FrameParser:
    """Find complete frames in an incremental TCP byte stream.

    The hardware protocol in the supplied sample has no magic word or checksum.
    This parser therefore starts at the first byte supplied after reset. If the
    stream becomes unaligned it raises FrameProtocolError instead of silently
    locking onto an ADC payload word that happens to look like a header.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.frames_decoded = 0
        self.bytes_consumed = 0

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()

    def scan(
        self,
        data: bytes | bytearray | memoryview,
        *,
        include_raw: bool = False,
        decode_latest: bool = True,
        decode_all: bool = False,
    ) -> FrameScanBatch:
        """Scan complete frames with one buffer compaction per input batch.

        ``include_raw`` returns the exact complete-frame bytes consumed from the
        stream. ``decode_latest`` keeps only the newest decoded frame for each
        channel, which is all that waveform rendering needs.
        """

        if data:
            self._buffer.extend(data)

        buffer = self._buffer
        cursor = 0
        frame_count = 0
        sample_count = 0
        channel_counts = [0] * ADC_CHANNEL_COUNT
        latest_spans: dict[int, tuple[int, FrameHeader]] = {}
        decoded_frames: list[AdcFrame] = []

        try:
            while len(buffer) - cursor >= HEADER_SIZE:
                try:
                    header = _parse_header_from_buffer(buffer, cursor)
                except FrameProtocolError:
                    buffer.clear()
                    raise

                frame_end = cursor + header.frame_bytes
                if frame_end > len(buffer):
                    break

                frame_count += 1
                sample_count += header.length * 4
                channel_counts[header.channel] += 1

                if decode_all:
                    decoded_frames.append(_decode_frame(buffer, cursor, header))
                elif decode_latest:
                    latest_spans[header.channel] = (cursor, header)
                cursor = frame_end
        except FrameProtocolError:
            raise

        latest_frames = {
            channel: _decode_frame(buffer, offset, header)
            for channel, (offset, header) in latest_spans.items()
        }

        consumed = memoryview(buffer)[:cursor] if include_raw else None
        try:
            raw_bytes = bytes(consumed) if consumed is not None else b""
        finally:
            if consumed is not None:
                consumed.release()

        if cursor:
            del buffer[:cursor]
            self.frames_decoded += frame_count
            self.bytes_consumed += cursor

        return FrameScanBatch(
            frame_count=frame_count,
            sample_count=sample_count,
            channel_counts=tuple(channel_counts),
            latest_frames=latest_frames,
            raw_bytes=raw_bytes,
            frames=tuple(decoded_frames),
        )

    def feed(self, data: bytes | bytearray | memoryview) -> list[AdcFrame]:
        return list(
            self.scan(
                data,
                include_raw=True,
                decode_latest=False,
                decode_all=True,
            ).frames
        )
