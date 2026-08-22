#!/usr/bin/env python3
"""Phase 3B analysis. Join only by run_id + frame_id. Warmup discarded."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

REPO = "/home/qtannguyen/projects/researcher/HGRIA"
SHA = "8764213c5c568fe20e01a1f387d8a80c8269aa64"
RUN_ID_PREFIX = f"phase3b-local-browser-{SHA}"
FUNNEL_KEYS = ("no_hand", "noise", "temporal", "cooldown", "unmapped", "command")


def parse_iso(text: str) -> datetime:
    ts = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            rows.append(json.loads(text))
    return rows


def wall_of(rec: Dict[str, Any]) -> Optional[datetime]:
    raw = rec.get("wall_iso") or rec.get("timestamp")
    if not raw:
        return None
    return parse_iso(str(raw))


def in_window(rec: Dict[str, Any], start: datetime, end: datetime) -> bool:
    ts = wall_of(rec)
    if ts is None:
        return False
    return start <= ts <= end


def pct(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=float), q, method="linear"))


def summarize(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "p50": None, "p95": None, "p99": None, "min": None, "max": None}
    arr = np.asarray(values, dtype=float)
    return {
        "n": int(arr.size),
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "p50": pct(values, 50),
        "p95": pct(values, 95),
        "p99": pct(values, 99),
        "min": float(arr.min()),
        "max": float(arr.max()),
    }


def frame_key(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)


def index_by_frame(records: List[Dict[str, Any]], run_id: str, predicate) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        if rec.get("run_id") != run_id:
            continue
        if predicate is not None and not predicate(rec):
            continue
        key = frame_key(rec.get("frame_id"))
        if key is None:
            continue
        indexed[key] = rec
    return indexed


def analyze_run(run_index: int) -> Dict[str, Any]:
    run_dir = os.path.join(REPO, "docs", "experiments", f"run_{SHA}_r{run_index}")
    run_id = f"{RUN_ID_PREFIX}-r{run_index}"
    start = parse_iso(open(os.path.join(run_dir, "measure_start_utc.txt"), encoding="utf-8").read())
    end = parse_iso(open(os.path.join(run_dir, "measure_end_utc.txt"), encoding="utf-8").read())
    warmup = parse_iso(open(os.path.join(run_dir, "warmup_start_utc.txt"), encoding="utf-8").read())
    wall_s = (end - start).total_seconds()

    debug_end = json.load(open(os.path.join(run_dir, "debug_end.json"), encoding="utf-8"))
    debug_start = json.load(open(os.path.join(run_dir, "debug_start.json"), encoding="utf-8"))
    sidecar = json.load(open(os.path.join(run_dir, "instrumentation.run.json"), encoding="utf-8"))
    cfg_end = debug_end.get("config") or {}
    cfg_start = debug_start.get("config") or {}

    client_all = load_jsonl(os.path.join(run_dir, "client_instrumentation.jsonl"))
    server_all = load_jsonl(os.path.join(run_dir, "instrumentation.jsonl"))
    client = [r for r in client_all if in_window(r, start, end)]
    server = [r for r in server_all if in_window(r, start, end)]

    captures = index_by_frame(
        client, run_id, lambda r: r.get("event") == "client_capture" or "t_client_capture" in r
    )
    https = index_by_frame(
        client, run_id, lambda r: r.get("event") == "client_http" or "t_client_http_send" in r
    )
    commands = index_by_frame(
        client, run_id, lambda r: r.get("event") == "client_command" or r.get("command_received") is True
    )
    servers = index_by_frame(server, run_id, None)

    unmatched_client = sorted(fid for fid in captures if fid not in servers)
    server_without_client = sorted(fid for fid in servers if fid not in captures)
    command_emitted_ids = [
        fid for fid, rec in servers.items() if rec.get("command_emitted") is True
    ]

    e2e_samples: List[Dict[str, Any]] = []
    rejected_negative = 0
    for fid, capture in captures.items():
        server_row = servers.get(fid)
        command = commands.get(fid)
        if server_row is None or command is None:
            continue
        if server_row.get("command_emitted") is not True:
            continue
        if capture.get("run_id") != run_id or command.get("run_id") != run_id:
            continue
        if server_row.get("run_id") != run_id:
            continue
        t_cap = capture.get("t_client_capture")
        t_recv = command.get("t_client_cmd_recv")
        if not isinstance(t_cap, (int, float)) or not isinstance(t_recv, (int, float)):
            continue
        if isinstance(t_cap, bool) or isinstance(t_recv, bool):
            continue
        e2e = float(t_recv) - float(t_cap)
        if e2e < 0:
            rejected_negative += 1
            continue
        http = https.get(fid, {})
        http_ms = None
        t_send, t_ack = http.get("t_client_http_send"), http.get("t_client_http_ack")
        if isinstance(t_send, (int, float)) and isinstance(t_ack, (int, float)):
            if not isinstance(t_send, bool) and not isinstance(t_ack, bool):
                delta = float(t_ack) - float(t_send)
                if delta >= 0:
                    http_ms = delta
        e2e_samples.append({
            "frame_id": capture.get("frame_id"),
            "run_id": run_id,
            "e2e_latency_ms": e2e,
            "http_request_ms": http_ms,
            "total_server_ms": server_row.get("total_server_ms"),
        })

    http_values: List[float] = []
    for rec in https.values():
        ms = rec.get("http_request_ms")
        if not isinstance(ms, (int, float)) or isinstance(ms, bool):
            t_send, t_ack = rec.get("t_client_http_send"), rec.get("t_client_http_ack")
            if isinstance(t_send, (int, float)) and isinstance(t_ack, (int, float)):
                if not isinstance(t_send, bool) and not isinstance(t_ack, bool):
                    ms = float(t_ack) - float(t_send)
            else:
                continue
        if ms is None or ms < 0:
            continue
        http_values.append(float(ms))

    server_ms = [
        float(r["total_server_ms"])
        for r in servers.values()
        if isinstance(r.get("total_server_ms"), (int, float)) and not isinstance(r.get("total_server_ms"), bool)
    ]
    e2e_ms = [s["e2e_latency_ms"] for s in e2e_samples]
    e2e_server_ms = [
        float(s["total_server_ms"])
        for s in e2e_samples
        if isinstance(s.get("total_server_ms"), (int, float)) and not isinstance(s.get("total_server_ms"), bool)
    ]

    t_caps = [float(r["t_capture"]) for r in servers.values() if isinstance(r.get("t_capture"), (int, float))]
    duration_s = (max(t_caps) - min(t_caps)) if len(t_caps) >= 2 else wall_s
    processed = len(servers)
    processed_fps = processed / duration_s if duration_s > 0 else None
    commands_emitted = len(command_emitted_ids)
    command_rate = commands_emitted / duration_s if duration_s > 0 else None
    dropped = max((int(r.get("dropped_frames") or 0) for r in servers.values()), default=0)

    cpu_vals = [float(r["cpu_percent"]) for r in servers.values() if isinstance(r.get("cpu_percent"), (int, float))]
    rss_vals = [float(r["rss_mb"]) for r in servers.values() if isinstance(r.get("rss_mb"), (int, float))]

    funnel = {k: 0 for k in FUNNEL_KEYS}
    funnel["null"] = 0
    funnel["other"] = 0
    for rec in servers.values():
        reason = rec.get("exit_reason")
        if reason is None:
            funnel["null"] += 1
        elif reason in funnel:
            funnel[reason] += 1
        else:
            funnel["other"] += 1

    capture_ids = [int(fid) for fid in captures if str(fid).isdigit()]
    flags_ok = (
        cfg_start.get("evaluation_mode") is True
        and cfg_start.get("preview_enabled") is False
        and cfg_start.get("strict_camera") is True
        and cfg_start.get("browser_source") is True
        and cfg_start.get("colab_mode") is False
        and cfg_start.get("colab_fallback") is False
        and cfg_start.get("dynamic_gestures_enabled") is False
        and cfg_end.get("evaluation_mode") is True
        and cfg_end.get("preview_enabled") is False
        and cfg_end.get("browser_source") is True
        and cfg_end.get("colab_mode") is False
        and cfg_end.get("colab_fallback") is False
        and cfg_end.get("dynamic_gestures_enabled") is False
        and sidecar.get("colab_mode") is False
        and sidecar.get("colab_fallback") is False
        and sidecar.get("browser_source") is True
        and sidecar.get("evaluation_mode") is True
        and sidecar.get("preview_enabled") is False
        and sidecar.get("dynamic_gestures_enabled") is False
        and sidecar.get("opencv", {}).get("cv2_version") == "4.10.0"
        and processed >= 0
        and len(captures) >= 1000
        and wall_s >= 60.0
        and capture_ids
        and max(capture_ids) > min(capture_ids)
    )
    invalid_reasons = []
    if len(captures) < 1000:
        invalid_reasons.append(f"client_frames={len(captures)}<1000")
    if wall_s < 60:
        invalid_reasons.append(f"duration={wall_s}<60")
    if cfg_end.get("colab_mode") or cfg_end.get("colab_fallback"):
        invalid_reasons.append("colab_path")
    if not capture_ids:
        invalid_reasons.append("no_client_frame_ids")

    return {
        "run": f"r{run_index}",
        "run_id": run_id,
        "run_dir": run_dir,
        "validity": "VALID" if flags_ok and not invalid_reasons else "INVALID",
        "invalid_reasons": invalid_reasons,
        "warmup_start": warmup.isoformat(),
        "measure_start": start.isoformat(),
        "measure_end": end.isoformat(),
        "wall_window_s": wall_s,
        "duration_s": duration_s,
        "client_submitted_frames": len(captures),
        "server_processed_frames": processed,
        "unmatched_client_frames": len(unmatched_client),
        "server_rows_without_client_capture": len(server_without_client),
        "command_emitted_frames": commands_emitted,
        "command_received_frames": len(commands),
        "matched_E2E_frames": len(e2e_samples),
        "rejected_negative_e2e": rejected_negative,
        "processed_fps": processed_fps,
        "command_rate": command_rate,
        "dropped_frames": dropped,
        "cpu_mean_percent": float(np.mean(cpu_vals)) if cpu_vals else None,
        "rss_min_mb": float(np.min(rss_vals)) if rss_vals else None,
        "rss_mean_mb": float(np.mean(rss_vals)) if rss_vals else None,
        "rss_max_mb": float(np.max(rss_vals)) if rss_vals else None,
        "server_total_server_ms": summarize(server_ms),
        "http_request_ack_ms": summarize(http_values),
        "e2e_latency_ms": summarize(e2e_ms),
        "e2e_subset_total_server_ms": summarize(e2e_server_ms),
        "funnel": funnel,
        "unmatched_client_frame_ids_head": unmatched_client[:20],
        "unmatched_client_frame_ids_count": len(unmatched_client),
        "capture_id_min": min(capture_ids) if capture_ids else None,
        "capture_id_max": max(capture_ids) if capture_ids else None,
        "debug_end": {
            "evaluation_mode": cfg_end.get("evaluation_mode"),
            "preview_enabled": cfg_end.get("preview_enabled"),
            "strict_camera": cfg_end.get("strict_camera"),
            "browser_source": cfg_end.get("browser_source"),
            "colab_mode": cfg_end.get("colab_mode"),
            "colab_fallback": cfg_end.get("colab_fallback"),
            "dynamic_gestures_enabled": cfg_end.get("dynamic_gestures_enabled"),
            "processed_frames": debug_end.get("processed_frames"),
            "commands_sent": debug_end.get("commands_sent"),
            "dropped_frames": debug_end.get("dropped_frames"),
            "diagnosis": debug_end.get("diagnosis"),
        },
        "sidecar": {
            "git_sha": sidecar.get("git_sha"),
            "cv2_version": sidecar.get("opencv", {}).get("cv2_version"),
            "cv2_file": sidecar.get("opencv", {}).get("cv2_file"),
            "browser_source": sidecar.get("browser_source"),
            "config_sha256_live": sidecar.get("config_sha256"),
        },
    }


def main() -> int:
    results = [analyze_run(i) for i in (1, 2, 3)]
    out = os.path.join(REPO, "docs", "experiments", "phase3b_metrics.json")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    for rec in results:
        print(json.dumps({
            "run": rec["run"],
            "validity": rec["validity"],
            "invalid_reasons": rec["invalid_reasons"],
            "client": rec["client_submitted_frames"],
            "server": rec["server_processed_frames"],
            "unmatched": rec["unmatched_client_frames"],
            "server_wo_client": rec["server_rows_without_client_capture"],
            "cmd_emitted": rec["command_emitted_frames"],
            "cmd_recv": rec["command_received_frames"],
            "e2e": rec["matched_E2E_frames"],
            "duration_s": rec["duration_s"],
            "wall_s": rec["wall_window_s"],
            "fps": rec["processed_fps"],
            "server": rec["server_total_server_ms"],
            "http": rec["http_request_ack_ms"],
            "e2e_stats": rec["e2e_latency_ms"],
            "e2e_server": rec["e2e_subset_total_server_ms"],
            "funnel": rec["funnel"],
            "cpu": rec["cpu_mean_percent"],
            "rss": [rec["rss_min_mb"], rec["rss_mean_mb"], rec["rss_max_mb"]],
            "drops": rec["dropped_frames"],
            "cmd_rate": rec["command_rate"],
            "ids": [rec["capture_id_min"], rec["capture_id_max"]],
        }, indent=2))
    print("WROTE", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
