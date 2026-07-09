# Snore Recorder Mac Server

Local MVP server for ESP audio-event storage and browser playback.

## Run

```bash
python3 tools/snore_server/server.py --host 0.0.0.0 --port 8765 --recordings recordings
```

Open:

```text
http://127.0.0.1:8765/
```

ESP should call the API defined in `docs/snore-recorder/mac-http-storage-contract.md`.

## Synthetic Upload

With the server running:

```bash
python3 tools/snore_server/synthetic_client.py --url http://127.0.0.1:8765
```

Expected result:

- one `recordings/YYYY-MM-DD/<segment_id>.wav`;
- one matching `recordings/YYYY-MM-DD/<segment_id>.json`;
- `GET /` lists the segment with an `<audio controls>` player.
