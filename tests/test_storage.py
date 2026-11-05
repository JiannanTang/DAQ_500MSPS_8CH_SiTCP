from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sitcp_host.core.storage import RawFrameWriter


def make_frame(channel: int = 3) -> bytes:
    header0 = (
        (channel << 60)
        | (12 << 32)
        | (5000 << 16)
        | (2 << 8)
        | 1
    )
    trigger_time = 0x0102030405060708
    samples = (0x2000, 0x2001, 0x1FFF, 0x2002, 0x1FFE, 0x2003, 0x2004, 0x1FFD)
    return (
        header0.to_bytes(8, "big")
        + trigger_time.to_bytes(8, "big")
        + b"".join(sample.to_bytes(2, "big") for sample in samples)
    )


class RawFrameWriterTests(unittest.TestCase):
    def test_writes_complete_frames_and_metadata(self) -> None:
        frame = make_frame()
        with tempfile.TemporaryDirectory() as directory:
            writer = RawFrameWriter(
                directory,
                source_host="192.168.10.16",
                source_port=24,
            )
            info = writer.start()
            writer.write_frame(frame)
            writer.write_frame(frame)
            summary = writer.stop()

            self.assertIsNone(summary.error)
            self.assertEqual(summary.bytes_written, len(frame) * 2)
            self.assertEqual(summary.frames_written, 2)
            self.assertEqual(summary.binary_path.read_bytes(), frame * 2)
            self.assertFalse(summary.binary_path.with_suffix(".bin.part").exists())
            self.assertEqual(info.binary_path, summary.binary_path)

            metadata = json.loads(summary.metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["state"], "complete")
            self.assertEqual(metadata["source"]["host"], "192.168.10.16")
            self.assertEqual(metadata["storage"]["frames_written"], 2)
            self.assertEqual(metadata["storage"]["bytes_written"], len(frame) * 2)
            self.assertEqual(metadata["storage"]["channel_frames"], [0, 0, 0, 2, 0, 0, 0, 0])

    def test_second_capture_gets_a_unique_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for _index in range(2):
                writer = RawFrameWriter(
                    Path(directory),
                    source_host="127.0.0.1",
                    source_port=24,
                )
                writer.start()
                paths.append(writer.stop().binary_path)
            self.assertNotEqual(paths[0], paths[1])

    def test_user_filename_gets_standard_extensions(self) -> None:
        frame = make_frame()
        with tempfile.TemporaryDirectory() as directory:
            writer = RawFrameWriter(
                directory,
                source_host="127.0.0.1",
                source_port=24,
                filename="my_run.bin",
            )
            writer.start()
            writer.write_frame(frame)
            summary = writer.stop()

            self.assertEqual(summary.binary_path.name, "my_run.bin")
            self.assertEqual(summary.metadata_path.name, "my_run.json")
            self.assertEqual(summary.binary_path.read_bytes(), frame)


if __name__ == "__main__":
    unittest.main()

