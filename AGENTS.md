# Project AGENTS.md

## Project Identity

- This repo is being adapted from XiaoZhi ESP32 into a snore/audio event recorder.
- Target board is `zhengchen-1.54tft-wifi` on ESP32-S3 Wi-Fi.
- This is MCU firmware. RAM, flash, task stack, SPI display bandwidth, Wi-Fi stability, and CPU time are constrained.

## MVP Scope

- Keep board hardware support, Wi-Fi provisioning, buttons, audio input, LCD display, power management, and local flashing workflow.
- Replace the XiaoZhi chat application with a compact audio monitor/recorder application.
- Mac runs a local HTTP server for MVP storage and playback.
- ESP connects to Wi-Fi, syncs internet time, enters standby, then starts/stops monitoring by button.
- One detected audio event is one recording segment.
- Mac storage truth is one playable `.wav` file plus one `.json` metadata file per segment.
- Network transport may send small chunks, but Mac must append them into one segment file. Do not store chunk files as user-facing data.

## Device State Machine

```text
BOOT
  -> PROVISIONING       no Wi-Fi / provisioning active
  -> WIFI_CONNECTING    Wi-Fi connecting
  -> TIME_SYNCING       SNTP time sync
  -> STANDBY            time valid, app idle
  -> MONITORING         volume+ started app, mic + animation active
  -> RECORDING          threshold exceeded, uploading PCM to Mac HTTP
  -> ERROR              Wi-Fi / time / HTTP / audio failure
```

## Controls

- `BOOT` button keeps provisioning behavior unless explicitly changed.
- In `STANDBY`, volume+ toggles application start/stop: `STANDBY <-> MONITORING`.
- In `RECORDING`, volume+ stops the current segment cleanly before returning to standby/monitoring.
- Volume- cycles sensitivity threshold presets and shows the selected threshold on the bottom of the screen.
- Do not keep the old volume-control behavior in the recorder application mode unless explicitly required.

## Time Contract

- After Wi-Fi connects, firmware must sync time before normal recording.
- Use SNTP or another explicit network time source. Do not depend on XiaoZhi OTA server time.
- Segment time format is RFC 3339 / ISO 8601.
- Store canonical segment times in UTC, for example `2026-07-09T18:13:44.123Z`.
- File names must be filesystem-safe, for example `20260709T181344Z_esp-3cdc75fc81e4.wav`.
- Segment metadata must include at least `segment_id`, `device_id`, `start_time`, `end_time`, `timezone`, `duration_ms`, `time_synced`, `threshold_dbfs`, `max_dbfs`, `avg_dbfs`, `sample_rate`, `format`, and `upload_status`.
- For per-chunk timing, use `offset_ms` from segment start, not repeated wall-clock timestamps.
- Use monotonic time (`esp_timer`) for durations and chunk offsets to avoid wall-clock jumps after sync.

## Audio Contract

- MVP upload format is PCM `16 kHz`, `16-bit`, mono.
- Mac HTTP server writes playable WAV files directly from PCM chunks.
- ESP may keep a small RAM ring buffer for 1-2 seconds of pre-roll.
- Do not add local persistent audio storage on ESP for MVP.
- Threshold detection should use PCM RMS/peak converted to relative dBFS.
- Do not call dBFS real physical dB SPL unless a microphone calibration flow exists.
- Snore detection must not rely only on speech VAD; snoring may not be classified as speech.
- Initial threshold presets:
  - `-50 dBFS` super sensitive
  - `-45 dBFS` high
  - `-40 dBFS` medium
  - `-35 dBFS` low

## Mac HTTP Contract

- `POST /api/segments/start` creates a segment and opens one WAV file with a provisional header.
- `POST /api/segments/{segment_id}/chunk` appends PCM bytes to the open WAV file and updates in-memory stats.
- `POST /api/segments/{segment_id}/stop` finalizes the WAV header, closes the file, writes metadata, and updates the index.
- `GET /` serves a playback page.
- `GET /api/segments` returns the segment list.
- `GET /audio/{segment_id}.wav` returns a playable WAV file.
- If a recording is interrupted, finalize the WAV as playable and mark metadata `status=partial` / `upload_status=partial`.
- Never report a segment as saved unless the WAV is closed/finalized or explicitly marked partial.

## Display Contract

- Target screen is 240x240 ST7789 SPI LCD.
- Current LCD path is `ZHENGCHEN_LcdDisplay -> SpiLcdDisplay -> LcdDisplay`.
- Show clear status text: provisioning, connecting, syncing time, standby, monitoring, recording, upload failure.
- Show current local display time after time sync.
- Show real-time audio animation based on RMS/peak, independent from upload threshold.
- Show threshold changes on the bottom area after volume- presses.
- Keep UI simple; avoid heavy images, GIFs, chat bubbles, or unnecessary animation layers for the recorder app.

## Firmware Coding Rules

- Prefer small, direct C++ classes with explicit ownership.
- Avoid generic frameworks, unnecessary abstractions, dynamic plugin systems, large template utilities, and duplicate DTOs.
- Minimize heap allocation in audio hot paths; prefer fixed buffers, bounded queues, and compile-time constants.
- Avoid `std::string` churn and JSON construction in per-audio-frame paths.
- Audio capture, threshold calculation, display animation, and upload must have bounded work per tick.
- No fallback paths that silently change protocol, format, time source, or upload status.
- Errors must be surfaced to display/log and metadata where applicable.
- Do not keep dead XiaoZhi chat logic in the recorder app. If application behavior is replaced, remove unused old app paths after dependency checks.
- Keep code size and RAM usage visible when adding features. Build output size and task stack risks matter.

## Verification Gates

- Firmware must build for `zhengchen-1.54tft-wifi` before claiming implementation complete.
- Mac HTTP server must be tested with a real WAV segment that plays in a browser before claiming playback complete.
- End-to-end completion requires ESP sending audio to Mac, Mac saving one playable WAV, metadata containing RFC3339 start time, and browser playback working.
- If hardware verification is not run, report the exact missing gate and do not claim closed-loop success.

## L1 Loop Governance

- Project loop: `snore-recorder-l1-design-review`.
- L1 is report-only. It may inspect source, specs, and loop files, then report findings.
- L1 must not edit firmware code, Mac server code, build config, SDK config, flashing scripts, or generated artifacts.
- L1 required files: `LOOP.md`, `STATE.md`, `loop-constraints.md`, `loop-budget.md`, `loop-run-log.md`.
- Before each L1 run: read loop files, confirm `kill_switch: inactive`, check budget, inspect one focus area, append one run-log entry.
- Escalate to Jason before L2 for any implementation, build/config, flashing, server, auth, WebDAV, or cloud action.
