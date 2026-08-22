Phase 1 baseline stabilization is in place. The experiment is frozen on the **static MediaPipe/rule-based path**; the dynamic ONNX code is still in the tree but is not loaded.

## 1. Summary of changes

- `config/config.json` now has `dynamic_gestures.enabled = false`, and `PipelineRunner` **reads that flag** instead of treating section presence as enablement.
- Baseline-critical defaults were aligned with `config.json` (detection confidence, smoothing window, blur threshold, log path).
- One `Session` instance is shared by the orchestrator, pipeline/`CommandGenerator`, and `/api/session`.
- Evaluation mode exists (`evaluation.mode`, `?evaluation=true`, `HGRIA_EVALUATION_MODE`). Demo keyboard/UI bypass remains the default; evaluation mode turns them off.
- `scipy` is pinned to the version in this environment (`1.15.3`).
- Stale tests were updated to match the current FSM/`COMMAND_MAP`; new tests cover the Phase 1 invariants.
- Baseline contract is written in `docs/experiments/baseline.md` (configuration targets only — no claimed results).

## 2. Changed files

**Production / config**
- `config/config.json`
- `backend/core/configuration.py`
- `backend/pipeline/pipeline_runner.py`
- `backend/main.py`
- `backend/app.py`
- `frontend/js/config.js`
- `frontend/js/state.js`
- `frontend/js/websocket.js`
- `frontend/js/main.js`
- `frontend/index.html` (cache-bust `?v=3` on the edited scripts)
- `requirements.txt`

**Tests / docs**
- `tests/test_pipeline_baseline.py` (new)
- `tests/test_configuration.py`
- `tests/test_commander.py`
- `tests/test_state_manager.py`
- `tests/test_cooldown.py`
- `tests/test_filter.py`
- `tests/test_flask_api.py`
- `docs/experiments/baseline.md` (new)

## 3. Why each change was necessary

| Change | Why |
|---|---|
| `dynamic_gestures.enabled: false` + `is_dynamic_gestures_enabled()` | Baseline must be static-only; the audit found the initializer ignored the flag. |
| Align DEFAULTS for confidence / window / blur / `logs/` | Those were the contradictions that made runs incomparable. `config.json` remains source of truth. |
| Inject `session=` into `PipelineRunner` | Flask `/api/session` was a different object from `CommandGenerator`, so recorded commands never showed up. |
| `evaluation.mode` + client guards + 403 on `/api/test-emit` | UI_BYPASS and keyboard injection must not contaminate eval runs; demo path stays default-off. |
| `scipy==1.15.3` | Only under-pinned runtime dep called out; version taken from this machine (`pip show scipy`). |
| Stale tests | `COMMAND_MAP` is 9 static + 24 dynamic names, not 9 keys; FSM is the current key set, not “21”; fixtures needed a logger and `camera.colab_mode`. |
| `docs/experiments/baseline.md` | Freeze the contract without claiming measurements. |

**Final baseline values** (configuration targets):

- Path: static MediaPipe + `GESTURE_RULES` only  
- `dynamic_gestures.enabled`: **false**  
- MediaPipe: detection **0.5**, tracking **0.5**, `max_num_hands` **1**, complexity **0**  
- `smoothing_window_size`: **3**  
- `noise_filter_blur_threshold`: **30**  
- `confidence_threshold`: **0.75**  
- Capture: OpenCV, `colab_mode` **false**, **640×480**, 30 FPS  
- Log path: **`logs/`**  
- `evaluation.mode`: **false** (demo default)

## 4–6. Tests

Executed: `python3 -m pytest tests/ -q --tb=short`

**103 passed, 0 failed, 0 skipped.**

Smoke check (no live camera/server): config load, ONNX class **not** constructed when `enabled=false`, shared Session identity, `/api/session` shows a pipeline-recorded `open_palm`, `/api/test-emit` is 200 in demo and **403** in evaluation mode, frontend source contains the evaluation guards.

## 7. Remaining reproducibility risks

- Transitive packages (protobuf, werkzeug, …) are still unpinned; record `pip freeze` per published run.
- Root README still says Python 3.8+; SciPy 1.15.3 needs **3.10+**. This environment is **3.10.12**.
- If the local camera fails to open, `CameraModule` can flip `colab_mode` for that process — that is **not** this baseline.
- `ConfigurationManager.get()` still uses `or default` (`0`/`False` fall through). Baseline code uses dedicated helpers for the two flags.
- Env overrides only support one `_` split (`HGRIA_CAMERA_INDEX` works; nested gesture keys do not).
- Git SHA is not embedded; run `git rev-parse HEAD` when you freeze a run.
- No labeled corpus and no latency instrumentation yet (intentionally out of Phase 1).

## 8. Exact next recommended step

Commit this freeze, record `git rev-parse HEAD` in the run log, and recreate the environment with `pip install -r requirements.txt`.

**Do not** start Docker, ONNX, new gestures, or load tests yet. The next phase is **instrumentation only**: measure what the static pipeline already emits (`PipelineRunner.stats`, command timestamps, Protocol A landmark-in / command-out) against this frozen config.