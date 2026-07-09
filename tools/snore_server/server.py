#!/usr/bin/env python3
"""Local HTTP WAV storage server for the snore recorder MVP."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
SAMPLE_FORMAT = "s16le"
SEGMENT_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[A-Za-z0-9._-]+(?:_[0-9]{3})?$")


def parse_rfc3339_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be RFC3339 UTC ending with Z")
    dt = datetime.fromisoformat(value[:-1] + "+00:00")
    if dt.tzinfo is None:
        raise ValueError("timestamp must include UTC timezone")
    return dt.astimezone(timezone.utc)


def segment_time_id(start_time: str) -> str:
    dt = parse_rfc3339_utc(start_time)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def date_dir_name(start_time: str) -> str:
    dt = parse_rfc3339_utc(start_time)
    return dt.strftime("%Y-%m-%d")


def clean_device_id(device_id: str) -> str:
    if not isinstance(device_id, str) or not device_id:
        raise ValueError("device_id is required")
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "", device_id)
    if not cleaned or len(cleaned) > 64:
        raise ValueError("device_id contains no valid characters or is too long")
    return cleaned


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


@dataclass
class ActiveSegment:
    segment_id: str
    device_id: str
    start_time: str
    timezone_name: str
    time_synced: bool
    threshold_dbfs: float
    pre_roll_ms: int
    date_dir: Path
    wav_path: Path
    wav_file_handle: Any
    wav_writer: wave.Wave_write
    next_seq: int = 0
    chunk_count: int = 0
    audio_bytes: int = 0
    max_dbfs: float | None = None
    rms_weighted_sum: float = 0.0
    rms_weight: int = 0
    created_at_monotonic: float = field(default_factory=time.monotonic)

    def append_chunk(self, pcm: bytes, seq: int, rms_dbfs: float, peak_dbfs: float) -> None:
        if seq != self.next_seq:
            raise ValueError(f"expected seq {self.next_seq}, got {seq}")
        if len(pcm) == 0 or len(pcm) % SAMPLE_WIDTH_BYTES != 0:
            raise ValueError("PCM chunk must contain whole 16-bit samples")

        self.wav_writer.writeframesraw(pcm)
        sample_count = len(pcm) // SAMPLE_WIDTH_BYTES
        self.audio_bytes += len(pcm)
        self.chunk_count += 1
        self.next_seq += 1
        self.max_dbfs = peak_dbfs if self.max_dbfs is None else max(self.max_dbfs, peak_dbfs)
        self.rms_weighted_sum += rms_dbfs * sample_count
        self.rms_weight += sample_count

    def audio_duration_ms(self) -> int:
        samples = self.audio_bytes // (SAMPLE_WIDTH_BYTES * CHANNELS)
        return int(round(samples * 1000 / SAMPLE_RATE))

    def avg_dbfs(self) -> float:
        if self.rms_weight == 0:
            return -math.inf
        return self.rms_weighted_sum / self.rms_weight

    def close_wav(self) -> None:
        self.wav_writer.close()
        self.wav_file_handle.close()


class RecordingStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.active: dict[str, ActiveSegment] = {}

    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    def start(self, payload: dict[str, Any]) -> dict[str, str]:
        required = [
            "device_id",
            "start_time",
            "timezone",
            "time_synced",
            "sample_rate",
            "channels",
            "sample_format",
            "threshold_dbfs",
            "pre_roll_ms",
        ]
        missing = [name for name in required if name not in payload]
        if missing:
            raise ValueError(f"missing fields: {', '.join(missing)}")
        if payload["sample_rate"] != SAMPLE_RATE or payload["channels"] != CHANNELS:
            raise ValueError("unsupported sample_rate or channels")
        if payload["sample_format"] != SAMPLE_FORMAT:
            raise ValueError("unsupported sample_format")
        if payload["time_synced"] is not True:
            raise ValueError("time_synced must be true")

        device_id = clean_device_id(payload["device_id"])
        if any(seg.device_id == device_id for seg in self.active.values()):
            raise FileExistsError("duplicate active segment for device")

        base_id = f"{segment_time_id(payload['start_time'])}_{device_id}"
        segment_id = self._unique_segment_id(base_id)
        date_dir = self.root / date_dir_name(payload["start_time"])
        date_dir.mkdir(parents=True, exist_ok=True)
        wav_path = date_dir / f"{segment_id}.wav"
        wav_handle = wav_path.open("wb")
        wav_writer = wave.open(wav_handle, "wb")
        wav_writer.setnchannels(CHANNELS)
        wav_writer.setsampwidth(SAMPLE_WIDTH_BYTES)
        wav_writer.setframerate(SAMPLE_RATE)

        self.active[segment_id] = ActiveSegment(
            segment_id=segment_id,
            device_id=device_id,
            start_time=payload["start_time"],
            timezone_name=str(payload["timezone"]),
            time_synced=True,
            threshold_dbfs=float(payload["threshold_dbfs"]),
            pre_roll_ms=int(payload["pre_roll_ms"]),
            date_dir=date_dir,
            wav_path=wav_path,
            wav_file_handle=wav_handle,
            wav_writer=wav_writer,
        )
        return {
            "segment_id": segment_id,
            "upload_url": f"/api/segments/{segment_id}/chunk",
            "stop_url": f"/api/segments/{segment_id}/stop",
        }

    def append_chunk(
        self,
        segment_id: str,
        pcm: bytes,
        seq: int,
        offset_ms: int,
        rms_dbfs: float,
        peak_dbfs: float,
    ) -> None:
        seg = self._active_segment(segment_id)
        if offset_ms < 0:
            raise ValueError("X-Offset-Ms must be >= 0")
        seg.append_chunk(pcm, seq, rms_dbfs, peak_dbfs)

    def stop(self, segment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        seg = self._active_segment(segment_id)
        for name in ("end_time", "duration_ms", "close_reason"):
            if name not in payload:
                raise ValueError(f"missing field: {name}")
        parse_rfc3339_utc(payload["end_time"])
        duration_ms = int(payload["duration_ms"])
        if duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")

        seg.close_wav()
        self.active.pop(segment_id, None)
        if seg.audio_bytes == 0:
            seg.wav_path.unlink(missing_ok=True)
            raise RuntimeError("empty segment discarded")

        metadata = {
            "segment_id": segment_id,
            "device_id": seg.device_id,
            "start_time": seg.start_time,
            "end_time": payload["end_time"],
            "timezone": seg.timezone_name,
            "time_synced": seg.time_synced,
            "duration_ms": duration_ms,
            "audio_duration_ms": seg.audio_duration_ms(),
            "threshold_dbfs": seg.threshold_dbfs,
            "max_dbfs": round(seg.max_dbfs if seg.max_dbfs is not None else -math.inf, 2),
            "avg_dbfs": round(seg.avg_dbfs(), 2),
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "sample_format": SAMPLE_FORMAT,
            "container": "wav",
            "chunk_count": seg.chunk_count,
            "pre_roll_ms": seg.pre_roll_ms,
            "upload_status": "complete",
            "close_reason": str(payload["close_reason"]),
            "playable": True,
            "audio_file": seg.wav_path.name,
            "audio_url": f"/audio/{segment_id}.wav",
            "metadata_url": f"/api/segments/{segment_id}",
        }
        metadata_path = seg.date_dir / f"{segment_id}.json"
        metadata_path.write_bytes(json_bytes(metadata))
        self._write_index()
        return {
            "segment_id": segment_id,
            "status": "complete",
            "playable": True,
            "audio_url": f"/audio/{segment_id}.wav",
            "metadata_url": f"/api/segments/{segment_id}",
        }

    def list_segments(self) -> list[dict[str, Any]]:
        segments = []
        for metadata_path in self.root.glob("*/*.json"):
            if metadata_path.name == "index.json":
                continue
            try:
                metadata = json.loads(metadata_path.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            segments.append(
                {
                    "segment_id": metadata["segment_id"],
                    "start_time": metadata["start_time"],
                    "duration_ms": metadata["duration_ms"],
                    "status": metadata["upload_status"],
                    "audio_url": metadata["audio_url"],
                    "threshold_dbfs": metadata["threshold_dbfs"],
                    "max_dbfs": metadata["max_dbfs"],
                    "avg_dbfs": metadata["avg_dbfs"],
                }
            )
        return sorted(segments, key=lambda item: item["start_time"], reverse=True)

    def metadata(self, segment_id: str) -> dict[str, Any]:
        self._validate_segment_id(segment_id)
        for metadata_path in self.root.glob(f"*/{segment_id}.json"):
            return json.loads(metadata_path.read_text("utf-8"))
        raise FileNotFoundError("segment metadata not found")

    def audio_path(self, segment_id: str) -> Path:
        metadata = self.metadata(segment_id)
        path = self.root / date_dir_name(metadata["start_time"]) / metadata["audio_file"]
        if not path.exists():
            raise FileNotFoundError("audio file not found")
        return path

    def close_active_partials(self) -> None:
        for segment_id in list(self.active):
            seg = self.active.pop(segment_id)
            seg.close_wav()
            if seg.audio_bytes == 0:
                seg.wav_path.unlink(missing_ok=True)
                continue
            end_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            metadata = {
                "segment_id": segment_id,
                "device_id": seg.device_id,
                "start_time": seg.start_time,
                "end_time": end_time,
                "timezone": seg.timezone_name,
                "time_synced": seg.time_synced,
                "duration_ms": seg.audio_duration_ms(),
                "audio_duration_ms": seg.audio_duration_ms(),
                "threshold_dbfs": seg.threshold_dbfs,
                "max_dbfs": round(seg.max_dbfs if seg.max_dbfs is not None else -math.inf, 2),
                "avg_dbfs": round(seg.avg_dbfs(), 2),
                "sample_rate": SAMPLE_RATE,
                "channels": CHANNELS,
                "sample_format": SAMPLE_FORMAT,
                "container": "wav",
                "chunk_count": seg.chunk_count,
                "pre_roll_ms": seg.pre_roll_ms,
                "upload_status": "partial",
                "close_reason": "server_shutdown",
                "playable": True,
                "audio_file": seg.wav_path.name,
                "audio_url": f"/audio/{segment_id}.wav",
                "metadata_url": f"/api/segments/{segment_id}",
            }
            (seg.date_dir / f"{segment_id}.json").write_bytes(json_bytes(metadata))
        self._write_index()

    def _active_segment(self, segment_id: str) -> ActiveSegment:
        self._validate_segment_id(segment_id)
        if segment_id not in self.active:
            raise FileNotFoundError("active segment not found")
        return self.active[segment_id]

    def _unique_segment_id(self, base_id: str) -> str:
        self._validate_segment_id(base_id)
        existing = {path.stem for path in self.root.glob("*/*.wav")}
        existing.update(self.active.keys())
        if base_id not in existing:
            return base_id
        for suffix in range(1, 1000):
            candidate = f"{base_id}_{suffix:03d}"
            if candidate not in existing:
                return candidate
        raise FileExistsError("too many duplicate segment ids")

    def _write_index(self) -> None:
        index = {"segments": self.list_segments()}
        self.index_path.write_bytes(json_bytes(index))

    @staticmethod
    def _validate_segment_id(segment_id: str) -> None:
        if not SEGMENT_RE.match(segment_id):
            raise ValueError("invalid segment_id")


class SnoreRequestHandler(BaseHTTPRequestHandler):
    server_version = "SnoreHTTP/0.1"

    @property
    def store(self) -> RecordingStore:
        return self.server.store  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        try:
            path = unquote(urlparse(self.path).path)
            if path == "/":
                self._send_html(self._index_html())
            elif path == "/api/segments":
                self._send_json({"segments": self.store.list_segments()})
            elif path.startswith("/api/segments/"):
                segment_id = path.removeprefix("/api/segments/")
                self._send_json(self.store.metadata(segment_id))
            elif path.startswith("/audio/") and path.endswith(".wav"):
                segment_id = path.removeprefix("/audio/").removesuffix(".wav")
                self._send_file(self.store.audio_path(segment_id), "audio/wav")
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "not found")
        except FileNotFoundError as exc:
            self._send_error(HTTPStatus.NOT_FOUND, str(exc))
        except ValueError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:
        try:
            path = unquote(urlparse(self.path).path)
            if path == "/api/segments/start":
                payload = self._read_json()
                response = self.store.start(payload)
                self._send_json(response, HTTPStatus.CREATED)
            elif path.startswith("/api/segments/") and path.endswith("/chunk"):
                segment_id = path.removeprefix("/api/segments/").removesuffix("/chunk")
                pcm = self.rfile.read(self._content_length())
                self.store.append_chunk(
                    segment_id=segment_id,
                    pcm=pcm,
                    seq=self._required_int_header("X-Seq"),
                    offset_ms=self._required_int_header("X-Offset-Ms"),
                    rms_dbfs=self._required_float_header("X-Rms-Dbfs"),
                    peak_dbfs=self._required_float_header("X-Peak-Dbfs"),
                )
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
            elif path.startswith("/api/segments/") and path.endswith("/stop"):
                segment_id = path.removeprefix("/api/segments/").removesuffix("/stop")
                response = self.store.stop(segment_id, self._read_json())
                self._send_json(response)
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "not found")
        except FileExistsError as exc:
            self._send_error(HTTPStatus.CONFLICT, str(exc))
        except FileNotFoundError as exc:
            self._send_error(HTTPStatus.NOT_FOUND, str(exc))
        except RuntimeError as exc:
            self._send_error(HTTPStatus.CONFLICT, str(exc))
        except ValueError as exc:
            message = str(exc)
            status = HTTPStatus.CONFLICT if message.startswith("expected seq") else HTTPStatus.BAD_REQUEST
            self._send_error(status, message)

    def log_message(self, fmt: str, *args: Any) -> None:
        if getattr(self.server, "quiet", False):  # type: ignore[attr-defined]
            return
        super().log_message(fmt, *args)

    def _content_length(self) -> int:
        raw = self.headers.get("Content-Length")
        if raw is None:
            raise ValueError("Content-Length is required")
        length = int(raw)
        if length < 0:
            raise ValueError("Content-Length must be >= 0")
        return length

    def _read_json(self) -> dict[str, Any]:
        body = self.rfile.read(self._content_length())
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _required_int_header(self, name: str) -> int:
        value = self.headers.get(name)
        if value is None:
            raise ValueError(f"{name} is required")
        return int(value)

    def _required_float_header(self, name: str) -> float:
        value = self.headers.get(name)
        if value is None:
            raise ValueError(f"{name} is required")
        return float(value)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, mime: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as src:
            shutil.copyfileobj(src, self.wfile)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status)

    def _index_html(self) -> str:
        return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Snore Recorder</title>
  <style>
    :root { color-scheme: light; --bg:#f4efe7; --ink:#1d2528; --line:#d8cbbb; --accent:#0f6b5f; }
    body { margin:0; font:16px/1.45 Georgia, "Songti SC", serif; background:linear-gradient(135deg,#f8f0df,#dfeee9); color:var(--ink); }
    main { max-width:920px; margin:0 auto; padding:34px 18px 48px; }
    h1 { margin:0 0 6px; font-size:34px; letter-spacing:-0.03em; }
    .sub { margin:0 0 24px; color:#506064; }
    .card { border:1px solid var(--line); border-radius:18px; padding:18px; margin:14px 0; background:rgba(255,255,255,.68); box-shadow:0 14px 34px rgba(49,43,34,.08); }
    .row { display:flex; gap:16px; justify-content:space-between; flex-wrap:wrap; }
    .id { font-family:"SF Mono", Menlo, monospace; font-size:13px; color:#526165; }
    .status { color:var(--accent); font-weight:700; }
    audio { width:100%; margin-top:12px; }
    button { border:0; border-radius:999px; background:var(--ink); color:white; padding:10px 16px; cursor:pointer; }
  </style>
</head>
<body>
<main>
  <h1>Snore Recorder</h1>
  <p class="sub">Mac 本地录音段回放页：一个片段对应一个 WAV 和一个 JSON metadata。</p>
  <button onclick="loadSegments()">刷新列表</button>
  <section id="segments"></section>
</main>
<script>
async function loadSegments() {
  const res = await fetch('/api/segments');
  const data = await res.json();
  const root = document.getElementById('segments');
  if (!data.segments.length) {
    root.innerHTML = '<div class="card">暂无录音片段。</div>';
    return;
  }
  root.innerHTML = data.segments.map(seg => `
    <article class="card">
      <div class="row">
        <div>
          <div class="id">${seg.segment_id}</div>
          <strong>${seg.start_time}</strong>
        </div>
        <div class="status">${seg.status}</div>
      </div>
      <p>时长 ${seg.duration_ms} ms · 阈值 ${seg.threshold_dbfs} dBFS · 峰值 ${seg.max_dbfs} dBFS · 平均 ${seg.avg_dbfs} dBFS</p>
      <audio controls preload="metadata" src="${seg.audio_url}"></audio>
    </article>
  `).join('');
}
loadSegments();
</script>
</body>
</html>
"""


def create_server(host: str, port: int, recordings: Path, quiet: bool = False) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), SnoreRequestHandler)
    server.store = RecordingStore(recordings)  # type: ignore[attr-defined]
    server.quiet = quiet  # type: ignore[attr-defined]
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local snore recorder HTTP server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--recordings", type=Path, default=Path("recordings"))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    server = create_server(args.host, args.port, args.recordings, args.quiet)
    print(f"Snore server listening on http://{args.host}:{args.port}")
    print(f"Recordings directory: {args.recordings.resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.store.close_active_partials()  # type: ignore[attr-defined]
        server.server_close()


if __name__ == "__main__":
    main()
