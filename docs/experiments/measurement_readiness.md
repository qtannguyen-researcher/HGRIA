# HGRIA Pre-Phase 3 — measurement readiness

This document records the instrumentation/evaluation hardening that makes
the repository safe to run the first controlled Phase 3 measurement.

It is **not** a results paper. No latency, throughput, cloud, or scalability
number is claimed here.

---

## 1. Purpose

Close the gaps that would contaminate or invalidate an A-only local OpenCV
server-processing baseline:

- preview JPEG encode/emit inside `total_server_ms` with no off switch
- no per-frame `exit_reason`
- `_dbgInject` not gated by evaluation mode
- silent `colab_mode=true` camera fallback
- JSONL lacking run identity
- conflicting OpenCV distributions
- accidental ONNX/dynamic load
- `ConfigurationManager.get()` `or default` swallowing `false` / `0`

---

## 2. Scope

In scope: configuration flags, preview emission, JSONL fields, run sidecar,
evaluation-mode injection guards, camera fallback observability, OpenCV
dependency specification, tests, this document.

Out of scope (deliberately not done):

- Phase 3 benchmark (no 10 s warmup + 60 s measurement, no 3-repetition run)
- E1 corpus capture
- browser E2E / cloud / ngrok / Docker / Kubernetes / load testing
- enabling ONNX or `dynamic_gestures`
- new gestures, `GESTURE_RULES`, thresholds, smoothing, MediaPipe knobs, FSM,
  last-write-wins, or command mapping
- recognition-pipeline optimization
- accuracy/F1 dataset
- changing the frozen experimental protocol except where this checkout’s
  instrumentation contract needed additive fields

---

## 3. Changes made

| Area | Change |
|---|---|
| Preview | `evaluation.preview_enabled` (default `true`). When `false`, `_maybe_emit_preview` is not called; no JPEG encode, no `frame_preview` emit. |
| `exit_reason` | Recorded on `FrameTiming` / JSONL at the pipeline decision that ended the frame. |
| Evaluation isolation | `_dbgInject` / `_dbgServerEmit` no-op in evaluation mode; `enqueueCommand` rejects `DEBUG`, `KEYBOARD`, and `_source=client_bypass`. `/api/test-emit` remains 403. |
| Camera | `camera.colab_fallback` set on silent OpenCV→browser fallback. `/api/debug` reports `colab_mode`, `colab_fallback`, `strict_camera`. `evaluation.strict_camera=true` re-raises instead of falling back. |
| Run identity | `instrumentation.run_id` (or `HGRIA_INSTRUMENTATION_RUN_ID`, or generated UUID). Sidecar `*.run.json` next to the JSONL. `run_id` also copied onto each JSONL row. |
| OpenCV spec | `requirements.txt` pins **both** `opencv-python-headless==4.10.0.84` and `opencv-contrib-python==4.10.0.84` (MediaPipe requires contrib). |
| Config helpers | `is_preview_enabled()`, `is_strict_camera()`, `run_id()` use dict lookup, not `get()`. |

---

## 4. Changes deliberately NOT made

- `ConfigurationManager.get()` still uses `value or default`. Unused for
  baseline/measurement flags. Documented, not refactored.
- Colab/browser capture path is still present. Fallback still happens unless
  `strict_camera` is true.
- Preview functionality is not removed.
- Dynamic/ONNX code is not deleted or loaded.
- `webcam_bridge.js` still does not send `frame_id` (server assigns one).
- No environment uninstall/reinstall on this machine.
- Frozen protocol documents were not rewritten. Phase 2 instrumentation.md
  points here for the additive fields.

---

## 5. Frozen baseline values

These must remain for the Phase 3 A-only OpenCV baseline:

| Setting | Value |
|---|---|
| Recognition path | static MediaPipe + `GESTURE_RULES` |
| `dynamic_gestures.enabled` | `false` |
| MediaPipe detection / tracking confidence | `0.5` / `0.5` |
| `max_num_hands` | `1` |
| `model_complexity` | `0` |
| `smoothing_window_size` | `3` |
| `noise_filter_blur_threshold` | `30` |
| `confidence_threshold` | `0.75` |
| Capture | OpenCV `VideoCapture` |
| `colab_mode` | `false` |
| Resolution / FPS | 640×480 / 30 |
| `evaluation.mode` | available; **true for a measurement run** |
| `scipy` | `1.15.3` |

Demo defaults in committed `config/config.json` stay demo-safe
(`evaluation.mode=false`, `preview_enabled=true`, `strict_camera=false`).
A measurement run must override the evaluation flags (config or `HGRIA_*`).

---

## 6. Preview semantics

**Option B.**

- When `evaluation.preview_enabled` is `true` (demo default): JPEG encode +
  `frame_preview` emit still run inside `_process_frame`, so they remain
  **inside** `total_server_ms`. They are not a named stage.
- When `evaluation.preview_enabled` is `false`: `_maybe_emit_preview` is
  not entered. Encode and emit are **completely absent**. They do not
  contribute to `total_server_ms` because they do not run.

Phase 3 baseline **must** set `preview_enabled=false`
(`HGRIA_EVALUATION_PREVIEW_ENABLED=false`).

`total_server_ms` is still `(t_end − t_server_received) × 1000` from
`FrameTiming.finish()` in the `finally` of `_process_frame`.

---

## 7. `exit_reason` semantics

One value per processed JSONL row (capture succeeded). Recorded at the
decision, not inferred later from timings. `command_emitted` remains
authoritative for whether a command was emitted.

| Value | Meaning |
|---|---|
| `no_hand` | MediaPipe returned no hand. |
| `noise` | `NoiseFilter` rejected the classification. |
| `temporal` | `TemporalFilter` returned `UNKNOWN` (held / no majority). |
| `cooldown` | A valid command candidate was suppressed by cooldown. |
| `unmapped` | A gesture existed but `CommandGenerator.generate` raised (not in `COMMAND_MAP`). |
| `command` | A command was generated and emitted. |

**Existing branch that does not invent a seventh category**

If MediaPipe returns a detection but `LandmarkExtractor.extract_all` returns
an empty list, no classification occurs. The current extractor always
builds one `Landmark` per raw detection, so this is unreachable. If it
were reached, `exit_reason` is recorded as `no_hand` (no classification).

**Null `exit_reason`**

If `HandDetector.detect` raises, `_process_frame` still writes a JSONL row
from `finally` (existing Phase 2 behaviour). No listed category fits;
`exit_reason` stays `null`. `command_emitted` is false.

---

## 8. Evaluation-mode isolation

When `evaluation.mode` is true (config, `HGRIA_EVALUATION_MODE=true`,
and/or frontend `?evaluation=true|1|yes`):

| Path | Behaviour |
|---|---|
| `window._dbgInject` | No-op; logs `blocked: evaluation mode`. |
| `window._dbgServerEmit` | No-op; server would also 403. |
| Keyboard injection | Still gated by `isEvaluationMode` in `main.js`. |
| `UI_BYPASS` | Still gated in `websocket.js`. |
| `GameState.enqueueCommand` | Rejects `DEBUG`, `KEYBOARD`, `_source=client_bypass`. Real `gesture_command` (`MOVE` / `ACTION` / `UI` / `SYSTEM`) is allowed. |
| `GET/POST /api/test-emit` | HTTP 403. |

Demo/default (`evaluation.mode=false`) is unchanged: debug inject,
keyboard fallback, UI bypass, and `/api/test-emit` still work.

---

## 9. Run metadata schema

Static metadata is written once at `PipelineRunner` init, next to the JSONL:

```
logs/instrumentation.jsonl  →  logs/instrumentation.run.json
```

(`sidecar_path_for`: same stem + `.run.json`.)

```json
{
  "schema": "hgria.run_metadata.v1",
  "run_id": "phase3-a-local-001",
  "created_at": "2026-08-22T03:00:00.000+00:00",
  "git_sha": "<rev-parse HEAD or null>",
  "config_sha256": "<sha256 of live config._data>",
  "python": "3.10.12",
  "cwd": "<process cwd>",
  "jsonl_path": "logs/instrumentation.jsonl",
  "deployment_path": "local_opencv_server",
  "preview_enabled": false,
  "evaluation_mode": true,
  "strict_camera": true,
  "colab_mode": false,
  "colab_fallback": false,
  "dynamic_gestures_enabled": false,
  "instrumentation_enabled": true,
  "opencv": {
    "cv2_version": "4.10.0",
    "cv2_file": ".../cv2/__init__.py",
    "distributions": {
      "opencv-python": null,
      "opencv-python-headless": "4.10.0.84",
      "opencv-contrib-python": "4.10.0.84"
    }
  },
  "packages": {
    "mediapipe": "0.10.14",
    "numpy": "1.26.4",
    "scipy": "1.15.3",
    "onnxruntime": "1.17.1",
    "flask": "3.0.3"
  },
  "validity": {
    "opencv_baseline_invalid_if_colab_mode": true,
    "note": "A copied log is identified by run_id + this sidecar. If colab_mode is true the run is not a local OpenCV baseline."
  }
}
```

Each JSONL row also contains `run_id` (and `exit_reason`) so a copied line
can still be associated with the sidecar.

Supply `run_id` explicitly:

- `"instrumentation": { "run_id": "phase3-a-local-001" }`
- or `HGRIA_INSTRUMENTATION_RUN_ID=phase3-a-local-001`

If empty, a UUID is generated at pipeline start (not written back to config).

---

## 10. OpenCV dependency status

**What this machine loaded during the audit (do not hide):**

| Item | Value |
|---|---|
| `opencv-python` | not installed |
| `opencv-python-headless` | 4.10.0.84 |
| `opencv-contrib-python` | 4.11.0.86 |
| `import cv2` version | **4.11.0** |
| `cv2.__file__` | `/home/qtannguyen/.local/lib/python3.10/site-packages/cv2/__init__.py` |

`mediapipe==0.10.14` **requires** `opencv-contrib-python` (unpinned by
MediaPipe). HGRIA’s static path only uses core `cv2` APIs. Both packages
export the `cv2` namespace; the loaded module was contrib 4.11.0.

**Repository spec after this hardening**

`requirements.txt` now pins both distributions to the baseline version:

```
opencv-python-headless==4.10.0.84
opencv-contrib-python==4.10.0.84
```

Do not also install `opencv-python`. Do not leave contrib unpinned.

This task did **not** uninstall or downgrade packages in the live
user site-packages (that would be a broad environment change). A clean
venv installed from the updated `requirements.txt` is the intended
measurement environment.

**Blocker if Phase 3 is run on this machine without a clean venv:**
loaded `cv2` will still be 4.11.0 from contrib. Record that in the sidecar
(`opencv.cv2_version`) and treat the run as not matching the pinned
OpenCV version. Recreate the venv before a defensible A-only result.

---

## 11. Camera / Colab validity rule

- Configured `camera.colab_mode=false` is required for the OpenCV baseline.
- If OpenCV `VideoCapture` fails to open and `evaluation.strict_camera` is
  false, the process **falls back** to browser JPEG POST and sets
  `colab_mode=true` **and** `colab_fallback=true`.
- **The run is invalid as a local OpenCV baseline if `colab_mode` is true**,
  whether that was configured or caused by fallback.
- `GET /api/debug` reports `config.colab_mode`, `config.colab_fallback`,
  `config.strict_camera`, and `config.opencv_baseline_invalid_if_colab_mode`.
- For measurement, set `evaluation.strict_camera=true` so a missing camera
  fails loudly instead of silently becoming a Colab/browser run.

Colab support is not removed.

---

## 12. Test results

```
python3 -m pytest tests/ -q --tb=short
154 passed in 1.78s
```

No test was deleted or weakened. New coverage includes preview on/off,
every `exit_reason`, evaluation injection (`_dbgInject`, keyboard/UI
source guards, `/api/test-emit` 403), run metadata, camera fallback /
strict camera, dynamic path still off, baseline config values, and
recognition invariance (instrumentation on/off and preview on/off).

No benchmark was run. JSONL written by tests is schema smoke only.

---

## 13. Known remaining risks

| Issue | Why it remains | Blocks A-only local server-processing? | Blocks E2E / cloud / scalability? |
|---|---|---|---|
| Live site-packages still load `cv2` 4.11.0 from contrib | Did not mutate the user environment | **Yes, on this machine, until a clean venv matches the pins** | Yes (same env) |
| `ConfigurationManager.get()` swallows `false`/`0` | Unused by baseline/measurement helpers; not refactored | No | No |
| Preview encode still inside `total_server_ms` when enabled | Smallest change; disable for measurement | No if `preview_enabled=false` | N/A |
| `webcam_bridge.js` omits `frame_id` | Not required for A-only server IDs | No | Yes for client-correlated E2E |
| No client capture / HUD / network timers | Phase 2/3 A-only is server-side only | No | Yes — E2E not instrumented |
| No Docker / K8s / cloud / ngrok measurement harness | Out of scope | No | Yes |
| MediaPipe `Hands(static_image_mode=False)` is stateful | Existing | Does not invalidate A-only if documented | — |
| Detect-exception JSONL row has `exit_reason=null` | Existing `finally` write | No (rare) | — |
| Env overrides only split on first `_` | Existing | No if using the documented `HGRIA_*` keys below | — |

---

## 14. Exact Phase 3 entry criteria

| Criterion | Status |
|---|---|
| Static path remains unchanged | Yes |
| `dynamic_gestures.enabled=false` | Yes |
| ONNX not loaded in baseline | Yes (regression test) |
| Preview can be explicitly disabled | Yes |
| `exit_reason` exists and is correct | Yes |
| Evaluation mode blocks artificial command injection | Yes |
| `/api/test-emit` returns 403 in evaluation | Yes |
| `_dbgInject` cannot inject in evaluation | Yes |
| Camera / Colab state is observable | Yes |
| Run identity can be recorded | Yes |
| OpenCV dependency situation understood and specified | Yes in repo spec; **live env still mismatched until venv recreate** |
| All tests pass | Yes (154) |
| No benchmark has been run | Yes |
| Measurement protocol remains documented | Yes |
| No E2E / cloud / scalability claims | Yes |

**Verdict:** `READY_FOR_PHASE_3` for an **A-only local OpenCV
server-processing** measurement, after the researcher confirms `import cv2`
matches the 4.10.0.84 pins (clean venv recommended).

Not ready for local browser E2E, cloud, or scalability experiments.

---

## Phase 3 measurement overrides (do not commit as new defaults)

```bash
export HGRIA_EVALUATION_MODE=true
export HGRIA_EVALUATION_PREVIEW_ENABLED=false
export HGRIA_EVALUATION_STRICT_CAMERA=true
export HGRIA_INSTRUMENTATION_RUN_ID=phase3-a-local-001
```

Confirm `GET /api/debug` shows:

- `config.colab_mode` = false
- `config.colab_fallback` = false
- `config.preview_enabled` = false
- `config.evaluation_mode` = true
- `config.dynamic_gestures_enabled` = false

If `colab_mode` is true, discard the run.
