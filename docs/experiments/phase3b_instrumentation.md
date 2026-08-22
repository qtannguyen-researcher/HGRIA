# HGRIA Phase 3B — local browser end-to-end instrumentation

This document describes **how** local browser capture-to-command-receive
latency is measured. It is **not** a results paper.

- JSONL lines are **raw observations**, not benchmark results.
- No performance claim is made in this phase.
- WebSocket ping RTT is **not** end-to-end gesture latency.
- HUD "Latency" remains ping RTT and is not renamed.

Record the git SHA of the tree you actually run:

```bash
git rev-parse HEAD
```

---

## Measurement objective

Instrument the **local browser webcam path**:

```
browser frame capture
    → browser HTTP POST /api/frame
    → server receives / processes frame
    → server emits gesture_command
    → browser receives the matching gesture_command
```

The primary metric is browser end-to-end latency on **one** monotonic clock.

This phase is local only. It does not measure cloud, Docker, Kubernetes,
ngrok-as-a-factor, ONNX, dynamic gestures, load, multi-client, or
accuracy/F1.

---

## Timestamp definitions

| Symbol | Where | Clock | Meaning |
|---|---|---|---|
| `t_client_capture` | After `canvas.drawImage` of the webcam frame | `performance.now()` | Browser has the frame that will be posted |
| `t_client_http_send` | Immediately before `fetch('/api/frame')` | `performance.now()` | Browser starts the HTTP request |
| `t_client_http_ack` | Immediately after `fetch` resolves | `performance.now()` | Browser has the HTTP response (204 ack) |
| `t_server_received` | `FrameStore.put()` | `time.perf_counter()` | Server first sighting of JPEG bytes |
| `t_capture` | Start of `CameraModule.capture()` | `time.perf_counter()` | Server begins consuming the stored frame |
| stage `t_*` / `*_ms` | Existing Phase 2 pipeline timers | `time.perf_counter()` | Unchanged |
| `t_command_emitted` | After `socketio.emit('gesture_command')` | `time.perf_counter()` | Server emit call returned |
| `t_client_cmd_recv` | Socket.IO `gesture_command` handler | `performance.now()` | Browser received the matching command |

Wall-clock ISO-8601 (`wall_iso` on the client, JSONL `timestamp` on the
server) is **correlation only**. It is never subtracted.

### Clock domains (non-negotiable)

`performance.now()` is only compared with `performance.now()` within the
same browser process.

`server perf_counter()` is not subtracted from browser `performance.now()`.
Those clocks are process-local and cannot be compared.

Ping RTT is not E2E latency.

---

## frame_id lifecycle

```
1. WebcamBridge (webcam_capture.js) assigns a monotonically increasing
   client integer via ClientMeasurementLog.nextFrameId() at capture.
2. POST /api/frame body is { image, frame_id }.
3. receive_frame() stores the optional frame_id on FrameStore.put().
4. CameraModule.capture() reads last_consumed_meta() and keeps that id
   (server generates an id only if the client omitted one).
5. PipelineRunner copies frame.frame_id onto FrameTiming and onto the
   CommandGenerator partial.
6. Command.to_dict() includes frame_id in the gesture_command payload.
7. Browser gesture_command handler records data.frame_id + t_client_cmd_recv.
```

`frontend/js/webcam_bridge.js` is **not** on the live path. It is owned by
`nobody:nogroup` (mode 0644) and was left untouched to avoid chown/chmod.
`frontend/index.html` loads `webcam_capture.js` instead. Capture geometry
and JPEG quality are unchanged (640×480, 30 FPS target, JPEG quality 0.7,
un-mirrored draw).

---

## Client JSONL schema

Path: `instrumentation.client_jsonl_path`
(default `logs/client_instrumentation.jsonl`).

The browser writes **separate event records** that share `run_id` and
`frame_id`. Fields are omitted when they do not apply. A frame that never
receives a command is **not** turned into an E2E sample.

```json
{"event":"client_capture","run_id":"...","frame_id":123,"t_client_capture":12345.67,"wall_iso":"2026-08-22T00:00:00.000Z"}
```

```json
{"event":"client_http","run_id":"...","frame_id":123,"t_client_http_send":12346.10,"t_client_http_ack":12378.22,"http_request_ms":32.12,"wall_iso":"..."}
```

```json
{"event":"client_command","run_id":"...","frame_id":123,"t_client_cmd_recv":12410.55,"t_client_capture":12345.67,"e2e_latency_ms":64.88,"command_received":true,"wall_iso":"..."}
```

`e2e_latency_ms` is present on a `client_command` row **only** when a
same-`frame_id` capture timestamp exists and
`t_client_cmd_recv - t_client_capture >= 0`.

Records are buffered in `window.HGRIA_CLIENT_LOG` and POSTed to
`/api/client-log`, which appends them with the existing `ExperimentLogger`.

`run_id` is the existing `instrumentation.run_id` /
`HGRIA_INSTRUMENTATION_RUN_ID` value, delivered via `server_info.run_id`
and `/api/debug.instrumentation.run_id`. A second run-identity system is
not used.

---

## Server JSONL schema used

Unchanged Phase 2/3A server observations. Correlation fields:

| Field | Use |
|---|---|
| `frame_id` | Join key |
| `run_id` | Same configured run identity |
| `command_emitted` | Must be `true` for a valid E2E sample |
| `total_server_ms` | Server processing latency (metric A) |
| stage `*_ms` | Existing stage timings |

Server `t_*` values stay on the server clock and are **not** used in the
E2E subtraction.

---

## Matching rules

A valid E2E sample requires **all** of:

1. A client capture record exists for `frame_id`
2. A server JSONL row exists for the same `frame_id`
3. That server row has `command_emitted=true`
4. The browser received `gesture_command`
5. The command `frame_id` equals the capture `frame_id`

Then:

```
E2E_latency_ms = t_client_cmd_recv - t_client_capture
```

Do **not**:

- infer missing IDs
- match by nearest timestamp
- match by row number
- match by gesture name
- use server wall-clock timestamps for E2E arithmetic
- subtract `perf_counter()` from `performance.now()`

Unmatched client frames (last-write-wins overwrites, no command, no
server row) remain in the client log. They are counted, not converted
into errors.

Quantities that must stay distinct:

- client frames submitted
- server frames processed
- unmatched client frames
- commands received
- matched E2E commands

Helper: `backend/utils/e2e_matching.py`.

---

## HTTP request/ack definition

```
http_request_ms = t_client_http_ack - t_client_http_send
```

This is **browser HTTP request/ack latency**.

It is **not**:

- one-way network latency
- pure upload latency
- JPEG encode time (encode is before `t_client_http_send`)

The server replies `204` with an empty body. The interval includes
browser request handling and server response time.

---

## E2E definition

```
E2E_latency_ms = t_client_cmd_recv - t_client_capture
```

Same browser process, same `performance.now()` clock, matching `frame_id`.

Report separately:

| Label | Metric | Formula |
|---|---|---|
| A | server processing latency | existing `total_server_ms` |
| B | browser HTTP request/ack latency | `t_client_http_ack - t_client_http_send` |
| D | browser E2E capture→command-receive | `t_client_cmd_recv - t_client_capture` |

`D − A` is **not** exact network latency. The intervals overlap and the
HTTP acknowledgement path is not identical to the frame's one-way upload
path. Do not report that difference unless it is clearly labelled as an
approximation.

---

## Exclusions

Not measured / not claimed:

- cloud latency
- Docker / Kubernetes
- ngrok/tunnel as an experimental factor
- ONNX / dynamic gestures
- load testing / multi-client
- recognition accuracy / F1
- ping RTT (HUD Latency)
- `Session.avg_latency_ms`

---

## Evaluation isolation

A measurement run must use:

```
HGRIA_EVALUATION_MODE=true
HGRIA_EVALUATION_PREVIEW_ENABLED=false
HGRIA_EVALUATION_STRICT_CAMERA=true
HGRIA_CAMERA_BROWSER_SOURCE=true
```

and `dynamic_gestures.enabled=false`.

Existing guards (unchanged):

- `UI_BYPASS` is skipped when `isEvaluationMode`
- keyboard injection is skipped when `isEvaluationMode`
- `/api/test-emit` returns 403
- `_dbgInject` / `_dbgServerEmit` no-op
- `enqueueCommand` rejects `DEBUG`, `KEYBOARD`, and `_source=client_bypass`

Do not start the debug panel in a way that injects commands.

Preview remains disabled via `HGRIA_EVALUATION_PREVIEW_ENABLED=false`.
Committed demo defaults are unchanged (`preview_enabled=true`).

---

## Local browser capture vs Colab fallback

Phase 3A used OpenCV (`colab_mode=false`). Phase 3B needs the browser
JPEG POST path **without** silent Colab fallback.

`camera.browser_source` (env `HGRIA_CAMERA_BROWSER_SOURCE`) selects
`FrameStore` / `POST /api/frame` **without** setting `colab_mode` or
`colab_fallback`. Default is `false`, so Phase 3A OpenCV semantics are
unchanged.

`GET /api/debug` must report:

- `colab_mode=false`
- `colab_fallback=false`
- `browser_source=true` (Phase 3B measurement only)

If `colab_mode` or `colab_fallback` is true, the run is invalid.

`evaluation.strict_camera=true` still refuses OpenCV→Colab fallback.
When `browser_source=true` the process does not open the OpenCV device,
so the browser can hold `/dev/video0`.

NoiseFilter blur reduction (`threshold // 4`) remains gated on
`colab_mode` only. Phase 3B therefore uses the full blur threshold (30)
on JPEG frames. That is existing recognition behaviour, not a threshold
change.

---

## Known limitations

1. `webcam_bridge.js` could not be edited (owned by `nobody:nogroup`).
   The live path is `webcam_capture.js`.
2. HTTP request/ack is not one-way upload latency.
3. `D − A` is not exact network latency.
4. Last-write-wins still drops unread FrameStore frames; those IDs have
   client records and no server processing records.
5. JPEG blur scores are typically lower than raw OpenCV frames; with
   `colab_mode=false` the full blur threshold applies.
6. `performance.now()` is not comparable across browser processes or to
   `perf_counter()`.
7. Ping RTT / HUD Latency is still a different metric.
8. No live 3×60 s benchmark is published in this phase.

---

## Exact next step

Only after `docs/experiments/phase3b_measurement_readiness.md` says
`READY_FOR_PHASE_3B_MEASUREMENT`: run the controlled local browser E2E
protocol (warmup + measurement window, 3 process restarts). Do not start
cloud, Docker, Kubernetes, ONNX, scalability, or accuracy work.
