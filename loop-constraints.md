# loop-constraints.md

## Mode Lock

- Current loop is `L1 report-only`.
- L1 may inspect and report only.
- L1 must not edit source code, build config, SDK config, flashing scripts, server implementation, credentials, or generated artifacts.
- L1 may edit loop governance files, `note.md`, and `MEMORY.md` only to record loop rules or confirmed findings.

## Allowed Actions

- Read project memory and loop files.
- Search and open source files.
- Produce readiness findings with file references.
- Append one run entry to `loop-run-log.md`.
- Update `STATE.md` focus/status when no implementation code is touched.

## Denied Actions

- No firmware code changes in L1.
- No Mac server code changes in L1.
- No `sdkconfig`, partition, CMake, dependency, or board config changes in L1.
- No flashing, erase, reset, or serial interaction in L1.
- No background jobs, watchers, schedulers, or daemons.
- No WebDAV/cloud/auth implementation.
- No fallback or alternate hidden protocol path.
- No broad kill commands.

## Attempt Limits

- One L1 run handles one focus area.
- Max 3 searches per focus area before reporting uncertainty or escalating.
- If owner path cannot be identified after 2 focused inspections, report `owner pending` instead of guessing.

## Escalation Rules

Escalate to Jason before L2 if any of these are needed:

- Business code edits.
- Build/config edits.
- Device flashing or hardware verification.
- Starting a Mac HTTP server implementation.
- Choosing a persistent cloud/WebDAV/auth strategy.
- Any action that can alter existing firmware behavior.

## Report Rules

- Keep reports short and evidence-first.
- Do not claim implementation readiness without naming missing gates.
- Do not claim closed-loop success without real ESP-to-Mac-to-browser playback evidence.

