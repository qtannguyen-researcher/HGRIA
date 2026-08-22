Phase 2 is instrumentation only. Recognition, last-write-wins, and `/api/frame` semantics are unchanged.

## 1. Changed files

**New**
- `backend/utils/instrumentation.py` — monotonic clock, `frame_id` sequence, JSONL writer, 1 Hz resource sampler
- `tests/test_instrumentation.py`
- `docs/experiments/instrumentation.md`

**Modified**
- `backend/core/models.py` — additive `Command.frame_id`, `server_emitted_at`
- `backend/core/configuration.py` — `instrumentation` defaults + `is_instrumentation_enabled()`
- `config/config.json` — relative `logs/instrumentation.jsonl`
- `backend/pipeline/camera.py` — server/client `frame_id`, `FrameStore` drop counter
- `backend/pipeline/pipeline_runner.py` — timers around existing calls, JSONL, debug snapshot
- `backend/pipeline/commander.py` — pass `frame_id` through
- `backend/app.py` — optional `frame_id` on `POST /api/frame`
- `backend/routes/health.py` — `/api/debug` counters + latest timing
- `frontend/index.html` — cache-bust `webcam_bridge.js?v=3`
- `tests/test_configuration.py` — instrumentation defaults

**Not changed (permission)**  
`frontend/js/webcam_bridge.js` is root-owned. The server already accepts optional `frame_id` and assigns one if missing. Browser correlation still works via the server-generated ID.

## 2. Instrumentation architecture

Timers wrap existing calls. Recognition code is not restructured.

```
capture → preprocess → MediaPipe → extract → classify → noise → temporal
                                              ↓
                                    cooldown → generate → emit
                                              ↓
                              FrameTiming → JSONL + /api/debug
```

- Durations: `time.perf_counter()` only
- Wall-clock ISO: log correlation only (`timestamp`, `server_emitted_at`)
- Dynamic/ONNX time is not recorded (`enabled=false`)
- JSONL path: `instrumentation.jsonl_path` (default `logs/instrumentation.jsonl`)

## 3. Timestamp definitions

| Timestamp | Where | Clock |
|---|---|---|
| `t_capture` | start of `CameraModule.capture()` | monotonic |
| `t_server_received` | OpenCV: same as `t_capture`; Colab: `FrameStore.put()` | monotonic |
| `t_preprocess_done` | after `FramePreprocessor.process()` | monotonic |
| `t_mediapipe_done` | after `HandDetector.detect()` | monotonic |
| `t_classification_done` | after `GestureClassifier.classify()` | monotonic |
| `t_command_generated` | after `CommandGenerator.generate()` | monotonic |
| `t_command_emitted` | after `socketio.emit("gesture_command")` | monotonic |

`total_server_ms = (t_end − t_server_received) × 1000`  
On Colab, `t_server_received` can be earlier than `t_capture` (HTTP `put` vs later `consume`). That is expected.

## 4. JSONL schema

One object per processed frame. `score` is a rule score, not a probability.

```json
{
  "frame_id": 201,
  "timestamp": "2026-08-22T02:55:37.053+00:00",
  "capture_ms": 0.03,
  "preprocess_ms": 97.88,
  "mediapipe_ms": 0.07,
  "landmark_extraction_ms": 0.02,
  "classification_ms": 0.17,
  "noise_filter_ms": 0.01,
  "temporal_filter_ms": 0.04,
  "command_generation_ms": 0.02,
  "total_server_ms": 102.12,
  "gesture": "closed_fist",
  "score": 0.875,
  "command_emitted": true,
  "dropped_frames": 0,
  "cpu_percent": null,
  "rss_mb": 73.92
}
```

`cpu_percent` / `rss_mb` are a 1 Hz **process** sample copied onto the record (first interval: `cpu_percent` is null). Not system CPU. Not per-frame.

## 5. Tests added

`tests/test_instrumentation.py` (17 tests):

1. Unique `frame_id`; client ID preserved  
2. Monotonic timestamps  
3. Non-negative stage durations  
4. Command payload includes `frame_id` + original fields  
5. `FrameStore` overwrite increments dropped-frame counter  
6. JSONL lines parse  
7. Classification unchanged with timing / enabled vs disabled  

Plus configuration tests for the new defaults.

## 6. Test results

```
python3 -m pytest tests/ -q --tb=short
122 passed in 1.28s
```

(103 Phase 1 + 19 new)

## 7. Smoke-test evidence

Static path, mocked camera/detector, real classifier + filters + command path. Sample: `logs/instrumentation_smoke.jsonl` (3 lines).

| Check | Result |
|---|---|
| Frames processed | 3 (`201`, `202`, `203`) |
| JSONL parse | 3 valid objects |
| Command `frame_id` | `201`, `202`, `203` — matches JSONL |
| Existing command fields | kept; added `frame_id`, `server_emitted_at` |
| Negative `*_ms` | none |
| Classify direct vs timed | `closed_fist` / `0.875` unchanged |
| `/api/debug` | `processed_frames`, `commands_sent`, `dropped_frames`, `latest_timing`, `avg_total_server_ms` — no P50/P95/P99 |

The first-frame `preprocess_ms` (~98 ms) is one-time OpenCV/CLAHE startup in this process, not a measured result.

## 8. Known limitations

- WebSocket ping RTT is **not** end-to-end gesture latency.
- Rule `score` is **not** a calibrated probability.
- JSONL rows are raw observations, not benchmark results. No performance claim.
- `total_server_ms` is server-side only (no client capture, JPEG upload, or HUD apply).
- Preview JPEG encode can sit inside `total_server_ms` and is not a named stage.
- Dropped frames = unread `FrameStore` overwrites only (last-write-wins unchanged).
- `cpu_percent` is process CPU, 1 Hz, can exceed 100% on multi-core. GPU is not measured.
- `webcam_bridge.js` was not edited (root-owned). Server generates `frame_id` if the client omits it.
- `Session.avg_latency_ms` is still unused. Do not report it.

## 9. Exact next step

Use the JSONL + debug counters for a **defined measurement run** (window, hardware block, git SHA). Do **not** start E1, Docker, cloud, Kubernetes, load testing, ONNX, new gestures, or accuracy/F1 until that experiment is specified.