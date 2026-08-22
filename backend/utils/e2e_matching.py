"""Phase 3B: join client and server JSONL by frame_id.

E2E latency is computed only from matching browser monotonic timestamps:

    E2E_latency_ms = t_client_cmd_recv - t_client_capture

Server ``perf_counter()`` values are never subtracted from browser
``performance.now()`` values. Unmatched frames are counted, not invented.
Negative E2E samples are rejected.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple


def compute_e2e_ms(
    t_client_cmd_recv: Any,
    t_client_capture: Any,
) -> Optional[float]:
    """Return capture→command-receive latency, or None if invalid.

    Missing timestamps and negative results are rejected. This function
    does not fabricate a value for unmatched frames.
    """
    if not isinstance(t_client_cmd_recv, (int, float)):
        return None
    if not isinstance(t_client_capture, (int, float)):
        return None
    if isinstance(t_client_cmd_recv, bool) or isinstance(t_client_capture, bool):
        return None
    e2e = float(t_client_cmd_recv) - float(t_client_capture)
    if e2e < 0.0:
        return None
    return e2e


def compute_http_request_ms(
    t_client_http_ack: Any,
    t_client_http_send: Any,
) -> Optional[float]:
    """Browser HTTP request/ack latency. Not one-way network latency."""
    if not isinstance(t_client_http_ack, (int, float)):
        return None
    if not isinstance(t_client_http_send, (int, float)):
        return None
    if isinstance(t_client_http_ack, bool) or isinstance(t_client_http_send, bool):
        return None
    ms = float(t_client_http_ack) - float(t_client_http_send)
    if ms < 0.0:
        return None
    return ms


def _frame_key(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    """Read an append-only JSONL file. Blank lines are skipped."""
    records: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            records.append(json.loads(text))
    return records


def _index_by_frame(
    records: Iterable[Dict[str, Any]],
    predicate=None,
) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        if predicate is not None and not predicate(rec):
            continue
        key = _frame_key(rec.get("frame_id"))
        if key is None:
            continue
        indexed[key] = rec
    return indexed


def match_e2e_samples(
    client_records: Iterable[Dict[str, Any]],
    server_records: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return valid E2E samples joined strictly by frame_id.

    A valid sample requires:

    1. client capture record exists
    2. matching server frame_id exists
    3. server JSONL has command_emitted=true
    4. browser command-receive record exists
    5. command frame_id equals capture frame_id

    Matching is never by timestamp proximity, row number, or gesture name.
    """
    client_list = list(client_records)
    server_list = list(server_records)

    captures = _index_by_frame(
        client_list,
        lambda r: r.get("event") == "client_capture" or "t_client_capture" in r,
    )
    commands = _index_by_frame(
        client_list,
        lambda r: r.get("event") == "client_command" or r.get("command_received") is True,
    )
    https = _index_by_frame(
        client_list,
        lambda r: r.get("event") == "client_http" or "t_client_http_send" in r,
    )
    servers = _index_by_frame(server_list)

    samples: List[Dict[str, Any]] = []
    for frame_id, capture in captures.items():
        server = servers.get(frame_id)
        command = commands.get(frame_id)
        if server is None or command is None:
            continue
        if server.get("command_emitted") is not True:
            continue
        t_capture = capture.get("t_client_capture")
        t_recv = command.get("t_client_cmd_recv")
        e2e = compute_e2e_ms(t_recv, t_capture)
        if e2e is None:
            continue
        http = https.get(frame_id, {})
        samples.append({
            "frame_id": capture.get("frame_id"),
            "run_id": capture.get("run_id"),
            "t_client_capture": t_capture,
            "t_client_cmd_recv": t_recv,
            "e2e_latency_ms": e2e,
            "http_request_ms": compute_http_request_ms(
                http.get("t_client_http_ack"),
                http.get("t_client_http_send"),
            ),
            "total_server_ms": server.get("total_server_ms"),
            "command_emitted": True,
        })
    return samples


def summarize_correlation(
    client_records: Iterable[Dict[str, Any]],
    server_records: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Count submitted / processed / unmatched / matched quantities."""
    client_list = list(client_records)
    server_list = list(server_records)
    captures = _index_by_frame(
        client_list,
        lambda r: r.get("event") == "client_capture" or "t_client_capture" in r,
    )
    commands = _index_by_frame(
        client_list,
        lambda r: r.get("event") == "client_command" or r.get("command_received") is True,
    )
    servers = _index_by_frame(server_list)
    matched = match_e2e_samples(client_list, server_list)
    unmatched_client = [
        fid for fid in captures if fid not in servers
    ]
    return {
        "client_frames_submitted": len(captures),
        "server_frames_processed": len(servers),
        "unmatched_client_frames": len(unmatched_client),
        "commands_received": len(commands),
        "matched_e2e_commands": len(matched),
        "unmatched_client_frame_ids": unmatched_client,
    }


def parse_jsonl_text(text: str) -> List[Dict[str, Any]]:
    """Parse JSONL from a string (tests / in-memory dumps)."""
    records: List[Dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        records.append(json.loads(stripped))
    return records
