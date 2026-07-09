# Mac HTTP Storage And Playback Contract

## Purpose

Define the MVP contract between ESP firmware and the local Mac HTTP server for snore/audio event recording.

This document is a design contract only. It does not implement the server.

## Design Principle

- ESP streams small PCM chunks because it has limited RAM and no local persistent audio storage in MVP.
- Mac stores one recording segment as one playable WAV file plus one JSON metadata file.
- Chunk files are not user-facing data and must not appear in the final recording library.
- Browser playback uses the finalized WAV file directly.

## Audio Format

- Encoding on wire: raw PCM bytes.
- Sample rate: `16000` Hz.
- Channels: `1` mono.
- Sample format: signed little-endian 16-bit PCM, `s16le`.
- WAV container: Mac server writes standard RIFF/WAVE PCM.
- MIME for playback: `audio/wav`.

## Segment Identity

The ESP starts a new segment when audio exceeds threshold long enough.

Segment ID format:

```text
YYYYMMDDTHHMMSSZ_esp-<device_id>
```

Example:

```text
20260709T181344Z_esp-3cdc75fc81e4
```

Rules:

- Timestamp component is UTC and filesystem-safe.
- `device_id` should use the device MAC or stable device ID without `:`.
- If two segments start in the same second from the same device, server appends a short suffix such as `_001`.

## Filesystem Layout

```text
recordings/
  index.json
  2026-07-09/
    20260709T181344Z_esp-3cdc75fc81e4.wav
    20260709T181344Z_esp-3cdc75fc81e4.json
```

Rules:

- Date directory is derived from segment UTC date.
- WAV and JSON base names must match the segment ID.
- Temporary implementation files are allowed only during an active write and must not be exposed by list APIs.

## HTTP API

### `POST /api/segments/start`

Creates a segment, opens one WAV file, writes a provisional WAV header, and returns the segment ID.

Request JSON:

```json
{
  "device_id": "esp-3cdc75fc81e4",
  "start_time": "2026-07-09T18:13:44.123Z",
  "timezone": "Asia/Shanghai",
  "time_synced": true,
  "sample_rate": 16000,
  "channels": 1,
  "sample_format": "s16le",
  "threshold_dbfs": -40.0,
  "pre_roll_ms": 1500
}
```

Response JSON:

```json
{
  "segment_id": "20260709T181344Z_esp-3cdc75fc81e4",
  "upload_url": "/api/segments/20260709T181344Z_esp-3cdc75fc81e4/chunk",
  "stop_url": "/api/segments/20260709T181344Z_esp-3cdc75fc81e4/stop"
}
```

Status codes:

- `201`: segment created.
- `400`: invalid schema or unsupported audio format.
- `409`: duplicate active segment for same device.
- `507`: insufficient storage.

### `POST /api/segments/{segment_id}/chunk`

Appends PCM bytes to the open segment WAV file.

Headers:

```text
Content-Type: application/octet-stream
X-Seq: 0
X-Offset-Ms: 0
X-Rms-Dbfs: -38.4
X-Peak-Dbfs: -20.1
```

Body:

```text
raw s16le PCM bytes
```

Rules:

- `X-Seq` starts at `0` and increments by `1`.
- `X-Offset-Ms` is relative to segment start and is produced from monotonic time on ESP.
- Server rejects out-of-order chunks in MVP. It does not reorder silently.
- Server updates `chunk_count`, `duration_ms`, `max_dbfs`, and running average stats.

Status codes:

- `204`: chunk appended.
- `400`: invalid headers or non-PCM byte count.
- `404`: segment not found.
- `409`: out-of-order sequence or segment already closed.
- `507`: insufficient storage.

### `POST /api/segments/{segment_id}/stop`

Finalizes the WAV header, closes the file, writes JSON metadata, updates `index.json`, and exposes the segment for playback.

Request JSON:

```json
{
  "end_time": "2026-07-09T18:14:02.861Z",
  "duration_ms": 18738,
  "close_reason": "silence_timeout"
}
```

Response JSON:

```json
{
  "segment_id": "20260709T181344Z_esp-3cdc75fc81e4",
  "status": "complete",
  "playable": true,
  "audio_url": "/audio/20260709T181344Z_esp-3cdc75fc81e4.wav",
  "metadata_url": "/api/segments/20260709T181344Z_esp-3cdc75fc81e4"
}
```

Status codes:

- `200`: segment finalized.
- `404`: segment not found.
- `409`: already finalized.
- `500`: failed to finalize WAV or metadata.

### `GET /api/segments`

Returns finalized or partial playable segments.

Response JSON:

```json
{
  "segments": [
    {
      "segment_id": "20260709T181344Z_esp-3cdc75fc81e4",
      "start_time": "2026-07-09T18:13:44.123Z",
      "duration_ms": 18738,
      "status": "complete",
      "audio_url": "/audio/20260709T181344Z_esp-3cdc75fc81e4.wav"
    }
  ]
}
```

### `GET /api/segments/{segment_id}`

Returns the full metadata JSON for one segment.

### `GET /audio/{segment_id}.wav`

Returns the finalized WAV for browser playback.

### `GET /`

Serves a minimal playback UI:

- list segments sorted by `start_time` descending;
- show status, duration, threshold, max/avg dBFS;
- use a browser `<audio controls>` element for WAV playback.

## Metadata Schema

Metadata file path:

```text
recordings/YYYY-MM-DD/<segment_id>.json
```

Schema:

```json
{
  "segment_id": "20260709T181344Z_esp-3cdc75fc81e4",
  "device_id": "esp-3cdc75fc81e4",
  "start_time": "2026-07-09T18:13:44.123Z",
  "end_time": "2026-07-09T18:14:02.861Z",
  "timezone": "Asia/Shanghai",
  "time_synced": true,
  "duration_ms": 18738,
  "threshold_dbfs": -40.0,
  "max_dbfs": -18.2,
  "avg_dbfs": -36.9,
  "sample_rate": 16000,
  "channels": 1,
  "sample_format": "s16le",
  "container": "wav",
  "chunk_count": 312,
  "pre_roll_ms": 1500,
  "upload_status": "complete",
  "close_reason": "silence_timeout",
  "playable": true,
  "audio_file": "20260709T181344Z_esp-3cdc75fc81e4.wav"
}
```

## Partial Segment Rule

If ESP disconnects or server fails before `/stop`, the server must finalize the WAV if at least one valid PCM chunk was received.

Partial metadata fields:

```json
{
  "upload_status": "partial",
  "close_reason": "connection_lost",
  "playable": true
}
```

Rules:

- Do not leave unplayable WAV files in the visible library.
- If there are zero audio bytes, delete the WAV and write no segment entry.
- Partial segments must be visually marked in the playback UI.

## Index Rule

`recordings/index.json` is a derived convenience index, not the only source of truth.

Rules:

- Segment metadata JSON files are authoritative.
- Index may be rebuilt by scanning metadata files.
- Updates to index should be atomic: write temp file, then rename.

## Implementation Constraints For Future L2

- Keep server simple for MVP: one process, local filesystem, no database.
- Keep one active segment per device.
- Do not add WebDAV, auth, cloud, model processing, or transcription in MVP storage module.
- Do not silently convert audio format. Unsupported format returns `400`.
- Do not claim success until the WAV is finalized and browser playback is verified.

## Verification Gates

Future implementation is complete only after:

- a synthetic PCM request flow creates one WAV and one JSON;
- the WAV plays in a browser through `GET /`;
- metadata contains RFC3339 UTC `start_time` and `end_time`;
- interrupted upload produces a playable `partial` segment;
- invalid format is rejected with `400`.

