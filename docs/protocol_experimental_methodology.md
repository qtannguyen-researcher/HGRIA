The committed system is a **rule-based static path** (MediaPipe Hands → geometric classifier → noise/temporal filters → cooldown → command) plus an **optional ONNX + OC-SORT dynamic path**. There is no labeled dataset, no evaluation harness, and no random-seed control in the production pipeline. The protocol below uses only outputs the code already produces.

---

## What this system can actually evaluate

The static classifier is deterministic given 21 landmarks: weighted rule scores, argmax, then a per-gesture threshold (`backend/pipeline/classifier.py`). Existing tests already drive it with synthetic landmarks (`tests/fixtures.py`). Frame-in evaluation would need recorded video; those files are gitignored (`*.mp4`, `*.avi`, `*.webm`) and the ONNX weights referenced in `config.json` are not in this tree.

Do **not** report “accuracy ≥ 85%”, FPR/FNR on a balanced corpus, mAP, or MOT IDF1. Those appear in the SRS or leftover OC-SORT comments, not in runnable evaluation.

`Session.avg_latency_ms` is never written. `debug.log_pipeline_latency` is a unused config flag. Dynamic events are merged with **confidence hardcoded to 1.0**.

---

## Baseline

**Static-only pipeline with the committed `config/config.json` values, dynamic path off.**

That is the effective runtime of this checkout: `PipelineRunner` treats dynamic init as best-effort; missing ONNX files log a warning and continue on MediaPipe + `GESTURE_RULES`. `ConfigurationManager.DEFAULTS` already set `dynamic_gestures.enabled: false`.

Hold these at config values:

| Setting | Baseline value |
|---|---|
| `dynamic_gestures` | disabled / models absent |
| `gesture_recognition.confidence_threshold` | 0.75 (global; per-gesture thresholds in `GESTURE_RULES` still apply) |
| `smoothing_window_size` | 3 |
| `noise_filter_blur_threshold` | 30 |
| `dominant_hand` | `"Right"` |
| MediaPipe `model_complexity` | 0 |
| `max_num_hands` | 1 |
| `min_detection_confidence` | 0.5 |
| `min_tracking_confidence` | 0.5 |
| Frame size / target FPS | 640×480 / 30 |
| `colab_mode` | false |
| Per-gesture `gesture_cooldowns_ms` | as in `config.json` |
| `custom_gestures` | `[]` |

Compare every treatment to this baseline. Dual-path is a **treatment**, not the baseline, until weights are pinned in-tree.

---

## Independent variables

Vary only knobs the code already reads.

**Primary (always)**  
- **Intended static class:** the 9 `GESTURE_RULES` names plus `UNKNOWN` / ambiguous pose (already tested).

**Secondary (one factor at a time against baseline)**  
- `confidence_threshold`: `{0.50, 0.75, 0.85}` (schema range 0.5–1.0)  
- `smoothing_window_size`: `{1, 3, 5}` (majority = `window_size // 2 + 1`)  
- `noise_filter_blur_threshold`: `{30, 100}` (config vs `DEFAULTS`)  
- `colab_mode`: `{false, true}` — Colab divides the blur threshold by 4  
- `gesture_cooldowns_ms` for the class under test vs 0 (pass-through)

**Optional, only if ONNX weights are present**  
- Path mode: static-only vs dual-path  
- `max_age`, `min_hits`, `iou_threshold`, `maxlen`, `min_frames`

Do not treat `model_complexity` as a default IV. Schema allows 0–1; baseline is 0. Changing it changes MediaPipe, not the geometric rules.

---

## Dependent variables

Record only fields the pipeline already emits.

| Variable | Source |
|---|---|
| `gesture_name` | `Prediction` / merge output |
| `confidence` | `Prediction.confidence` (static); dynamic is always `1.0` — do not treat as a score |
| `raw_scores` | dict of all 9 rule scores |
| `is_filtered`, `filter_reason` | `NoiseFilter` |
| Temporal output | `TemporalFilter.update()` → name or `"UNKNOWN"` |
| Cooldown outcome | `CooldownManager.check()` → partial dict or `None` |
| `command_type`, `command_value` | `COMMAND_MAP` via `CommandGenerator` |
| Funnel counts | `PipelineRunner.stats`: `frames_captured`, `frames_no_hand`, `frames_filtered_noise`, `frames_filtered_temporal`, `frames_cooldown`, `commands_sent` |
| `Session.gesture_counts`, `commands_sent` | `Session.record_command` |
| Merge source | log field `source` = `"static"` \| `"dynamic"` |
| `warmup_ms` | `HandDetector` warmup log |
| Command-queue delay | `CommandTransmitter`: `transmitted_at - timestamp` (ms) |
| WebSocket RTT | existing `ping` / `pong` (`performance.now()`) |

Do not use `Session.avg_latency_ms` as a metric. It is never updated.

---

## Controlled variables

Pin these and report them with every run.

- Python and `requirements.txt` pins: `mediapipe==0.10.14`, `opencv-python-headless==4.10.0.84`, `numpy==1.26.4`, `onnxruntime==1.17.1`, `filterpy==1.4.5`, Flask/SocketIO pins  
- Committed `config.json` except the IV under test  
- `GESTURE_RULES` and `COMMAND_MAP` at the evaluated git SHA  
- Right hand only (`dominant_hand`, `max_num_hands=1`)  
- CLAHE policy: clip 2.0, tiles 8×8, apply if mean gray &lt; 60  
- Landmark extractor: 21 points, bbox from min/max, **never** sets `low_confidence` on MediaPipe Hands  
- Merge rule: dynamic wins if both fire  
- Single-thread `_process_frame` (static and dynamic are sequential, not parallel)  
- Preview emit off or isolated (JPEG encode at ~10 FPS adds work)  
- No live webcam: landmarks from fixtures, or a **versioned** video replay if Protocol B is used  
- OS, CPU model, ONNX providers actually used (`sess.get_providers()`)

---

## Evaluation metrics

### Protocol A — Landmark in, command out (reproducible from this repo)

Drive `GestureClassifier` → `NoiseFilter` → `TemporalFilter` → `CooldownManager` → `CommandGenerator` with the same synthetic-landmark style as `tests/fixtures.py`. No camera, no MediaPipe, no ONNX.

1. **Label match** — `1` if `gesture_name` equals the intended class, else `0`. For `UNKNOWN` poses, match is `gesture_name == "UNKNOWN"`.  
2. **Thresholding rate** — fraction of frames where max `raw_scores` &lt; that gesture’s `confidence_threshold` (returns `UNKNOWN`, confidence 0).  
3. **Rule confusion** — for each trial, argmax vs runner-up in `raw_scores`. Meaningful pairs in this rule set: `open_palm` vs `stop` (spread_ratio), `pinch` vs `ok` (pinch_distance).  
4. **Score bounds** — `confidence` and every `raw_scores` value in `[0, 1]` (already a unit-test invariant).  
5. **Noise rejection rate** by `filter_reason`: `blurry_frame`, `hand_too_small`. Do **not** treat `low_confidence_landmarks` as a live-pipeline metric; `LandmarkExtractor` always sets `low_confidence=False`.  
6. **Temporal delay** — frames until majority (`window_size // 2 + 1`). Window 3 → 2 frames; window 5 → 3.  
7. **Cooldown pass rate** — emissions / stable-gesture frames, compared to `gesture_cooldowns_ms`.  
8. **Command fidelity** — exact match of `(command_type, command_value)` to `COMMAND_MAP`.

**Success on this protocol** is agreement with the rules and maps, not “user accuracy.”

### Protocol B — Frame in (only with a pinned video + labels)

Replay a recorded 640×480 stream into `CameraModule.capture()` / `PipelineRunner._process_frame` (or `/api/frame` consume-once). Labels must be supplied by the experiment; they are not in the repo.

Meaningful quantities:

9. **Funnel rates** from `stats` (per 100 captured frames): no-hand, noise-drop, temporal-drop, cooldown-drop, command.  
10. **Event match** (if labeled): emitted `gesture_name` vs label **after** filters and cooldown — this is command-level, not per-frame classifier accuracy.  
11. **`warmup_ms`** and **per-frame wall time** of `_process_frame` (must be added; the latency flag is unused). Report P50/P95 of **this timer**, not of `avg_latency_ms`.

Skip dual-path event match unless ONNX files are pinned. Dynamic `confidence=1.0` is not a score.

### Protocol C — Timing the system actually implements

12. **Queue latency** — `latency_ms` in `command_transmitted` (create → emit). This is **not** capture-to-HUD latency.  
13. **WebSocket RTT** — ping/pong as in `frontend/js/websocket.js` / `handlers.py`.

The README “sub-150 ms end-to-end” claim is **not** measured by current code. Do not treat queue delay or ping RTT as a substitute.

---

## Number of repetitions

| Protocol | Repetitions | Why |
|---|---|---|
| A — identity, scores, mapping | **1** | Geometric rules have no RNG. |
| A — wall-clock of `classify` / filter | **5** process runs, discard first (OS jitter). Classifier target in the SRS is ≤ 5 ms; that is a budget, not a measured distribution. | |
| A — cooldown | **1** sequence with frozen `time.monotonic` (or `freezegun`, already a dependency). Wall-clock `time.sleep` in `test_cooldown.py` is not a benchmark. | |
| B — MediaPipe video | **5** full replays of the same file | `Hands(static_image_mode=False)` is a tracker; state persists. |
| C — queue latency | **1** session, **≥ 200** commands after warmup (cooldown-limited). SRS “1000-command P95” is a target, not implemented. | |
| C — ping RTT | **30** pings after connect (client interval is `CONFIG.PING_INTERVAL_MS`). | |

Do not average identity metrics across “random seeds.” There are none.

---

## Random seeds

**The production pipeline does not set or read a seed.**

- No `random.seed` / `np.random.seed` on the static or dynamic hot path.  
- `random.randn` in `ocsort/kalmanfilter.py` is demo code, not `MainController`.  
- `uuid.uuid4()` affects `hand_id` / `command_id` / `session_id` only, not labels.  
- ONNX sessions use sequential execution; `HandDetection` then **replaces** the session with `InferenceSession(model_path)` and **drops** the explicit `CPUExecutionProvider` list — provider choice is an environment variable, not a seed.  
- MediaPipe tracking is not seeded in this repo.

For Protocol A, report `seed: none (deterministic rules)`.  
If you later add Gaussian landmark jitter, that is a **new** experiment: use seeds `{0,1,2,3,4}` and keep it separate from the baseline fixtures.

---

## Hardware / software environment

Record a single environment block per published table:

```
OS:            <uname -sr>
Python:        3.10.x          # README_Local; README still says 3.8+
Packages:      requirements.txt lock (mediapipe 0.10.14, numpy 1.26.4, …)
MediaPipe:     model_complexity=0, static_image_mode=False
ONNX Runtime:  1.17.1; print sess.get_providers() per model
CPU:           <model>, no GPU assumed
Resolution:    640×480, target_fps=30
Config SHA:    git rev-parse HEAD + hash of config/config.json
```

Force CPU for any dual-path run: the wrapper prefers `CPUExecutionProvider`, but `HandDetection` reconstructs the session without that list, so CUDA can appear silently if `onnxruntime-gpu` is installed.

Do not mix Colab JPEG (`colab_mode: true`, blur threshold ÷ 4) with local OpenCV capture in the same table.

---

## Expected threats to validity

**Construct**  
- Protocol A tests the **rule engine**, not webcam recognition. Fixture “open palm” is not a MediaPipe landmark.  
- Command-level match after cooldown ≠ per-frame accuracy. Cooldown (e.g. `stop` = 1000 ms) converts a stable pose into a low command rate.  
- Queue latency and ping RTT do not measure capture → command.  
- Dynamic confidence is a constant, not a calibrated score.

**Internal**  
- `config.json` ≠ `DEFAULTS` (`smoothing_window_size` 3 vs 5, blur 30 vs 100, detection confidence 0.5 vs 0.7, dynamic enabled true vs false). Unspecified config source makes runs incomparable.  
- `NoiseFilter` “low_confidence landmarks” is dead on the live path.  
- CLAHE depends on mean brightness &lt; 60; dark videos change RGB that MediaPipe sees.  
- Dual-path merge hides static errors whenever a dynamic event fires.  
- Same-thread “parallel” paths: enabling ONNX changes **static** frame time.  
- Preview JPEG encode contends with recognition if SocketIO is attached.  
- `Hands(static_image_mode=False)` makes frame *t* depend on *t−1*; shuffled frames are invalid.

**External**  
- One right hand, 640×480, indoor-style assumptions in comments; no lighting/user corpus in-tree.  
- Webcam vs browser JPEG changes Laplacian blur and thus noise filtering.  
- ONNX provider and MediaPipe CPU kernels differ across machines.

**Conclusion**  
- SRS ≥ 85% accuracy and P95 ≤ 150 ms e2e are **requirements**, not measurements this repo can reproduce.  
- `test_commander.py` still asserts `COMMAND_MAP` has only 9 keys; the map now includes 24 dynamic names — tests are not a substitute for this protocol.

---

## Minimal run recipe (Protocol A)

1. Freeze git SHA and `config.json`.  
2. Build one landmark per class (extend `tests/fixtures.py` so each pose is geometrically consistent with that class’s rules — current `build_point_left_landmark` is not a distinct pose).  
3. For each class × each IV level, run the stage chain once; record metrics 1–8.  
4. Repeat the same inputs 5 times only for `classify()` wall time.  
5. Publish tables vs the static-only baseline above.

Protocol B/C start only after a versioned video (or ping session) exists; do not backfill accuracy or e2e latency from the SRS.