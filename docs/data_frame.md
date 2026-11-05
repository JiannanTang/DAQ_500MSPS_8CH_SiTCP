# FPGA ADC Data Frame

TCP 数据流由连续的 64 bit 字组成，每个数据帧包含两个 64 bit 包头和若干 64 bit ADC 数据字。多字节字段和 ADC 样本均按大端解释。

## First Header (64 bit)

| Bits | Width | Field | Description |
|---|---:|---|---|
| 63:60 | 4 | channel | ADC channel, 0-7 |
| 59:32 | 28 | trig_id | Trigger identifier |
| 31:30 | 2 | reserved | Must be `00` |
| 29:16 | 14 | threshold | Trigger threshold |
| 15:8 | 8 | length | Number of 64-bit ADC data words |
| 7:0 | 8 | offset | Trigger offset |

`length` does not include the two 64-bit headers. Four ADC samples are packed in every data word, so one frame contains `length * 4` samples.

## Second Header (64 bit)

The second header is the trigger time:

```text
trigger_time = uint64_be(bytes[8:16])
```

## ADC Payload

Every 64-bit payload word contains four unsigned 16-bit big-endian samples:

```text
byte 0..1 -> sample 0
byte 2..3 -> sample 1
byte 4..5 -> sample 2
byte 6..7 -> sample 3
```

The ADC is 14 bit. The upper two bits of each stored 16-bit word must be `00`.

```text
adc14 = stored_u16 & 0x3FFF
signed = adc14 - 8192
```

The captured data is offset-binary around midscale `8192`.

## Frame Size

```text
frame_bytes = 16 + length * 8
sample_count = length * 4
```

For the supplied capture:

```text
header0 = 0x4000000220D00E04
channel = 4
trig_id = 2
threshold = 8400
length = 14
offset = 4
trigger_time = 0x000000253E69065A
frame_bytes = 128
sample_count = 56
```

The first ADC word is `20031FFF1FFC2002`, which decodes to:

```text
raw14 = [8195, 8191, 8188, 8194]
signed = [3, -1, -4, 2]
```

## Stream Alignment

The current protocol has no magic word, frame checksum, or explicit synchronization marker. A parser can safely process a connection that begins at a frame boundary, but it cannot reliably recover after arbitrary byte loss or mid-frame connection.

The host parser validates:

- channel is in the range 0-7;
- the two reserved header bits are zero;
- the upper two bits of every ADC sample are zero;
- `length * 8` payload bytes are present before decoding.

If a future firmware version can produce ambiguous synchronization, add a fixed magic word and preferably a CRC.

