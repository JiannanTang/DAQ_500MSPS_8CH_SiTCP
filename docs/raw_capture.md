# Raw ADC Capture

The real-time acquisition page separates TCP acquisition from raw capture.

## Controls

- `开始采集` opens the TCP data socket and updates the eight channel plots.
- `开始存盘` starts a raw capture without interrupting acquisition.
- `停止存盘` drains queued frames and finalizes the current capture.
- `停止采集` closes the TCP socket. An active capture is finalized first.

All eight channel plots remain visible regardless of the current
`trig_channel` setting. A plot updates only when a frame carrying that channel
ID is received.

## Files

Captures are written to `captures/` by default. The directory can be changed
from the UI and is remembered between application launches.

The file-name field accepts a user-defined base name. Entering `measurement`
creates `measurement.bin` and `measurement.json`; `.bin` and `.json` suffixes
are optional. An empty field keeps the timestamp/IP automatic naming behavior.
If the selected name already exists, `_001`, `_002`, and so on are appended
instead of overwriting an existing capture.

```text
captures/
├── 20261023_180000_192-168-10-16.bin
└── 20261023_180000_192-168-10-16.json
```

The `.bin` file is a concatenation of complete raw frames exactly as received.
The two 64-bit headers and ADC payload are not transformed. Capture starts at
a complete frame boundary.

The `.json` sidecar records:

- capture and source metadata;
- start/end time and duration;
- bytes and frames written;
- per-channel frame counts;
- frame/ADC format identifiers;
- a terminal error, if any.

Frames are queued to a bounded background writer. If disk storage temporarily
cannot keep up, the queue provides backpressure instead of silently dropping
frames.

Waveform rendering runs in the GUI thread and is batched at about 10 updates per
second. Raw file writes run in a separate writer thread, so normal plotting does
not perform disk I/O and does not directly serialize plotting with disk access.
At very high sustained data rates, chart preparation and rendering still
consume CPU and can compete with acquisition/parser work. The bounded queue
prevents silent frame loss, but if it remains full the acquisition rate may be
throttled by TCP backpressure until the disk catches up.

The `存盘时暂停波形` toggle suppresses ADC sample decoding and chart redraws
while recording is active. Lightweight frame-boundary scanning, counters, and
batched raw writes continue unchanged. Plots refresh again when new frames
arrive after recording stops.

## High-Speed Path

The acquisition worker does not decode every frame while raw recording is
active. It performs a lightweight header scan, returns exact complete-frame byte
ranges, and sends each receive batch to the background writer in one queue
operation. NumPy sample arrays are generated only for the newest visible frame
of each channel, and are skipped entirely when plots are paused.

The file is first written as `.bin.part`. A normal stop flushes, synchronizes,
closes, and renames it to `.bin`. On an I/O failure the partial file is kept and
the JSON metadata reports the failure.
