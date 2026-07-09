# STATE.md

loop_id: snore-recorder-l1-design-review
mode: L1
kill_switch: inactive
last_run_id: 2026-07-09T14:38:38Z
current_focus: L2 implementation slice plan complete for L1

## Current Baseline

- Target board: `zhengchen-1.54tft-wifi`.
- Product direction: snore/audio event recorder.
- Firmware MVP: Wi-Fi provisioning, SNTP time sync, standby, monitoring, threshold-triggered recording, Mac HTTP upload.
- Mac MVP: one recording segment is one playable WAV plus one JSON metadata file.
- L1 status: report-only loop rules defined; no implementation started.

## Open L1 Questions

- ESP 240x240 display layout contract is defined in `docs/snore-recorder/esp-display-layout-contract.md`; accepted mockup is `docs/snore-recorder/display-mockup.html`.
- ESP audio PCM capture/upload contract is defined in `docs/snore-recorder/esp-audio-capture-upload-contract.md`; L2 still needs fixed-buffer implementation decisions before coding.
- ESP SNTP/time contract is defined in `docs/snore-recorder/esp-time-sync-contract.md`; L2 should create a small recorder time-sync owner after Wi-Fi connected and before standby.
- Mac HTTP API shape is defined in `docs/snore-recorder/mac-http-storage-contract.md`.
- L2 implementation order and verification map are defined in `docs/snore-recorder/l2-implementation-slice-plan.md`; recommended first implementation slice is Mac HTTP storage/playback with synthetic PCM verification.
