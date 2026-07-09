#!/usr/bin/env python3
"""Upload a synthetic PCM segment to the local snore recorder server."""

from __future__ import annotations

import argparse
import json
import math
import struct
from datetime import datetime, timedelta, timezone
from urllib import request


SAMPLE_RATE = 16000


def sine_pcm(duration_ms: int, frequency_hz: float = 180.0, amplitude: float = 0.35) -> bytes:
    samples = int(SAMPLE_RATE * duration_ms / 1000)
    out = bytearray()
    for i in range(samples):
        value = int(32767 * amplitude * math.sin(2 * math.pi * frequency_hz * i / SAMPLE_RATE))
        out.extend(struct.pack("<h", value))
    return bytes(out)


def post_json(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        base_url + path,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Content-Length": str(len(data))},
    )
    with request.urlopen(req, timeout=5) as res:
        return res.status, json.loads(res.read().decode("utf-8"))


def post_pcm(base_url: str, path: str, pcm: bytes, seq: int, offset_ms: int) -> int:
    req = request.Request(
        base_url + path,
        data=pcm,
        method="POST",
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(pcm)),
            "X-Seq": str(seq),
            "X-Offset-Ms": str(offset_ms),
            "X-Rms-Dbfs": "-32.0",
            "X-Peak-Dbfs": "-16.0",
        },
    )
    with request.urlopen(req, timeout=5) as res:
        return res.status


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload one synthetic snore recorder WAV segment.")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--device-id", default="esp-test001")
    parser.add_argument("--duration-ms", type=int, default=1000)
    parser.add_argument("--chunk-ms", type=int, default=100)
    args = parser.parse_args()

    start = datetime.now(timezone.utc).replace(microsecond=123000)
    end = start + timedelta(milliseconds=args.duration_ms)
    start_time = start.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    end_time = end.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    status, started = post_json(
        args.url,
        "/api/segments/start",
        {
            "device_id": args.device_id,
            "start_time": start_time,
            "timezone": "Asia/Shanghai",
            "time_synced": True,
            "sample_rate": SAMPLE_RATE,
            "channels": 1,
            "sample_format": "s16le",
            "threshold_dbfs": -40.0,
            "pre_roll_ms": 1500,
        },
    )
    if status != 201:
        raise SystemExit(f"start failed with HTTP {status}")

    seq = 0
    for offset_ms in range(0, args.duration_ms, args.chunk_ms):
        chunk_ms = min(args.chunk_ms, args.duration_ms - offset_ms)
        pcm = sine_pcm(chunk_ms)
        chunk_status = post_pcm(args.url, started["upload_url"], pcm, seq, offset_ms)
        if chunk_status != 204:
            raise SystemExit(f"chunk {seq} failed with HTTP {chunk_status}")
        seq += 1

    status, stopped = post_json(
        args.url,
        started["stop_url"],
        {
            "end_time": end_time,
            "duration_ms": args.duration_ms,
            "close_reason": "synthetic_fixture",
        },
    )
    if status != 200:
        raise SystemExit(f"stop failed with HTTP {status}")
    print(json.dumps(stopped, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
