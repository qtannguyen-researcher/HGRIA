The canonical path is the **static path** (always on). It is orchestrated in one method: `PipelineRunner._process_frame`. There is no offline accuracy/F1 loop in this repo — the live “metric” is a per-gesture score in `[0, 1]` plus a threshold.

---

## Orchestration

| Role | File | Class / function |
|---|---|---|
| Process entry | `backend/main.py` | `main()` → `SystemOrchestrator.start()` |
| Per-frame loop | `backend/pipeline/pipeline_runner.py` | `PipelineRunner.start()` → `_run_loop()` → **`_process_frame()`** |

`_process_frame` is the single function that walks the six stages below.

---

## 1. Raw input

**File:** `backend/pipeline/camera.py`  
**Types:** `backend/core/models.py` → `Frame`

| Class | Function | What it does |
|---|---|---|
| `CameraModule` | `capture()` | Reads one BGR `np.ndarray`, computes Laplacian blur, wraps a `Frame` |
| `OpenCVCaptureStrategy` | `read()` | Local webcam: `cv2.VideoCapture.read()` |
| `ColabCaptureStrategy` | `read()` → `FrameStore.consume()` | Browser JPEG posted to `/api/frame` |

Call site in the runner:

```186:199:backend/pipeline/pipeline_runner.py
        # Stage 1: Capture
        frame = self._camera.capture()
        if frame is None:
            return False
        # ...
        # Stage 2: Preprocess (BGR → RGB + optional CLAHE)
        frame = self._preprocessor.process(frame)
```

`CameraModule.capture()` also sets `Frame.blur_score` (`cv2.Laplacian(...).var()`). That score is used later as a quality gate, not as the gesture metric.

---

## 2. Preprocessing

**File:** `backend/pipeline/preprocessor.py`  
**Class:** `FramePreprocessor`

| Function | Role |
|---|---|
| `process(frame)` | BGR → RGB; optionally CLAHE |
| `_should_apply_clahe(frame)` | Mean brightness `< 60` (or debug overlay on) |
| `_apply_clahe(rgb_data)` | CLAHE on L channel in LAB |

Output: `frame.rgb_data` — this is the MediaPipe model input.

---

## 3. Model input

**File:** `backend/pipeline/detector.py`  
**Class:** `HandDetector`

`detect(frame)` requires `frame.rgb_data` and passes it straight into MediaPipe:

```61:64:backend/pipeline/detector.py
        if frame.rgb_data is None:
            return []

        results = self._hands.process(frame.rgb_data)
```

The model itself is constructed in `HandDetector.__init__`:

```26:32:backend/pipeline/detector.py
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=config.mediapipe.max_num_hands,
            min_detection_confidence=config.mediapipe.min_detection_confidence,
            min_tracking_confidence=config.mediapipe.min_tracking_confidence,
            model_complexity=config.mediapipe.model_complexity,
        )
```

Config fields live in `config/config.json` under `mediapipe.*`, loaded by `backend/core/configuration.py` → `ConfigurationManager`.

---

## 4. Forward pass

**File:** `backend/pipeline/detector.py`  
**Function:** `HandDetector.detect()`  
**Underlying call:** `mp.solutions.hands.Hands.process(frame.rgb_data)`

That is the only neural inference on this path. MediaPipe returns:

- `results.multi_hand_landmarks` — 21 points per hand
- `results.multi_handedness` — Left/Right + detection score

`detect()` zips those into `List[Tuple[mp_landmarks, handedness_info]]`. If empty, the runner calls `StateManager.transition("no_hand_detected")` and stops this path.

---

## 5. Post-processing

**File:** `backend/pipeline/extractor.py`  
**Class:** `LandmarkExtractor`  
**Types:** `Landmark`, `LandmarkPoint`, `BoundingBox` in `backend/core/models.py`

| Function | Role |
|---|---|
| `extract_all(raw_results, dominant_hand)` | Extract every hand, then keep the configured dominant hand |
| `extract(raw)` | Build one `Landmark`: 21 `LandmarkPoint`s, bbox, palm center, handedness |

Call site:

```229:233:backend/pipeline/pipeline_runner.py
            dominant_hand = self._config.gesture_recognition.dominant_hand
            landmarks = self._extractor.extract_all(raw_landmarks, dominant_hand)
            if landmarks:
                landmark = landmarks[0]
                prediction = self._classifier.classify(landmark)
```

Helpers used later by the classifier: `Landmark.distance()`, `BoundingBox.width()` / `diagonal()`.

---

## 6. Evaluation metric

**File:** `backend/pipeline/classifier.py`  
**Types:** `Prediction` in `backend/core/models.py`

This is the scoring step. There is no dataset accuracy/F1 in code.

| Class | Function | Metric |
|---|---|---|
| `Rule` | `evaluate(lm) -> float` | One geometric constraint, clamped to `[0, 1]` |
| `GestureRule` | `evaluate(lm) -> float` | Weighted average of its `Rule`s |
| `GestureClassifier` | `classify(lm) -> Prediction` | Argmax over gesture scores, then threshold |

Decision rule in `GestureClassifier.classify`:

```297:316:backend/pipeline/classifier.py
        raw_scores: Dict[str, float] = {}
        for rule in self._rules:
            raw_scores[rule.gesture_name] = rule.evaluate(lm)

        best_name = max(raw_scores, key=raw_scores.get)
        best_score = raw_scores[best_name]

        per_gesture_threshold = next(
            (r.confidence_threshold for r in self._rules if r.gesture_name == best_name),
            self._threshold
        )

        if best_score < per_gesture_threshold:
            return Prediction(gesture_name="UNKNOWN", raw_scores=raw_scores)

        return Prediction(
            gesture_name=best_name,
            confidence=best_score,
            raw_scores=raw_scores,
        )
```

Rule types inside `Rule.evaluate`: `finger_extended`, `finger_curled`, `spread_ratio`, `pinch_distance`, `horizontal_direction`, `thumb_up`, `victory_spread_angle`.

Built-in gestures are the module-level list `GESTURE_RULES`. Custom ones are parsed by `GestureClassifier._parse_custom()`.

**What the metric is, in one sentence:** the winning gesture’s weighted-average rule score (`Prediction.confidence`), accepted only if it exceeds that gesture’s `confidence_threshold` (else `"UNKNOWN"`).

---

## After the metric (same frame)

These are not a second model; they stabilize and emit the decision.

| Stage | File | Class | Function |
|---|---|---|---|
| Quality reject | `backend/pipeline/filter.py` | `NoiseFilter` | `filter(pred, lm, frame)` — low-conf landmarks, blur, bbox area |
| Temporal majority | `backend/pipeline/filter.py` | `TemporalFilter` | `update(pred) -> str` — majority in last `smoothing_window_size` frames |
| Merge | `backend/pipeline/pipeline_runner.py` | `PipelineRunner` | `_process_frame()` — dynamic event wins if both fire |
| FSM | `backend/core/state_manager.py` | `StateManager` | `transition("gesture_stable")` |
| Rate limit | `backend/pipeline/cooldown.py` | `CooldownManager` | `check(gesture, confidence)` |
| Command | `backend/pipeline/commander.py` | `CommandGenerator` | `generate(partial) -> Command` via `COMMAND_MAP` |
| Session counts | `backend/core/models.py` | `Session` | `record_command(cmd)` |
| Emit | `backend/pipeline/pipeline_runner.py` | `PipelineRunner` | `_socketio.emit("gesture_command", ...)` |

---

## Call chain (static path, one frame)

```
main()
  SystemOrchestrator.start()
    PipelineRunner.start() → _run_loop() → _process_frame()
      CameraModule.capture()                          # raw BGR Frame
        OpenCVCaptureStrategy.read()  |  ColabCaptureStrategy.read()
      FramePreprocessor.process()                     # BGR→RGB, CLAHE
      HandDetector.detect()                           # model input + forward
        mp.solutions.hands.Hands.process(rgb_data)
      LandmarkExtractor.extract_all() → extract()     # post-process
      GestureClassifier.classify()                    # evaluation
        GestureRule.evaluate()
          Rule.evaluate()                             # score ∈ [0, 1]
      NoiseFilter.filter()
      TemporalFilter.update()
      CooldownManager.check()
      CommandGenerator.generate()
      Session.record_command()
```

---

**Note:** `_process_frame` also runs a parallel **dynamic ONNX path** (`DynamicGestureRecognizer.process_frame` → `MainController.__call__` → `HandDetection` / `HandClassification` in `backend/pipeline/dynamic/onnx_models.py`). That path has an explicit tensor `OnnxModel.preprocess` and `sess.run` forward pass, then `np.argmax` plus `Deque.check_is_action`. It is optional and is merged only after the static metric above. If you want that path traced the same way, say so.