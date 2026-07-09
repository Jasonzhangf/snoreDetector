# L2 Implementation Slice Plan

## Purpose

Define the first implementation slices for the snore/audio recorder MVP before changing firmware or server code.

This document is a planning contract only. It does not implement firmware, server, build config, or flashing behavior.

## L2 Entry Rule

L2 starts only after explicit Jason approval to leave `L1 report-only`.

Before L2 coding:

- Update loop mode/constraints from report-only to implementation for the approved slice.
- Keep each slice small enough to verify independently.
- Do not change firmware and Mac server in the same first slice unless the verification gate requires it.
- Do not claim end-to-end success until ESP uploads audio, Mac stores one playable WAV, metadata has valid RFC3339 time, and browser playback works.

## Slice Order

### Slice 1: Mac HTTP Storage And Playback

Owner surface:

- New local Mac server files under a small explicit path, for example `tools/snore_server/`.
- Contract truth: `docs/snore-recorder/mac-http-storage-contract.md`.

Scope:

- Implement `POST /api/segments/start`.
- Implement `POST /api/segments/{segment_id}/chunk`.
- Implement `POST /api/segments/{segment_id}/stop`.
- Implement `GET /`, `GET /api/segments`, `GET /api/segments/{segment_id}`, and `GET /audio/{segment_id}.wav`.
- Write one WAV and one JSON metadata file per segment.
- Provide a tiny synthetic PCM client/test fixture that creates a playable segment without ESP hardware.

Verification gate:

- Synthetic PCM upload creates exactly one `.wav` and one `.json` for a segment.
- Browser page lists the segment and can play the WAV.
- WAV header duration matches uploaded PCM byte count.
- Out-of-order chunk is rejected with `409` and is not silently reordered.
- Empty segment stop does not produce a fake successful recording.

Reason to start here:

- It closes the storage/playback truth with no firmware risk.
- It gives ESP implementation a real HTTP target instead of a speculative API.

### Slice 2: Recorder Core Pure Logic

Owner surface:

- New compact firmware module, for example `main/recorder/`.
- Contract truth: `docs/snore-recorder/esp-audio-capture-upload-contract.md`.

Scope:

- `LevelDetector`: RMS/peak dBFS from `int16_t` PCM frames.
- `TriggerState`: quiet/candidate/recording transitions.
- `PreRollBuffer`: fixed 75-frame ring buffer, oldest-to-newest drain.
- No Wi-Fi, no LVGL, no HTTP client in this slice.

Verification gate:

- Synthetic frame tests verify RMS/peak dBFS.
- Start hold requires 500 ms over threshold.
- Silence stop requires 3000 ms below threshold.
- Button stop and max duration close reasons are represented.
- Pre-roll drain order is oldest-to-newest.

Reason to make this second:

- It keeps hot-path math and state transitions testable before binding to I2S, network, or display.

### Slice 3: Recorder Time Sync Owner

Owner surface:

- New small firmware owner, for example `RecorderTimeSync`.
- Integration point: `main/application.cc` around `Application::HandleNetworkConnectedEvent()`.
- Contract truth: `docs/snore-recorder/esp-time-sync-contract.md`.

Scope:

- Start SNTP only after Wi-Fi connected.
- Block standby/monitoring until `time_synced=true` and UTC year is at least 2025.
- Format RFC3339 UTC with milliseconds.
- Format filesystem-safe `YYYYMMDDTHHMMSSZ` timestamps.
- Use `esp_timer` for segment duration and offsets.

Verification gate:

- Host/unit formatting tests pass for RFC3339 and filename timestamps.
- Device log shows Wi-Fi connected -> time sync -> `time_synced=true` -> standby.
- Time sync failure blocks recording and shows a visible error.
- No dependency on XiaoZhi OTA `server_time`.

### Slice 4: Recorder Display Controller

Owner surface:

- Display binding through existing `Display`, `LvglDisplay`, and `LcdDisplay` surfaces.
- Contract truth: `docs/snore-recorder/esp-display-layout-contract.md`.

Scope:

- Create fixed LVGL objects once.
- Update status, clock, threshold text, recording elapsed, and 8 audio bars in place.
- Cap audio animation at 10 Hz and clock/elapsed at 1 Hz.
- Do not use chat bubbles or GIF assets.

Verification gate:

- Firmware build succeeds for `zhengchen-1.54tft-wifi`.
- Hardware screen shows time sync, standby, monitoring, recording, threshold change, and error states.
- No dynamic LVGL object creation per audio frame.

### Slice 5: Firmware Integration And Upload

Owner surface:

- Recorder application owner replacing XiaoZhi chat app behavior for this board/scope.
- Button owner: `main/boards/zhengchen-1.54tft-wifi/zhengchen-1.54tft-wifi.cc`.
- Audio boundary: `main/audio/audio_service.*` or a fixed-buffer codec path.
- Network boundary: ESP HTTP client to Mac server API.

Scope:

- Volume+ toggles `STANDBY <-> MONITORING`; in recording it closes the segment cleanly.
- Volume- cycles threshold presets.
- Capture 20 ms PCM frames.
- Batch 100 ms PCM chunks.
- Call Mac `/start -> /chunk -> /stop`.
- Surface upload/time/audio errors on display.

Verification gate:

- Firmware builds for `zhengchen-1.54tft-wifi`.
- Device mic level drives display bars.
- Threshold crossing starts a segment.
- Silence timeout stops the segment.
- Mac stores one playable WAV and one JSON metadata file.
- Browser playback works for the actual ESP recording.

## Known Owner Bindings

Current source evidence:

- Network event source: `main/boards/common/wifi_board.cc` emits `NetworkEvent::Connected`.
- Application network hook: `main/application.cc` has `Application::HandleNetworkConnectedEvent()`.
- Board buttons: `main/boards/zhengchen-1.54tft-wifi/zhengchen-1.54tft-wifi.cc` owns boot, volume up, and volume down callbacks.
- Button GPIOs: `main/boards/zhengchen-1.54tft-wifi/config.h` defines boot, volume up, and volume down pins.
- PCM read boundary: `main/audio/audio_service.h` declares `AudioService::ReadAudioData(...)`.
- Current read implementation: `main/audio/audio_service.cc` reads PCM through the codec path.
- Display status surface: `main/display/lvgl_display/lvgl_display.cc` implements `LvglDisplay::SetStatus(...)`.
- LCD emotion/UI surface: `main/display/lcd_display.cc` implements `LcdDisplay::SetEmotion(...)` and the LCD UI path.

## Forbidden In L2 MVP

- No WebDAV/cloud/auth work before local Mac HTTP path is closed.
- No local persistent audio storage on ESP.
- No OPUS/chat protocol path for recorder audio upload.
- No per-frame JSON or string construction in audio hot path.
- No hidden fallback time source.
- No silent retry/reorder that changes upload truth.
- No user-facing chunk files.
- No display claim of saved/complete before Mac finalizes WAV or marks playable partial.

## Minimal Done Definition

Implementation is only MVP-complete when all are true:

- ESP has Wi-Fi and valid SNTP time before monitoring.
- Volume+ starts/stops monitoring; volume- changes threshold.
- Audio threshold creates recording segments.
- Mac receives ESP PCM and stores one playable WAV plus one JSON metadata file per segment.
- Browser playback works from `GET /`.
- Metadata includes RFC3339 UTC start/end time, monotonic duration, threshold, max/avg dBFS, and upload status.
