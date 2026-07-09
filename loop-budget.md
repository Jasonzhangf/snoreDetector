# loop-budget.md

## L1 Budget

- Mode: `L1 report-only`.
- Max focus areas per run: 1.
- Max source files opened per run: 8.
- Max searches per run: 6.
- Max implementation actions per run: 0.
- Max config/build/flashing actions per run: 0.
- Max run-log entries per run: 1.

## Stop Conditions

- Stop immediately if kill switch is active.
- Stop if the next useful action requires code/config/device/server changes.
- Stop if the same uncertainty remains after 3 focused inspections.
- Stop if source state contradicts `AGENTS.md` and report the contradiction.

