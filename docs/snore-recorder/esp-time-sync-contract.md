# ESP Time Sync Contract

## Purpose

Define the ESP firmware-side MVP contract for internet time synchronization, local display time, and recording segment timestamps.

This document is a design contract only. It does not implement firmware code.

## Source Evidence

- Network connection events are forwarded through `NetworkEvent::Connected` in `main/boards/common/wifi_board.cc`.
- `Application::HandleNetworkConnectedEvent()` is the current application-level point after network connection.
- Existing XiaoZhi code can set system time from OTA `server_time` via `settimeofday()` in `main/ota.cc`, but the snore recorder must not depend on XiaoZhi OTA.
- Current display code already treats `tm_year >= 2025` as a rough "time is set" signal before displaying `HH:MM`.
- `sdkconfig` has LWIP SNTP config present, including `CONFIG_LWIP_SNTP_MAX_SERVERS=1` and `CONFIG_LWIP_SNTP_UPDATE_DELAY=3600000`.

## Time Source

MVP time source:

```text
SNTP over Wi-Fi
```

Default server:

```text
pool.ntp.org
```

Optional China-friendly server for local testing:

```text
ntp.aliyun.com
```

Rules:

- Use one configured SNTP server for MVP.
- Do not use XiaoZhi OTA `server_time` as the recorder time truth.
- Do not use Mac HTTP server time as the primary device clock in MVP.
- System time must be set with `settimeofday()` or ESP-IDF SNTP sync APIs before normal recording.

## State Machine Integration

Recorder application state after provisioning:

```text
WIFI_CONNECTING
  -> TIME_SYNCING       after NetworkEvent::Connected
  -> STANDBY            after valid time sync
  -> ERROR              after sync timeout/failure
```

Rules:

- `TIME_SYNCING` begins only after Wi-Fi connected.
- `STANDBY` is reachable only when `time_synced=true` for MVP.
- `MONITORING` and `RECORDING` are blocked while `time_synced=false`.
- If Wi-Fi disconnects, keep the last valid wall clock for display but block new recording until network returns and time is revalidated.

## Valid Time Check

Time is valid when both conditions are true:

```text
SNTP sync completed successfully
UTC year >= 2025
```

Rules:

- `tm_year >= 2025 - 1900` is acceptable as a guard, matching existing display practice.
- Store an explicit `time_synced` boolean in recorder state; do not infer it only from year checks.
- Store `last_time_sync_monotonic_ms` from `esp_timer` for freshness checks.

## Sync Timeout And Retry

MVP constants:

```text
time_sync_timeout_ms = 15000
time_sync_retry_delay_ms = 10000
max_sync_attempts_before_error = 3
resync_interval_ms = 60 * 60 * 1000
```

Rules:

- On Wi-Fi connect, try SNTP sync up to 3 times.
- During sync, screen shows `校时中` or equivalent.
- On failure after 3 attempts, enter `ERROR` with `校时失败`.
- User may retry by reconnecting Wi-Fi or restarting app flow later.
- Periodic resync may run every hour after standby, but must not interrupt active recording.
- If resync happens during `RECORDING`, defer wall-clock update use until after the segment closes.

## Timestamp Contract

Segment metadata uses wall-clock UTC strings.

Format:

```text
RFC3339 UTC with milliseconds
```

Example:

```text
2026-07-09T18:13:44.123Z
```

Filename timestamp format:

```text
YYYYMMDDTHHMMSSZ
```

Example:

```text
20260709T181344Z_esp-3cdc75fc81e4.wav
```

Rules:

- Use UTC for metadata and filenames.
- Display may convert to local `Asia/Shanghai`.
- Do not put `:` in filenames.
- Segment duration must not be computed from wall-clock start/end. Use monotonic time.

## Monotonic Time Contract

Use `esp_timer_get_time()` for:

- segment duration;
- chunk `offset_ms`;
- start-hold and silence-stop timers;
- upload timeout measurements;
- display elapsed time while recording.

Rules:

- Wall clock is for human time labels only.
- Monotonic time is for all durations and state transitions.
- If SNTP adjusts wall clock during a segment, the segment duration remains monotonic and stable.

## Segment Start/End Time Capture

On segment start:

```text
segment_start_wall_utc_ms = current wall UTC
segment_start_mono_us = esp_timer_get_time()
```

On segment end:

```text
duration_ms = (esp_timer_get_time() - segment_start_mono_us) / 1000
end_time = segment_start_wall_utc_ms + duration_ms
```

Rationale:

- This avoids duration errors if SNTP adjusts wall clock during a segment.
- End time remains consistent with start time plus monotonic duration.

## Display Time Contract

Display after time sync:

```text
HH:MM
HH:MM:SS while recording if useful
```

Rules:

- Display local time in `Asia/Shanghai` for MVP.
- Do not display an unset/default epoch time.
- If time sync fails, display an explicit sync error rather than `00:00` or stale startup time.

## Mac HTTP Relationship

ESP sends `start_time`, `end_time`, `timezone`, and `time_synced` to Mac per `docs/snore-recorder/mac-http-storage-contract.md`.

Rules:

- Mac accepts ESP-provided timestamps as segment metadata for MVP.
- Mac may record server receive time internally later, but it is not the canonical segment start time in MVP.
- If future scope allows `time_synced=false`, Mac must visibly mark the segment as unsynced. MVP blocks recording instead.

## Failure Rules

- If Wi-Fi connects but SNTP fails: no normal recording.
- If Wi-Fi disconnects during monitoring: leave monitoring, show network error, no new segment.
- If Wi-Fi disconnects during recording: stop local segment as `wifi_lost`; Mac finalizes partial if chunks arrived.
- Do not silently fall back to build time, boot time, Mac receive time, or OTA time.

## Readiness Findings

- Existing OTA time logic is coupled to XiaoZhi activation and should not be reused as the recorder time truth.
- Existing display time check can be reused conceptually, but recorder needs explicit `time_synced` state.
- SNTP config exists in `sdkconfig`, but no recorder-specific SNTP owner exists yet.
- The clean L2 owner should be a small time module, for example `RecorderTimeSync`, called after Wi-Fi connected and before entering standby.

## Verification Gates For Future L2

Implementation is not complete until:

- Unit or host test verifies RFC3339 UTC formatting and filesystem-safe filename timestamp formatting.
- Device log shows Wi-Fi connected -> SNTP sync -> `time_synced=true` -> standby.
- Recording is blocked when time sync fails.
- Segment metadata contains RFC3339 UTC `start_time`, `end_time`, `time_synced=true`, and monotonic `duration_ms`.
- Display never shows default epoch time as a valid clock.

