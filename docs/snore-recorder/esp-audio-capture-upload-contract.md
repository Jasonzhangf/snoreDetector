# ESP Audio Capture, Threshold, And Upload Contract

## Purpose

Define the ESP firmware-side MVP contract for microphone capture, local threshold detection, pre-roll, segment start/stop, and upload to the Mac HTTP storage service.

This document is a design contract only. It does not implement firmware code.

## Source Evidence

- Target board config uses `AUDIO_INPUT_SAMPLE_RATE 16000` and I2S mic pins in `main/boards/zhengchen-1.54tft-wifi/config.h`.
- Target board constructs `NoAudioCodecSimplex` for mic/speaker in `main/boards/zhengchen-1.54tft-wifi/zhengchen-1.54tft-wifi.cc`.
- `AudioService::ReadAudioData()` can return 16 kHz PCM samples and updates input activity in `main/audio/audio_service.cc`.
- Current chat pipeline encodes OPUS, but the recorder MVP must upload raw PCM per `docs/snore-recorder/mac-http-storage-contract.md`.
- Existing AFE VAD is speech-oriented; snore trigger must use RMS/peak dBFS as primary signal.

## MVP Audio Format

- Capture/output to uploader: raw PCM samples.
- Sample rate: `16000` Hz.
- Channels: `1` mono.
- Sample format: signed little-endian 16-bit PCM, `s16le`.
- Frame duration for recorder logic: `20 ms`.
- Samples per frame: `320`.
- Bytes per frame: `640`.

Rationale:

- `20 ms` keeps display animation responsive and threshold latency low.
- HTTP upload may batch multiple frames to reduce request overhead.

## Capture Ownership

The recorder app should own a simple PCM capture path for MVP.

Rules:

- Do not route recorder audio through OPUS send queues.
- Do not build JSON per audio frame.
- Do not use chat protocol queues as the long-term recorder path.
- Use existing codec/I2S primitives where possible, but keep recorder state separate from XiaoZhi chat state.
- Avoid enabling speaker output during monitoring unless explicitly needed.

Preferred future L2 shape:

```text
RecorderApp
  -> RecorderAudioInput
    -> AudioCodec/AudioService PCM read
  -> LevelDetector
  -> PreRollBuffer
  -> SegmentUploader
  -> RecorderDisplayController
```

## Level Calculation

For each `20 ms` PCM frame:

```text
rms = sqrt(sum(sample * sample) / sample_count)
peak = max(abs(sample))
rms_dbfs = 20 * log10(max(rms, 1) / 32768.0)
peak_dbfs = 20 * log10(max(peak, 1) / 32768.0)
```

Rules:

- Use dBFS only. Do not label it physical dB SPL.
- Clamp silence floor to avoid `log10(0)`.
- Use `int64_t` accumulation for `sample * sample` sum.
- Use RMS dBFS for trigger decisions.
- Use peak dBFS for display and metadata only.

## Sensitivity Presets

Initial threshold presets:

```text
SUPER:  -50 dBFS
HIGH:   -45 dBFS
MEDIUM: -40 dBFS
LOW:    -35 dBFS
```

Rules:

- Volume- cycles presets in this order: `SUPER -> HIGH -> MEDIUM -> LOW -> SUPER`.
- Current preset must be shown on the screen when changed.
- Preset may be stored in NVS later, but persistence is not required for the first firmware slice unless explicitly scoped.

## Trigger State Machine

Recorder states inside `MONITORING`:

```text
QUIET
  -> CANDIDATE_SOUND   rms_dbfs >= threshold
  -> RECORDING         sustained sound reached start hold
```

Constants:

```text
frame_ms = 20
start_hold_ms = 500
stop_silence_ms = 3000
pre_roll_ms = 1500
max_segment_ms = 10 * 60 * 1000
```

Start condition:

- `rms_dbfs >= threshold_dbfs` for at least `start_hold_ms`.
- Include pre-roll frames in the uploaded segment.

Stop condition:

- After recording starts, stop when `rms_dbfs < threshold_dbfs` continuously for `stop_silence_ms`.
- Also stop when volume+ is pressed during recording.
- Also stop at `max_segment_ms` to avoid one unbounded file.

Abort/failure condition:

- If Mac `/start` fails, do not enter `RECORDING`; show upload/server error.
- If `/chunk` fails during recording, stop local segment and mark display error. Mac is responsible for playable partial if it received data.
- If `/stop` fails, show error. Do not claim saved.

## Pre-Roll Buffer

Pre-roll stores recent PCM frames while monitoring.

Required size:

```text
pre_roll_ms = 1500
frame_ms = 20
frames = 75
bytes = 75 * 640 = 48000 bytes
```

Rules:

- Use a fixed-size ring buffer.
- No heap allocation per frame.
- On segment start, upload frames from oldest to newest before live frames.
- Pre-roll frames use `offset_ms` starting at `0`; live frames continue after pre-roll.

## Upload Batching

ESP may batch PCM frames into one HTTP chunk request.

Recommended MVP batch:

```text
batch_ms = 100
frames_per_batch = 5
payload_bytes = 3200
```

Rules:

- Each upload request maps to a sequential `X-Seq`.
- `X-Offset-Ms` is offset from the segment audio start, including pre-roll.
- `X-Rms-Dbfs` and `X-Peak-Dbfs` should summarize the batch, not every frame.
- Do not silently drop a failed batch. Stop recording and surface error.

## HTTP Call Sequence

On start:

```text
POST /api/segments/start
  JSON metadata with device_id, start_time, timezone, sample format, threshold, pre_roll_ms
```

On each batch:

```text
POST /api/segments/{segment_id}/chunk
  headers: X-Seq, X-Offset-Ms, X-Rms-Dbfs, X-Peak-Dbfs
  body: raw PCM bytes
```

On stop:

```text
POST /api/segments/{segment_id}/stop
  JSON with end_time, duration_ms, close_reason
```

Close reasons:

```text
silence_timeout
button_stop
max_duration
upload_error
wifi_lost
```

## Time Handling

- Normal recording requires `time_synced=true` from the system time module.
- `start_time` and `end_time` are RFC3339 UTC strings.
- Segment duration and chunk offsets use monotonic time from `esp_timer`.
- If future scope allows recording without synced wall time, metadata must explicitly set `time_synced=false`; MVP should block normal recording until time sync succeeds.

## Display Signals

Display updates should be derived from low-cost level stats:

- `QUIET`: show standby/monitoring and current time.
- `CANDIDATE_SOUND`: animate level bars but do not show saved/recording yet.
- `RECORDING`: show recording state, elapsed time, and upload indicator.
- threshold change: show preset and dBFS value on bottom area.
- upload failure: show clear error and do not claim saved.

Rules:

- Display animation may update at `10 Hz`, not every `20 ms` frame.
- Do not allocate new LVGL objects per frame.
- Update existing bars/labels only.

## Resource Limits

- No local persistent audio storage in MVP.
- Fixed pre-roll buffer target: about `48 KB`.
- HTTP batch buffer target: about `3.2 KB` plus request overhead.
- Avoid per-frame `std::vector` allocation in final implementation.
- Avoid per-frame `std::string` and JSON serialization.
- Keep all queues bounded.

## Readiness Findings

- Existing `AudioService::ReadAudioData()` currently uses `std::vector<int16_t>` and may allocate per read; L2 should either add a fixed-buffer recorder read path or carefully reuse one vector capacity.
- Existing `NoAudioCodec::Read()` allocates a temporary `std::vector<int32_t>` per read; this is acceptable for current chat design but should be reviewed before final recorder hot path.
- Existing AFE VAD is useful as an optional signal but should not own snore triggering.

## Verification Gates For Future L2

Implementation is not complete until:

- Synthetic PCM frame test verifies RMS/peak dBFS calculations.
- Threshold state machine test covers start hold, silence stop, button stop, and max duration.
- Pre-roll ordering test proves oldest-to-newest upload before live audio.
- Upload sequence test verifies `/start -> chunks -> /stop` and no per-chunk files.
- Hardware test shows live mic animation, threshold-triggered recording, Mac WAV playback, and correct metadata time.

