# HGRIA Phase 3B — measurement readiness audit

This audit decides whether the repository can run a **local browser
end-to-end** measurement. It is not a results paper. No E2E performance
number is published here.

Classification:

```
READY_FOR_PHASE_3B_MEASUREMENT
```

All required instrumentation items below are present and tested.
A live 3×60 s benchmark has **not** been run.

---

## Checklist

### 1. Is client frame_id generated at capture?

**Yes.** `frontend/js/webcam_capture.js` calls
`ClientMeasurementLog.nextFrameId()` immediately after
`canvas.drawImage` and records `t_client_capture` with that id.

`frontend/js/webcam_bridge.js` is **not** on the live path (see item 13
ownership note). `frontend/index.html` loads `webcam_capture.js`.

### 2. Is frame_id sent with every POST?

**Yes.** The `/api/frame` body is `{ image, frame_id }` via
`HGRIAClientInstrumentation.buildFramePayload`. Omission is still
accepted by the server (Phase 2 contract) but the instrumented client
always includes the id.

### 3. Is frame_id preserved by the server?

**Yes.** Existing path, re-verified:

`POST /api/frame` → `FrameStore.put(..., frame_id=)` →
`CameraModule.capture()` `last_consumed_meta()` →
`PipelineRunner` `timing.frame_id` / `partial["frame_id"]`.

Additive fix only: `/api/frame` is also active when
`camera.browser_source=true` so the local browser path works without
setting `colab_mode`.

### 4. Is server frame_id included in gesture_command?

**Yes.** `Command.to_dict()` already includes `frame_id`. Pipeline emit
tests still assert the payload id matches the captured frame.

### 5. Is client command receive time recorded?

**Yes.** `frontend/js/websocket.js` `gesture_command` handler records
`t_client_cmd_recv = performance.now()` and `data.frame_id` through
`HGRIA_CLIENT_LOG.recordCommandReceive`.

### 6. Are all client timestamps from performance.now()?

**Yes.** Capture, HTTP send, HTTP ack, and command-receive use
`performance.now()` (or an injected clock with the same semantics in
tests). `Date.toISOString()` is written only as `wall_iso` for
correlation. `Date.now()` is not used for latency arithmetic.

### 7. Is E2E defined as capture → matching command receive?

**Yes.**

```
E2E_latency_ms = t_client_cmd_recv - t_client_capture
```

Join is strictly by `frame_id`. See `backend/utils/e2e_matching.py`.
Negative results are rejected. Unmatched frames do not receive a
fabricated `e2e_latency_ms`.

### 8. Is ping RTT excluded?

**Yes.** HUD `Latency` / `GameState.latencyMs` is still computed only
from Socket.IO `pong`. The `gesture_command` handler does not call
`updateLatency`. Client JSONL uses `e2e_latency_ms`, not `latencyMs`.

### 9. Is preview disabled?

**Yes, for a measurement run.** `evaluation.preview_enabled` still
defaults `true` (demo unchanged). The measurement protocol must set
`HGRIA_EVALUATION_PREVIEW_ENABLED=false`. Pipeline already skips
`_maybe_emit_preview` when the flag is false.

### 10. Is evaluation isolation complete?

**Yes.** Unchanged guards:

| Path | Evaluation behaviour |
|---|---|
| UI_BYPASS | skipped when `isEvaluationMode` |
| keyboard | skipped when `isEvaluationMode` |
| `/api/test-emit` | HTTP 403 |
| `_dbgInject` / `_dbgServerEmit` | no-op |
| `enqueueCommand` | rejects DEBUG / KEYBOARD / client_bypass |

### 11. Can client/server JSONL be joined by frame_id?

**Yes.** Client events share `run_id` + `frame_id`. Server rows already
include both. `match_e2e_samples()` joins only on `frame_id` and
requires `command_emitted=true`.

`run_id` is the existing `HGRIA_INSTRUMENTATION_RUN_ID` /
`instrumentation.run_id` value, also placed on `server_info.run_id`.

### 12. Are unmatched frames represented honestly?

**Yes.** Last-write-wins is unchanged. Overwritten FrameStore ids have
client capture/send records and no server processing row. They are
counted as unmatched client frames, not as errors, and they do not
become E2E samples.

### 13. Are recognition semantics unchanged?

**Yes.** No edits to `GESTURE_RULES`, thresholds, MediaPipe,
`smoothing_window_size`, FSM, TemporalFilter, NoiseFilter, cooldown,
CommandGenerator mapping, last-write-wins, or dynamic gestures.

`camera.browser_source` only selects the FrameStore capture strategy.
It does **not** set `colab_mode` and therefore does **not** apply the
Colab JPEG blur divisor. That is existing recognition behaviour.

`frontend/js/webcam_bridge.js` was not modified (owned by
`nobody:nogroup`, mode 0644). Ownership was not changed. The live
capture script is a new file, `webcam_capture.js`, with the same
640×480 / 30 FPS / JPEG 0.7 / un-mirrored draw behaviour plus
instrumentation.

### 14. Are the tests green?

**Yes.**

```
python3 -m pytest tests/ -q --tb=short
182 passed in 1.90s
```

---

## Status

```
READY_FOR_PHASE_3B_MEASUREMENT
```

Not yet run: the controlled 10 s warmup + ≥60 s × 3 measurement.
Do not publish E2E numbers until that protocol completes on a clean
environment (same pins as Phase 3A: Python 3.10.12, OpenCV 4.10.0 from
`opencv-python-headless==4.10.0.84` + `opencv-contrib-python==4.10.0.84`).

---

## Measurement-run requirements (do not skip)

```
HGRIA_EVALUATION_MODE=true
HGRIA_EVALUATION_PREVIEW_ENABLED=false
HGRIA_EVALUATION_STRICT_CAMERA=true
HGRIA_CAMERA_BROWSER_SOURCE=true
HGRIA_INSTRUMENTATION_RUN_ID=<explicit id>
```

`dynamic_gestures.enabled=false` (committed default).

Before starting a timed window, `GET /api/debug` must show:

- `colab_mode=false`
- `colab_fallback=false`
- `browser_source=true`
- `evaluation_mode=true`
- `preview_enabled=false`
- camera target 640×480 / 30 FPS

If `colab_mode` or `colab_fallback` is true, invalidate the run.

Open the local frontend so the **browser webcam** is the frame source.
Do not open the OpenCV device in another process.

---

## Known leftover facts (not blockers)

- This host's user-site `cv2` is currently 4.11.0. A Phase 3B
  measurement must use the Phase 3A clean venv, not this user-site.
- JPEG frames + full blur threshold 30 may yield fewer commands than
  the OpenCV baseline. Do not change the threshold to compensate.
- HTTP request/ack is not one-way upload latency.
- `D − A` is not exact network latency.
