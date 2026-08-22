# HGRIA Phase 1 baseline (static-only)

This document freezes the **configuration and runtime contract** of the
committed static MediaPipe / rule-based path. It is **not** a results
paper. No accuracy, latency, or throughput numbers are claimed here.

- **Configuration targets** (this file): values the process is configured to use.
- **Measured results**: not recorded. Do not copy numbers from the SRS or README into a results table from this checkout.

Record the git SHA of the tree you actually ran (this file is not auto-updated):

```bash
git rev-parse HEAD
```

---

## Project

| Field | Value |
|---|---|
| Name | HGRIA — Hand Gesture Recognition for Interactive Applications |
| Purpose of this baseline | Reproducible **static-only** recognition path for later comparison. Dual-path (ONNX / OC-SORT) is a treatment, not the baseline. |
| Recognition path | MediaPipe Hands → geometric `GESTURE_RULES` classifier → noise filter → temporal majority vote → cooldown → `COMMAND_MAP` |
| Dynamic path | **Disabled.** Implementation remains in-tree under `backend/pipeline/dynamic/` and is not loaded when `dynamic_gestures.enabled` is false. |

## Configuration source of truth

**`config/config.json`** is the source of truth for this experiment.

`backend/core/configuration.py` `DEFAULTS` are aligned with that file for the
baseline-critical fields listed below so a missing key does not silently
revert to a different experiment. Environment overrides (`HGRIA_{SECTION}_{PARAM}`)
can still replace a value at process start; do not use them for a baseline run
unless the override is recorded.

Load path: `ConfigurationManager` → deep-merge `DEFAULTS` with `config.json` → env → schema clamp.

## Python and dependencies

| Item | Value | Kind |
|---|---|---|
| Python (this environment) | 3.10.12 | **measured** on the machine that produced this freeze |
| Documented local requirement | 3.10+ (`README_Local.md`) | documentation; root README still says 3.8+ |
| `scipy` pin | `scipy==1.15.3` | **from this environment** (`pip show scipy`); SciPy 1.15 requires Python ≥ 3.10 |

Pinned in `requirements.txt` at the time of this freeze:

| Package | Pin |
|---|---|
| flask | 3.0.3 |
| flask-socketio | 5.3.6 |
| flask-cors | 4.0.1 |
| mediapipe | 0.10.14 |
| opencv-python-headless | 4.10.0.84 |
| numpy | 1.26.4 |
| pytest | 8.3.2 |
| pytest-cov | 5.0.0 |
| freezegun | 1.5.1 |
| hypothesis | 6.112.0 |
| pyngrok | 7.2.0 |
| python-socketio | 5.11.2 |
| python-engineio | 4.9.1 |
| onnxruntime | 1.17.1 |
| filterpy | 1.4.5 |
| scipy | 1.15.3 |

ONNX Runtime and filterpy remain listed because the dynamic implementation is
not deleted; they are **not used** on the baseline path when `enabled` is false.

Transitive packages (protobuf, werkzeug, …) are **not** pinned in
`requirements.txt`. Re-create the environment from that file and record
`pip freeze` with each published run.

## Capture and image geometry (configuration targets)

| Setting | Baseline value |
|---|---|
| Capture mode | Local OpenCV `VideoCapture` (`camera.colab_mode` = `false`) |
| Fallback | If the local camera cannot open, `CameraModule` switches to browser JPEG POST (`/api/frame`) and sets `colab_mode` true for that process. **Do not treat a fallback process as this baseline.** |
| Resolution | 640 × 480 |
| Target FPS | 30 |
| Camera index | 0 |

## MediaPipe (configuration targets)

| Setting | Baseline value |
|---|---|
| `static_image_mode` | `false` (hard-coded in `HandDetector`, not a JSON field) |
| `min_detection_confidence` | 0.5 |
| `min_tracking_confidence` | 0.5 |
| `max_num_hands` | 1 |
| `model_complexity` | 0 |

## Gesture recognition (configuration targets)

| Setting | Baseline value |
|---|---|
| `confidence_threshold` (global) | 0.75 (per-gesture thresholds in `GESTURE_RULES` still apply) |
| `smoothing_window_size` | 3 |
| `noise_filter_blur_threshold` | 30 |
| `dominant_hand` | `"Right"` |
| `gesture_cooldowns_ms` | as in `config/config.json` |
| `custom_gestures` | `[]` |

## Dynamic path (must stay off)

| Setting | Baseline value |
|---|---|
| `dynamic_gestures.enabled` | **false** |
| ONNX init | `PipelineRunner._init_dynamic_recognizer` returns without constructing `DynamicGestureRecognizer` when the flag is false |

The JSON section may still exist (model paths, tracker knobs). **Section presence is not enablement.**

## Static gesture classes

Nine rule-based classes in `backend/pipeline/classifier.py` `GESTURE_RULES`:

`open_palm`, `closed_fist`, `point_left`, `point_right`, `thumb_up`, `victory`, `stop`, `pinch`, `ok`

plus `UNKNOWN` when no rule wins above its threshold.

`COMMAND_MAP` also lists 24 dynamic event names. Those names are not produced by the static baseline path.

## Logging (configuration target)

| Setting | Baseline value |
|---|---|
| `logging.level` | `INFO` |
| `logging.log_to_file` | `true` |
| `logging.log_file_path` | `logs/` (relative to process CWD; typically the repo root) |
| `logging.log_raw_landmarks` | `false` |

Do not use a machine-absolute path or a Colab Drive path for a baseline run.

## Evaluation-mode restrictions

Default **development/demo** behaviour is unchanged: `evaluation.mode` = `false`.

When evaluation mode is **on** (`evaluation.mode` = `true` in config, env
`HGRIA_EVALUATION_MODE=true`, and/or frontend `?evaluation=true|1|yes`):

- Frontend `UI_BYPASS` (synthetic commands from `gesture_update` for `victory` / `stop` / `ok` / `DOUBLE_TAP`) is **disabled**.
- Frontend keyboard command injection (`KEYBOARD_MAP` → `enqueueCommand`) is **disabled**.
- `/api/test-emit` returns **403**.
- Game commands must come from the server pipeline (`gesture_command` emitted after cooldown + `CommandGenerator`).

Keyboard handling for the backend-URL overlay (Enter to connect) is UI, not a game command, and is left intact.

To run an evaluation session: set `"evaluation": { "mode": true }` in `config/config.json` (or the env var), restart the process, and open the frontend with `?evaluation=true`. Restore `mode: false` for demo play.

## Session identity

One `Session` instance is shared by `SystemOrchestrator`, `PipelineRunner` /
`CommandGenerator`, and Flask `GET/DELETE /api/session`. Recording a command
in the pipeline increments `commands_sent` / `gesture_counts` visible on that API.

## Known limitations (not results)

- No labeled corpus, no evaluation harness, no random seed on the production path.
- `Session.avg_latency_ms` is never written; do not report it.
- `debug.log_pipeline_latency` is unused.
- Schema silently clamps out-of-range numeric fields to `DEFAULTS`.
- `ConfigurationManager.get()` uses `or default`, so `0` / `False` / `""` fall through; baseline code uses explicit helpers for `enabled` and `evaluation.mode`.
- Env overrides only support one nesting split (`HGRIA_CAMERA_INDEX` works; `HGRIA_GESTURE_RECOGNITION_CONFIDENCE_THRESHOLD` does not).
- Transitive dependency versions are unpinned.
- MediaPipe `Hands(static_image_mode=False)` is stateful across frames.
- Starting the full orchestrator without a camera can flip `colab_mode` for that process (see capture fallback above).

## What this freeze is not

Do not treat README claims (e.g. sub-150 ms end-to-end, ≥ 85 % accuracy) as
measurements of this baseline. Those are requirements or marketing text, not
outputs of a run recorded here.

## Infomations
Baseline Commit:
2de58ee8f49d07d1a4cc6f1fde942e3f908c4f4f

Python:
3.10.12

Environment:
See environment.txt

Baseline Date:
2026-08-22
