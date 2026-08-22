# PHASE_3B_INSTRUMENTATION_RESULT

## 1. Status

**READY_FOR_PHASE_3B_MEASUREMENT**

Instrumentation, tests, and the readiness audit are complete. No live E2E numbers were collected. The 3×60 s benchmark was not run.

Audit: `docs/experiments/phase3b_measurement_readiness.md`

## 2. Changes

**Changed**
- `backend/app.py` — `/api/frame` also accepts frames when `browser_source=true`; added `POST /api/client-log`
- `backend/core/configuration.py` — `camera.browser_source` (default `false`), `instrumentation.client_jsonl_path`
- `backend/pipeline/camera.py` — explicit FrameStore path when `browser_source=true` (does not set `colab_mode` / `colab_fallback`)
- `backend/pipeline/pipeline_runner.py` — expose `client_jsonl_path` on debug snapshot
- `backend/routes/health.py` — report `browser_source`; diagnose empty FrameStore on that path
- `backend/utils/instrumentation.py` — client JSONL helper; sidecar field `browser_source`
- `backend/websocket/handlers.py` — `server_info.run_id` from existing run-id mechanism
- `frontend/index.html` — load instrumented capture scripts
- `frontend/js/state.js` — store/apply `run_id`
- `frontend/js/websocket.js` — record command-receive time (does not touch ping RTT)
- `tests/test_configuration.py` — browser_source / client JSONL defaults

**Added**
- `frontend/js/client_instrumentation.js`
- `frontend/js/webcam_capture.js`
- `backend/utils/e2e_matching.py`
- `tests/js/test_client_instrumentation.js`
- `tests/test_phase3b_instrumentation.py`
- `docs/experiments/phase3b_instrumentation.md`
- `docs/experiments/phase3b_measurement_readiness.md`

**Not modified (intentional)**
- `frontend/js/webcam_bridge.js` — owned by `nobody:nogroup`, mode `0644`, `test -w` = not writable. Ownership was not changed. Live path is `webcam_capture.js` (same 640×480 / 30 FPS / JPEG 0.7 / un-mirrored draw, plus frame_id and clocks).
- `config/config.json`, `requirements.txt`, `GESTURE_RULES`, thresholds, MediaPipe, filters, FSM, cooldown, command map, dynamic/ONNX code.

## 3. Timestamp model

```
capture          t_client_capture      performance.now()   (same browser process)
    →
HTTP send        t_client_http_send    performance.now()
    →
HTTP ack         t_client_http_ack     performance.now()   (204 response)
    →
server receive   t_server_received     time.perf_counter() (FrameStore.put)
    →
server process   stage t_* / *_ms      time.perf_counter() (existing Phase 2)
    →
server emit      t_command_emitted     time.perf_counter()
    →
browser recv     t_client_cmd_recv     performance.now()   (same browser process)
```

`performance.now()` is only compared with `performance.now()` in the same browser process.  
`server perf_counter()` is not subtracted from browser `performance.now()`.  
Wall-clock ISO is correlation only.

## 4. frame_id trace

1. `webcam_capture.js` assigns a monotonically increasing client integer at `drawImage`.
2. `POST /api/frame` body is `{ image, frame_id }`.
3. `receive_frame()` stores it on `FrameStore.put()`.
4. `CameraModule.capture()` reuses `last_consumed_meta()` (server generates an id only if the client omitted one).
5. `PipelineRunner` copies `frame.frame_id` onto timing and the command partial.
6. `Command.to_dict()` includes `frame_id` in `gesture_command`.
7. Browser handler records `data.frame_id` + `t_client_cmd_recv`.

Last-write-wins is unchanged: overwritten ids stay in the client log and have no fabricated server row.

## 5. JSONL schema

**Client** (`logs/client_instrumentation.jsonl`, separate events, shared `run_id` + `frame_id`):

| event | fields |
|---|---|
| `client_capture` | `run_id`, `frame_id`, `t_client_capture`, `wall_iso` |
| `client_http` | `run_id`, `frame_id`, `t_client_http_send`, `t_client_http_ack`, `http_request_ms` |
| `client_command` | `run_id`, `frame_id`, `t_client_cmd_recv`, `command_received`; `e2e_latency_ms` only if a matching capture exists and E2E ≥ 0 |

**Server** (existing file): `frame_id`, `run_id`, `command_emitted`, `total_server_ms`, stage `*_ms`.

Join key: `frame_id`. Same `HGRIA_INSTRUMENTATION_RUN_ID` / `instrumentation.run_id` on both sides.

## 6. E2E formula

```
E2E_latency_ms = t_client_cmd_recv - t_client_capture
```

A sample is valid only if all of these hold:

1. client capture record exists  
2. server row exists for that `frame_id`  
3. server `command_emitted=true`  
4. browser received `gesture_command`  
5. command `frame_id` equals capture `frame_id`  

No nearest-timestamp, row-number, or gesture-name matching. Negative E2E is rejected. Unmatched frames are not fabricated into E2E.

## 7. HTTP metric

```
http_request_ms = t_client_http_ack - t_client_http_send
```

This is **browser HTTP request/ack latency**. It is not one-way network latency and not pure upload latency. The server returns an empty 204. The interval includes browser request handling and server response time.

Report separately: **A** = `total_server_ms`, **B** = HTTP request/ack, **D** = E2E above. `D − A` is not exact network latency.

## 8. Evaluation isolation

Unchanged and re-tested:

- `UI_BYPASS` skipped when `isEvaluationMode`
- keyboard injection skipped when `isEvaluationMode`
- `/api/test-emit` → 403
- `_dbgInject` / `_dbgServerEmit` no-op
- `enqueueCommand` rejects `DEBUG`, `KEYBOARD`, `_source=client_bypass`

Preview off for a run: `HGRIA_EVALUATION_PREVIEW_ENABLED=false` (demo default still `true`).

## 9. Recognition invariance

No edits to `GESTURE_RULES`, thresholds, MediaPipe, smoothing, FSM, filters, cooldown, command map, or last-write-wins.  
`browser_source` only selects the capture strategy. The Colab JPEG blur divisor remains gated on `colab_mode` only.  
`test_phase3b_instrumentation.py` asserts the nine static rule names and that `time_call` does not change `classify()` output.

## 10. Tests

```
python3 -m pytest tests/ -q --tb=short
182 passed in 1.90s
```

## 11. Known limitations

- `webcam_bridge.js` could not be edited without chown/chmod; the live file is `webcam_capture.js`.
- HTTP request/ack is not one-way upload latency.
- `D − A` is not exact network latency.
- Last-write-wins still drops unread FrameStore frames (honest unmatched client ids).
- With `colab_mode=false`, JPEG frames use blur threshold 30 (not `30/4`). That may reduce command rate versus Colab. Thresholds were not changed.
- This process currently loads user-site `cv2` **4.11.0**. Requirements still pin **4.10.0.84**. A measurement run must use the Phase 3A clean venv.
- `config/config.json` was not edited. Live merged config SHA includes new default-false keys (`browser_source`, `client_jsonl_path`).
- No E2E performance numbers yet.

## 12. Exact next step

Controlled Phase 3B measurement only (local browser E2E). Do not start cloud, Docker, Kubernetes, ONNX, scalability, or accuracy work.

**Environment** (same pins as Phase 3A): Python 3.10.12, `opencv-python-headless==4.10.0.84`, `opencv-contrib-python==4.10.0.84`, clean venv, `dynamic_gestures.enabled=false`.

**Env (do not change committed `config.json`):**

```
HGRIA_EVALUATION_MODE=true
HGRIA_EVALUATION_PREVIEW_ENABLED=false
HGRIA_EVALUATION_STRICT_CAMERA=true
HGRIA_CAMERA_BROWSER_SOURCE=true
HGRIA_INSTRUMENTATION_RUN_ID=phase3b-local-browser-<sha>-rN
HGRIA_INSTRUMENTATION_JSONL_PATH=docs/experiments/run_<sha>_rN/instrumentation.jsonl
HGRIA_INSTRUMENTATION_CLIENT_JSONL_PATH=docs/experiments/run_<sha>_rN/client_instrumentation.jsonl
```

**Before each timed window**
1. Confirm `GET /api/debug`: `colab_mode=false`, `colab_fallback=false`, `browser_source=true`, `evaluation_mode=true`, `preview_enabled=false`, 640×480 / 30 FPS.
2. Confirm the **browser webcam** is the frame source (server must not hold `/dev/video0` via OpenCV).
3. If Colab fallback occurred, invalidate the run.
4. Open `/?evaluation=true` against the local server. Do not use the debug panel.

**Protocol:** 3 independent process restarts; 10 s warmup discarded; ≥60 s measurement; ≥1000 client-submitted frames recorded; report A / B / D plus submitted / processed / unmatched / commands-received / matched-E2E counts. Join only by `frame_id`. Do not publish ping RTT as E2E.

---

**Reproducibility (this instrumentation tree)**

| Item | Value |
|---|---|
| git HEAD | `b7737bffb73bcb950faf01778c34237b8538e0d3` (Phase 3B files uncommitted) |
| Frozen Phase 3A SHA | `4be769ca6a0ffe02611a236b7cc4eac199c6c04c` (semantics not changed) |
| Live config SHA-256 | `7775c84ff4328cc83b2a817d1ed92131e71c2367627c9e3b6bade766ff4a150f` |
| Python | 3.10.12 |
| OpenCV in this process | 4.11.0 (user-site; **not** the measurement venv) |
| Requirements pins | `opencv-python-headless==4.10.0.84`, `opencv-contrib-python==4.10.0.84`, `mediapipe==0.10.14`, `numpy==1.26.4`, `scipy==1.15.3`, `flask==3.0.3` |
| Tests | 182 passed |
| Readiness | `READY_FOR_PHASE_3B_MEASUREMENT` |