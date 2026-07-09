# LOOP.md

## Loop Purpose

- Loop name: `snore-recorder-l1-design-review`.
- Mode: `L1 report-only`.
- Purpose: repeatedly inspect the snore recorder MVP design and current XiaoZhi ESP32 codebase to produce actionable findings before implementation.
- This loop must improve implementation readiness without changing firmware, Mac server code, build config, secrets, or flashing behavior.

## Cadence

- Manual only. Run when Jason asks for a loop pass, design check, implementation-readiness review, or pre-code audit.
- No watcher, scheduler, daemon, background process, or unattended run is allowed in L1.

## Owner

- Human owner: Jason.
- Agent role: report-only investigator.
- L1 agent may not approve escalation to L2 by itself. L2 requires Jason approval.

## Scope

Allowed L1 inspection targets:

- `AGENTS.md`, `MEMORY.md`, `note.md`.
- Firmware board path: `main/boards/zhengchen-1.54tft-wifi/`.
- Audio paths: `main/audio/`, codec setup, relevant audio service APIs.
- Display paths: `main/display/`, `main/display/lvgl_display/`.
- Wi-Fi/provisioning paths: `main/boards/common/`, `main/settings.*`, relevant board/network code.
- Existing protocol/network client code only as reference.
- Mac HTTP server design documents or future local server files once created.

Out of L1 scope:

- Firmware implementation edits.
- Mac HTTP server implementation edits.
- SDK config changes.
- Partition table changes.
- Build system changes.
- Flashing device or changing device state.
- WebDAV/cloud/auth implementation.
- Long-running tests or background jobs.

## Kill Switch

- If `STATE.md` contains `kill_switch: active`, the loop must stop after logging `no-op`.
- If Jason says `停止循环`, `暂停 loop`, or equivalent, set/keep kill switch active only after explicit instruction to edit state.
- Any repeated unknown, missing owner, or unclear verification gate escalates instead of continuing.

## L1 Output

Each L1 run must produce only a short report with:

- `Findings`: concrete gaps, contradictions, or readiness risks.
- `Evidence`: file references or explicit absence of evidence.
- `No-Change Confirmation`: state that no business code/config was modified.
- `Next L1 Target` or `L2 Candidate` if there is a clear next step.

## L1 Completion Criteria

An L1 run is complete when it has:

- Read required loop governance files.
- Checked kill switch and budget.
- Inspected the smallest relevant source set.
- Logged the run in `loop-run-log.md`.
- Reported findings without making implementation changes.

