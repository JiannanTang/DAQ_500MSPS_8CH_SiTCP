from __future__ import annotations

import unittest

import numpy as np

from sitcp_host.core.framing import FrameParser, parse_frame, parse_header
from sitcp_host.errors import FrameProtocolError

SAMPLE_HEX = (
    "4000000220d00e04000000253e69065a"
    "20031fff1ffc20021ffc20021ffd1ffa1ffc20001fff1ffd1ffd20041ffd2000"
    "200020001ffe200220001ffd1ffe200020001ff81ffb1ffe2002200020001ffe1ffb"
    "1ffe1fff1ffe1ffe1ffc20041ffd1ffe20001fff20021ff620021ffd1ffe1ffb1ffe"
    "1ffc20051fff1ffc20001fff"
    "5000000220d00e04000000253e69065a"
    "20041ffa20002001200320081ffe20041ffd1ffe200120011ffe1ffc1ffd1ffd1ffc"
    "1ffc200120001ffc200120051ffd2002200420021ffe1ffd20001ff41ffe20022002"
    "1ffe2004200120021ffb200120041fff1fff1fff1ffd20011fff1ffd20051ffe1fff"
    "1ffc1ffb20021fff1ffd"
    "6000000220d00e04000000253e69065a"
    "1ffc2004200220002000200320031ffd20031ff81fff1ffc1fff2000200520012000"
    "1ffd1fff1ffc200120011ffe20031fff20011ffe2003200520012005200020041ffe"
    "200220032008200220012006200020021fff20031fff1ffd20011ffb200120012004"
    "20002000200020042000"
)


class FrameParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = bytes.fromhex(SAMPLE_HEX)

    def test_sample_contains_three_complete_frames(self) -> None:
        frames = FrameParser().feed(self.data)
        self.assertEqual(len(frames), 3)
        self.assertEqual([frame.channel for frame in frames], [4, 5, 6])
        self.assertTrue(all(frame.length == 14 for frame in frames))
        self.assertTrue(all(frame.sample_count == 56 for frame in frames))

    def test_header_fields_match_wire_format(self) -> None:
        header = parse_header(self.data[:16])
        self.assertEqual(header.channel, 4)
        self.assertEqual(header.trig_id, 2)
        self.assertEqual(header.threshold, 8400)
        self.assertEqual(header.length, 14)
        self.assertEqual(header.offset, 4)
        self.assertEqual(header.trigger_time, 0x000000253E69065A)
        self.assertEqual(header.frame_bytes, 128)

    def test_adc_samples_are_big_endian_14_bit_offset_binary(self) -> None:
        frame = parse_frame(self.data[:128])
        self.assertEqual(
            frame.raw_samples[:8].tolist(),
            [0x2003, 0x1FFF, 0x1FFC, 0x2002, 0x1FFC, 0x2002, 0x1FFD, 0x1FFA],
        )
        self.assertEqual(frame.samples[:4].tolist(), [3, -1, -4, 2])
        self.assertEqual(frame.samples.dtype, np.int16)
        self.assertFalse(frame.samples.flags.writeable)

    def test_incremental_tcp_chunks_preserve_frame_boundaries(self) -> None:
        parser = FrameParser()
        frames = []
        positions = (1, 3, 17, 65, 127, 128, 256, 383, 384)
        start = 0
        for end in positions:
            frames.extend(parser.feed(self.data[start:end]))
            start = end
        self.assertEqual([frame.channel for frame in frames], [4, 5, 6])
        self.assertEqual(parser.frames_decoded, 3)
        self.assertEqual(parser.buffered_bytes, 0)

    def test_scan_can_record_raw_bytes_without_decoding_all_frames(self) -> None:
        parser = FrameParser()
        batch = parser.scan(
            self.data,
            include_raw=True,
            decode_latest=True,
        )
        self.assertEqual(batch.frame_count, 3)
        self.assertEqual(batch.sample_count, 3 * 56)
        self.assertEqual(batch.channel_counts[4:7], (1, 1, 1))
        self.assertEqual(batch.raw_bytes, self.data)
        self.assertEqual(tuple(batch.latest_frames), (4, 5, 6))
        self.assertEqual(batch.frames, ())

    def test_scan_can_skip_adc_decoding_for_paused_plots(self) -> None:
        batch = FrameParser().scan(
            self.data,
            include_raw=True,
            decode_latest=False,
        )
        self.assertEqual(batch.frame_count, 3)
        self.assertEqual(batch.raw_bytes, self.data)
        self.assertEqual(batch.latest_frames, {})

    def test_reserved_bits_reject_unaligned_stream(self) -> None:
        malformed = bytearray(self.data[:128])
        malformed[4] |= 0x40
        with self.assertRaises(FrameProtocolError):
            FrameParser().feed(malformed)

    def test_nonzero_adc_upper_bits_are_rejected(self) -> None:
        malformed = bytearray(self.data[:128])
        malformed[16] = 0x60
        with self.assertRaises(FrameProtocolError):
            FrameParser().feed(malformed)


if __name__ == "__main__":
    unittest.main()
