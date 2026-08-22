HGRIA is a **real-time dual-path inference product**, not a training codebase. Static gestures are geometric rules on MediaPipe landmarks. Dynamic gestures consume pretrained ONNX models that are **not in the working tree**. There is no trainer, no labeled dataset, and no accuracy/latency eval harness.

A visual map of the eight sections is in [HGRIA architecture review](/home/qtannguyen/.cursor/projects/home-qtannguyen-projects-researcher-HGRIA/canvases/HGRIA-architecture-review.canvas.tsx) — a canvas you can open beside this chat. The repository was not modified.

---

## 1. Architecture

The process is a Flask-SocketIO server plus one background pipeline thread.

`SystemOrchestrator.start` is the composition root: it loads config, constructs `HandDetector` and `CameraModule`, builds the Flask app, starts `PipelineRunner`, optionally opens ngrok, then blocks on Socket.IO.

```39:128:backend/main.py
    def start(self) -> None:
        """Start the entire HGRIA system."""
        try:
            # ...
            self._config = ConfigurationManager(self._config_path)
            # ...
            detector = HandDetector(self._config, self._logger)
            camera = CameraModule(self._config)
            self._app, self._socketio = create_app(...)
            self._pipeline = PipelineRunner(...)
            self._pipeline.start()
            # ...
            self._socketio.run(self._app, host=..., port=..., use_reloader=False, ...)
```

`create_app` registers HTTP blueprints, the Colab frame endpoint, Socket.IO handlers, CORS, and ProxyFix for ngrok.

```30:84:backend/app.py
def create_app(...) -> tuple:
    app = Flask(__name__, static_folder="../frontend", static_url_path="")
    CORS(app, origins=cors_origins)
    socketio = SocketIO(app, async_mode="threading", ...)
    app.register_blueprint(health_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(session_bp)
```

`PipelineRunner` documents two paths and merge-with-dynamic-priority. The loop is a single daemon thread (`PipelineRunner.start` → `_run_loop` → `_process_frame`). The docstring says the paths run “in parallel”; the implementation is sequential on that thread.

```1:14:backend/pipeline/pipeline_runner.py
"""Pipeline runner that orchestrates all stages in a background thread.
...
3a. Static path
3b. Dynamic path ... runs on the raw BGR frame in parallel with 3a
4.  Merge & cooldown – first valid gesture wins (dynamic takes priority)
```

```147:151:backend/pipeline/pipeline_runner.py
    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
```

An 8-state FSM (`SystemState` + `TRANSITION_TABLE`) lives in `StateManager.transition`. WebSocket `pause_pipeline` / `resume_pipeline` both call `stop_gesture`. **`PipelineRunner._process_frame` never reads `SystemState.PAUSED`**, so pause does not stop inference.

```94:114:backend/core/state_manager.py
    def transition(self, event: str) -> bool:
        key = (self._state, event)
        next_state = TRANSITION_TABLE.get(key)
        if next_state is None:
            ...
            return False
```

```46:54:backend/websocket/handlers.py
    @sio.on("pause_pipeline")
    def on_pause_pipeline():
        state_manager.transition("stop_gesture")

    @sio.on("resume_pipeline")
    def on_resume_pipeline():
        state_manager.transition("stop_gesture")
```

Frontend bootstrap is `frontend/js/main.js` (DOMContentLoaded): `GameState` → `Renderer` → `AudioManager` → `SocketClient` → `HUDManager` → `GameEngine` → `WebcamBridge`. Frontend is also served statically from Flask (`static_folder="../frontend"`) and deployed independently via `.github/workflows/deploy.yml` (GitHub Pages) and `vercel.json`.

---

## 2. Data pipeline

Frames enter through a strategy pattern in `CameraModule.__init__`: local OpenCV or Colab/browser `FrameStore`.

**Local.** `OpenCVCaptureStrategy.__init__` opens `cv2.VideoCapture(config.camera.index)` and sets width/height/FPS. `read` returns BGR or `None`.

**Browser / Colab.** `WebcamBridge.#sendFrame` draws 640×480 JPEG quality 0.7 at 30 FPS and POSTs base64 to `/api/frame`. `receive_frame` (in `create_app`) decodes JPEG → BGR and calls `FrameStore.put`. `ColabCaptureStrategy.read` uses `FrameStore.consume` (read-and-clear) so each JPEG is processed once.

```87:102:backend/pipeline/camera.py
    def put(self, bgr: np.ndarray) -> None:
        with self._store_lock:
            self._frame = bgr

    def consume(self) -> Optional[np.ndarray]:
        with self._store_lock:
            frame = self._frame
            self._frame = None
            return frame
```

If the local camera fails, `CameraModule._open_local_or_fallback` patches `config._data["camera"]["colab_mode"] = True` so `/api/frame` becomes live.

**Per-frame packaging.** `CameraModule.capture` computes Laplacian variance as `Frame.blur_score`, then `FramePreprocessor.process` converts BGR→RGB and applies CLAHE when mean brightness `< FramePreprocessor.BRIGHTNESS_THRESHOLD` (60), or always if `debug.show_landmark_overlay`.

**Static geometry.** `LandmarkExtractor.extract` builds 21 `LandmarkPoint`s, a bbox from min/max x/y, and palm center as midpoint of landmarks 0 and 9. `extract_all` keeps the configured `dominant_hand` when both hands appear.

**Dynamic tensors.** `OnnxModel.preprocess` does BGR→RGB, resize, `(x-127)/128`, NCHW, batch dim. Detector input is 320×240 (`HandDetection.__init__`); classifier crops are square-padded then 128×128 (`HandClassification.get_square` / `get_crops`). Class names are the `targets` list in `backend/pipeline/dynamic/utils/enums.py` (47 labels). Gesture IDs used by the action FSM (e.g. `25` fist, `19` point) are integer indices into that list, consumed in `Deque.set_hand_position` and `Deque.check_is_action`.

Empty-store spinning is throttled in `PipelineRunner._run_loop` (`time.sleep(0.005)` when capture returns `None`).

---

## 3. Training pipeline

**There is no training pipeline in this repository.**

- Static path: `GESTURE_RULES` is a hardcoded list; `GestureClassifier.__init__` copies it and optionally appends `config.custom_gestures` via `_parse_custom`. README states “No training data required.”
- Dynamic path: `DynamicGestureRecognizer.__init__` only checks that two ONNX files exist and constructs `MainController`. A glob of the tree found **zero** `.onnx` / `.pth` / `.ckpt` files. `.gitignore` comments that ONNX weights “are tracked,” but they are not present.
- `requirements.txt` pins `onnxruntime` and `mediapipe`; it does not pin PyTorch or a training stack. Notebooks import TensorFlow only to print a version while launching the server.
- `temp_requirements.md` describes a *future* MLP/CNN + TFLite trainer; that code is not here.

When ONNX files are missing, `PipelineRunner._init_dynamic_recognizer` catches the exception and continues static-only.

---

## 4. Inference pipeline

### Static path

1. `HandDetector.detect` — `mp.solutions.hands.Hands.process` on `frame.rgb_data` (`static_image_mode=False`, complexity from config). `_warmup` runs a blank 480×640 inference at init.
2. `LandmarkExtractor.extract_all`
3. `GestureClassifier.classify` — every `GestureRule.evaluate` is a weighted mean of `Rule.evaluate` (finger_extended/curled, spread_ratio, pinch_distance, horizontal_direction, thumb_up, victory_spread_angle). Winner is `max(raw_scores)`; if below that gesture’s `confidence_threshold`, return `UNKNOWN`.
4. `NoiseFilter.filter` — reject if `len(low_confidence_indices) > 3`, `blur_score` below threshold (÷4 in colab_mode), or bbox area `< MIN_BBOX_AREA` (0.005).
5. `TemporalFilter.update` — deque of size `smoothing_window_size`; emit only if count `>= window//2 + 1`.

### Dynamic path

1. `DynamicGestureRecognizer.process_frame` → `MainController.__call__`
2. `HandDetection.__call__` — ONNX boxes + probs, denormalized to pixel coords
3. `HandClassification.__call__` — `argmax` on batched crops
4. `MainController.update` — OC-SORT: `KalmanBoxTracker.predict`, `associate` (velocity + GIoU via `asso_func = ASSO_FUNCS["giou"]`), second-round rematch, new tracks, drop if `time_since_update > max_age`
5. `Deque.append` → `set_hand_position` → `check_is_action` (duration, swipe distance, horizontal/vertical gates)
6. `DynamicGestureRecognizer._collect_events` — one-shot events cleared; `DRAG`/`DRAG2`/`DRAG3` emitted once per track

**Merge.** Dynamic wins; confidence is hard-coded to `1.0`. Config key `dynamic_gestures.enabled` is **never read** (grep of `*.py` has no match).

```263:272:backend/pipeline/pipeline_runner.py
        if dynamic_gesture:
            gesture = dynamic_gesture
            confidence = 1.0
        elif static_gesture:
            gesture = static_gesture
            confidence = static_confidence
        else:
            return True
```

### Command emission

`CooldownManager.check` → `CommandGenerator.generate` (static `COMMAND_MAP` + custom_gestures) → `socketio.emit("gesture_command", command.to_dict())` and `command_queue.put_nowait`. `CommandTransmitter` is implemented and unit-tested but **never constructed in `SystemOrchestrator.start`**. Frontend `SocketClient` also synthesizes UI commands from `gesture_update` for `victory`/`stop`/`ok`/`DOUBLE_TAP` (800 ms client cooldown). `GameEngine` applies `COMMAND_HANDLERS`; `KEYBOARD_MAP` injects local commands without the backend.

---

## 5. Evaluation pipeline

**Unit tests, not model evaluation.**

| What | Where |
|---|---|
| Synthetic 21-point landmarks | `tests/fixtures.py` `build_landmark` |
| Rule score ∈ [0,1], argmax, UNKNOWN | `tests/test_classifier.py` |
| Blur / small-hand / majority vote | `tests/test_filter.py` |
| Cooldown / COMMAND_MAP | `tests/test_cooldown.py`, `tests/test_commander.py` |
| Schema, env override, hot-reload | `tests/test_configuration.py` |
| FSM table | `tests/test_state_manager.py` |
| HTTP + headers | `tests/test_flask_api.py` |
| Socket.IO connect | `tests/test_websocket.py` |

Gaps:

- No tests for `PipelineRunner`, `HandDetector`, ONNX, or OC-SORT.
- README “hypothesis” tests: no `@given` in `tests/`.
- `Session.avg_latency_ms` is returned by `get_session` and reset by `reset_session`, never updated (`record_command` only increments counts).
- `debug.log_pipeline_latency` is in `HOT_RELOAD_FIELDS` and never referenced in the pipeline.
- Operational diagnostics only: `debug_info` / `_diagnose` on `GET /api/debug`.
- CI (`.github/workflows/deploy.yml`) deploys `frontend/` only; pytest is not run.
- Spec accuracy in `temp_requirements.md` (NFR-002.1 ≥85%) has no harness.

---

## 6. Configuration mechanism

Load path: `ConfigurationManager.__init__` → `_deep_merge(DEFAULTS, _load_file)` → `_apply_env_overrides` → `_validate`.

- **File:** `config/config.json`. Missing file → `{}`.
- **Env:** `HGRIA_{SECTION}_{PARAM}` with `split("_", 1)` — only one nesting level. `HGRIA_CAMERA_INDEX` works; `HGRIA_GESTURE_RECOGNITION_CONFIDENCE_THRESHOLD` does not map to `gesture_recognition.confidence_threshold`.
- **Schema:** `SCHEMA` covers a subset (camera size/FPS, a few MediaPipe and gesture fields, `server.port`). Out-of-range values are **silently replaced** with `DEFAULTS` in `_validate`. `dynamic_gestures.*`, `colab_mode`, blur threshold, cooldowns are unvalidated.
- **Hot reload:** `PUT /api/config` → `update_config` → `ConfigurationManager.update`. Allowed: `HOT_RELOAD_FIELDS` plus `gesture_cooldowns_ms.*`.
- **Live vs copied:** `CooldownManager` holds the cooldown dict (updates apply). `GestureClassifier._threshold`, `TemporalFilter._window_size` (and deque `maxlen`), `StructuredLogger._level` are copied at init. `dominant_hand` is reread each frame in `_process_frame`.
- **`get` trap:** `ConfigurationManager.get` uses `or default`, so `0`/`False`/`""` fall through (DRAG cooldown is `0`).
- **Frontend URL:** `CONFIG.SERVER_URL` getter: `window.HGRIA_BACKEND_URL` > `?server=` > `localStorage['hgria_backend_url']` > `http://localhost:5000`.
- **Public config:** `public_dict` strips `logging.log_file_path` before WS `server_info` and `GET /api/config`.

Custom static gestures: `GestureClassifier._parse_custom` + `CommandGenerator.__init__` merge from `config.custom_gestures`.

---

## 7. Reproducibility risks

1. **Missing ONNX weights** — `DynamicGestureRecognizer.__init__` raises `FileNotFoundError`; `_init_dynamic_recognizer` swallows it. `config.json` has `"enabled": true` but that flag is unused, so “enabled” does not mean the path is actually running.

2. **Machine-specific paths** — `config/config.json` `logging.log_file_path` is `/home/qtannguyen/projects/researcher/HGRIA/logs/`. `DEFAULTS` uses `/content/drive/MyDrive/HGRIA/logs/`.

3. **Pin / doc drift** — `requirements.txt` has `onnxruntime==1.17.1`; README troubleshooting says `1.13.1`. Notebooks import TensorFlow; it is not in `requirements.txt`. `mediapipe.min_detection_confidence` is `0.5` in JSON vs `0.7` in `DEFAULTS`.

4. **Two `Session` objects** — `SystemOrchestrator.start` creates one for Flask `HG_SESSION`; `PipelineRunner.__init__` creates another for `CommandGenerator`. `GET /api/session` never sees `record_command`.

5. **Naive UTC** — `Frame`/`Prediction`/`Command` use `datetime.utcnow`; `Command.to_dict` appends `"Z"` to a naive ISO string.

6. **Unseeded IDs** — `uuid.uuid4` for commands/landmarks; `KalmanBoxTracker.count` is a process-wide class counter, never reset.

7. **OC-SORT association is not deterministic across numeric edge cases** — `giou_batch` has `assert (wc > 0).all()`; degenerate boxes can crash the dynamic path (caught and logged in `_process_frame`).

8. **Notebook mutates source** — `README_Local.md` documents an in-place patch of `backend/core/configuration.py`.

9. **CORS `*`** — `config.server.cors_origins` and `SocketIO(cors_allowed_origins=...)`.

10. **`HandDetection.__init__` rebuilds `InferenceSession(model_path)`** after `OnnxModel.__init__` already created a session with provider selection — detector inference ignores the CUDA/DML provider logic in `OnnxModel.get_onnx_provider`.

11. **Client bypass** — `SocketClient` can fire UI commands the server did not emit, so logged server commands ≠ what the game executed.

---

## 8. Computational bottlenecks

All of the following run **on the same pipeline thread** inside `PipelineRunner._process_frame`. Ranked from call-graph cost (no profiler run in this analysis).

| Rank | Bottleneck | Why | Function |
|---|---|---|---|
| 1 | MediaPipe Hands | Full-frame landmark network every captured frame; extra blank-frame warmup at startup | `HandDetector.detect`, `HandDetector._warmup` |
| 2 | ONNX detect + classify | Second full-frame net (320×240) plus per-box 128×128 crops; default provider is CPU (`OnnxModel.get_onnx_provider` starts with `CPUExecutionProvider`; `HandDetection` then drops that session) | `HandDetection.__call__`, `HandClassification.__call__` |
| 3 | Browser JPEG path | 30 FPS canvas encode + base64 JSON POST + `cv2.imdecode`; JPEG smoothing also tanks Laplacian variance, so `NoiseFilter` is more likely to drop frames unless colab ÷4 applies | `WebcamBridge.#sendFrame`, `receive_frame`, `NoiseFilter._blur_threshold` |
| 4 | Preview encode | JPEG quality 60 + base64 `frame_preview` ~10 Hz on the same thread | `PipelineRunner._maybe_emit_preview` |
| 5 | Duplicate grayscale | Laplacian in `CameraModule.capture` and brightness in `FramePreprocessor._should_apply_clahe` each convert BGR→gray | those two methods |
| 6 | OC-SORT + action FSM | Cheap vs the nets; still Python `associate` + Kalman + a long `check_is_action` chain | `MainController.update`, `Deque.check_is_action` |
| 7 | Geometric classifier | Negligible vs neural nets (pure numpy/python on 21 points) | `GestureClassifier.classify` |

Additional latency (not GPU/CPU of the nets): ngrok + Socket.IO in Colab/local-tunnel mode (`SystemOrchestrator._start_ngrok`, `SocketClient.connect`). Claimed “sub-150 ms” in README is not measured: `avg_latency_ms` is unused and `log_pipeline_latency` is unused.

`backend/utils/geometry.py` duplicates classifier math and is **never imported**.