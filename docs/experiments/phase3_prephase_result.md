# Pre-Phase 3 Result

## Status

**READY_FOR_PHASE_3** for an A-only local OpenCV server-processing baseline, after the researcher confirms `import cv2` matches the pinned 4.10.0.84 distributions (this machine currently does not — see OpenCV below).

Not ready for local browser E2E, cloud, or scalability.

## Files changed

- `backend/core/configuration.py`
- `backend/pipeline/camera.py`
- `backend/pipeline/pipeline_runner.py`
- `backend/routes/health.py`
- `backend/utils/instrumentation.py`
- `config/config.json`
- `docs/experiments/phase2_instrumentation.md`
- `frontend/index.html`
- `frontend/js/config.js`
- `frontend/js/state.js`
- `requirements.txt`
- `tests/test_configuration.py`
- `tests/test_pipeline_baseline.py`

## Files added

- `docs/experiments/measurement_readiness.md`
- `tests/test_measurement_readiness.py`

(`dynamic_gestures/` was already untracked and was not added or modified.)

## Behavior changes

Intentional only:

1. **Preview switch.** `evaluation.preview_enabled` defaults to `true` (demo unchanged). When `false`, JPEG encode and `frame_preview` emit do not run.
2. **`exit_reason`** is written on every processed JSONL row at the decision point.
3. **Evaluation isolation.** `_dbgInject` / `_dbgServerEmit` are no-ops in evaluation mode. `enqueueCommand` rejects `DEBUG`, `KEYBOARD`, and `_source=client_bypass`. `/api/test-emit` still returns 403.
4. **Camera observability.** Fallback still exists, but sets `camera.colab_fallback=true` and is reported on `/api/debug`. `evaluation.strict_camera=true` re-raises instead of falling back.
5. **Run identity.** `instrumentation.run_id` (or `HGRIA_INSTRUMENTATION_RUN_ID`, or a generated UUID) is stored in a sidecar and copied onto each JSONL row.
6. **OpenCV spec.** `requirements.txt` now pins both `opencv-python-headless` and `opencv-contrib-python` to `4.10.0.84` (MediaPipe requires contrib).

Recognition, `GESTURE_RULES`, thresholds, smoothing, MediaPipe knobs, FSM, last-write-wins, and command mapping were not changed.

## Recognition invariance

Verified with mocked frames:

- classifier output identical with instrumentation enabled vs disabled
- gesture, `command_emitted`, and `exit_reason` identical with preview enabled vs disabled
- same two-frame sequence produces the same gesture/command/`exit_reason` decisions with instrumentation on and off
- committed baseline values still match `config/config.json` / `DEFAULTS`
- `dynamic_gestures.enabled=false` still does not construct `DynamicGestureRecognizer`

## Preview

`evaluation.preview_enabled` (default `true`).

**Option B:** when preview is enabled, JPEG encode remains **inside** `total_server_ms` (still not a named stage). When disabled, encode/emit are **completely absent** and cannot contribute to `total_server_ms`.

Phase 3 must set `HGRIA_EVALUATION_PREVIEW_ENABLED=false`.

## Exit reasons

| Value | Meaning |
|---|---|
| `no_hand` | MediaPipe found no hand |
| `noise` | Noise filter rejected the classification |
| `temporal` | Temporal filter held / returned `UNKNOWN` |
| `cooldown` | Valid candidate suppressed by cooldown |
| `unmapped` | Gesture existed but no command mapping |
| `command` | Command generated and emitted |

`command_emitted` remains authoritative. An empty extract after a MediaPipe hit is unreachable with the current extractor; if it occurred it would be recorded as `no_hand`. A detect exception still writes a JSONL row from `finally` with `exit_reason=null`.

## Evaluation isolation

When evaluation mode is on:

- `_dbgInject` returns immediately
- `_dbgServerEmit` returns immediately
- keyboard injection remains gated
- `UI_BYPASS` remains gated
- `enqueueCommand` drops `DEBUG` / `KEYBOARD` / client bypass (real `MOVE`/`ACTION`/`UI`/`SYSTEM` still enqueue)
- `/api/test-emit` returns 403

Demo mode is unchanged.

## Run metadata

Sidecar next to the JSONL: `logs/instrumentation.jsonl` → `logs/instrumentation.run.json`.

Schema `hgria.run_metadata.v1`: `run_id`, `created_at`, `git_sha`, `config_sha256`, `python`, `cwd`, `jsonl_path`, `deployment_path`, `preview_enabled`, `evaluation_mode`, `strict_camera`, `colab_mode`, `colab_fallback`, `dynamic_gestures_enabled`, `instrumentation_enabled`, `opencv` (version, file, distributions), `packages`, `validity`.

Each JSONL row also has `run_id` and `exit_reason`.

## OpenCV environment

**Do not hide this conflict. This machine still loads 4.11.0.**

| Package | Installed |
|---|---|
| `opencv-python` | not installed |
| `opencv-python-headless` | 4.10.0.84 |
| `opencv-contrib-python` | **4.11.0.86** (`Required-by: mediapipe`) |

```
cv2 4.11.0
/home/qtannguyen/.local/lib/python3.10/site-packages/cv2/__init__.py
```

HGRIA only needs core `cv2`. MediaPipe 0.10.14 requires `opencv-contrib-python`, so two distributions share the `cv2` namespace. The repo now pins **both** to `4.10.0.84`. This task did not uninstall or downgrade user site-packages.

A Phase 3 run on this machine without a clean venv will record `cv2` 4.11.0 in the sidecar and will not match the pin.

## Tests

```
python3 -m pytest tests/ -q --tb=short
154 passed in 1.78s
```

## Remaining blockers

- **This machine’s OpenCV:** recreate a venv from the updated `requirements.txt` (or otherwise make `import cv2` report 4.10.0 from the pinned distributions) before treating a run as the pinned baseline.
- **E2E / cloud / scalability:** still not instrumented (no client capture→HUD timers, no Docker/K8s/ngrok harness). `webcam_bridge.js` still omits `frame_id`.
- `ConfigurationManager.get()` still swallows `false`/`0`; unused for measurement flags — not a Phase 3 blocker.

## Phase 3 allowed scope

| Experiment | Allowed? |
|---|---|
| **A-only local OpenCV server-processing baseline** | **Yes**, after OpenCV pin check; preview off; evaluation on; `colab_mode` must stay false |
| local browser E2E | No |
| cloud | No |
| scalability | No |

## Exact next command

```bash
# 1. Confirm the suite (already green on this tree)
python3 -m pytest tests/ -q --tb=short

# 2. Confirm loaded OpenCV. If this is not 4.10.0 from the pinned
#    distributions, recreate a venv from requirements.txt first.
python3 -c "import cv2; print(cv2.__version__); print(cv2.__file__)"
python3 -m pip show opencv-python-headless opencv-contrib-python

# 3. Measurement overrides (do not commit these as new defaults)
export HGRIA_EVALUATION_MODE=true
export HGRIA_EVALUATION_PREVIEW_ENABLED=false
export HGRIA_EVALUATION_STRICT_CAMERA=true
export HGRIA_INSTRUMENTATION_RUN_ID=phase3-a-local-001

# 4. Start the server, then confirm GET /api/debug:
#    colab_mode=false, colab_fallback=false, preview_enabled=false,
#    evaluation_mode=true, dynamic_gestures_enabled=false
#    If colab_mode is true, discard the run.
python3 -m backend.main
```

Then run the defined A-only protocol (10 s warmup + 60 s measurement × 3) against `logs/instrumentation.jsonl` and `logs/instrumentation.run.json`. Do not start Docker, Kubernetes, ngrok, ONNX, or an E2E/cloud/scalability experiment.