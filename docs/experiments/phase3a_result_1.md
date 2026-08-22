# HGRIA Phase 3A — local OpenCV server-processing baseline

**Status: PHASE_3A_COMPLETE**

This experiment measures local server-processing latency only.

It does **not** measure end-to-end gesture-to-command latency, browser
latency, HTTP upload latency, Socket.IO delivery latency, network latency,
cloud latency, tunnel/ngrok latency, scalability, multi-client capacity,
recognition accuracy, F1, or model generalization.

Percentiles use `numpy.percentile(..., method="linear")`. Latency
outliers were not removed or winsorized. `Session.avg_latency_ms`, ping
RTT, and HUD latency were not used. Rule `score` is not a probability
and is not recognition accuracy. Processed FPS is not camera FPS and is
not system capacity.

---

## 1. Status

`PHASE_3A_COMPLETE`

Three independent process restarts produced valid 10 s warmup + ≥60 s
measurement windows on the local OpenCV path.

The previous attempt on this host was `PHASE_3A_INVALID` (no
`/dev/video0`). This rerun used the same clean venv after the Acer HD
Webcam enumerated as `/dev/video0`.

---

## 2. Environment verification

Clean venv: `/tmp/hgria-phase3a-venv`

- `include-system-site-packages = false`
- `site.ENABLE_USER_SITE = False`
- `PYTHONNOUSERSITE=1`
- loaded `cv2` is inside the venv, not user-site 4.11.0

| Check | Result |
|---|---|
| `python3 --version` | Python 3.10.12 |
| `cv2.__version__` | **4.10.0** |
| `cv2.__file__` | `/tmp/hgria-phase3a-venv/lib/python3.10/site-packages/cv2/__init__.py` |
| `opencv-python-headless` | 4.10.0.84 |
| `opencv-contrib-python` | 4.10.0.84 |
| `opencv-python` | not installed |
| Matches `requirements.txt` | **Yes** |

Camera probe before measurement: `VideoCapture(0)` opened, first frame
`640×480`, reported FPS 30.

`pip freeze` artifact: `docs/experiments/phase3a_pip_freeze.txt`

---

## 3. Test result

```
/tmp/hgria-phase3a-venv/bin/python -m pytest tests/ -q --tb=short
154 passed in 1.23s
```

All tests passed before any measurement process was started.

---

## 4. Run validity

Runtime settings (env only; committed `config/config.json` defaults were
not changed):

```
HGRIA_EVALUATION_MODE=true
HGRIA_EVALUATION_PREVIEW_ENABLED=false
HGRIA_EVALUATION_STRICT_CAMERA=true
HGRIA_INSTRUMENTATION_RUN_ID=phase3a-local-opencv-4be769ca6a0f-rN
HGRIA_INSTRUMENTATION_JSONL_PATH=docs/experiments/run_<sha>_rN/instrumentation.jsonl
```

Each process was confirmed via `GET /api/debug` **before** the
measurement window:

| Flag | Required | r1 | r2 | r3 |
|---|---|---|---|---|
| `evaluation_mode` | true | true | true | true |
| `preview_enabled` | false | false | false | false |
| `strict_camera` | true | true | true | true |
| `dynamic_gestures_enabled` | false | false | false | false |
| `colab_mode` | false | false | false | false |
| `colab_fallback` | false | false | false | false |
| `dropped_frames` | 0 | 0 | 0 | 0 |

Measurement window = JSONL rows whose wall-clock `timestamp` lies in
`[measure_start_utc, measure_end_utc]` recorded after the 10 s warmup.
Duration and processed FPS use `t_server_received` (monotonic). Warm-up
rows are excluded. All remaining processed frames are included
(UNKNOWN, no-hand, cooldown, command).

| Planned run | Validity | processed_frames | duration_s | notes |
|---|---|---|---|---|
| r1 | **VALID** | 1920 | 62.993 | dropped_frames=0 |
| r2 | **VALID** | 1921 | 63.015 | dropped_frames=0 |
| r3 | **VALID** | 1920 | 62.976 | dropped_frames=0 |

`backend/main.py` opened a pyngrok tunnel on each start (machine ngrok
config, not `HGRIA_*`). The tunnel process was killed after
`/api/debug` confirmed the OpenCV path and **before** the measurement
window. That is documented in Limitations. It is not treated as a
recognition-config override.

---

## 5. Per-run metrics

Valid measurement-window rows only.

| run | validity | processed_frames | duration_s | processed_fps | mean_server_ms | median_server_ms | p95_server_ms | p99_server_ms | command_rate | dropped_frames | cpu_mean_percent | rss_min_mb | rss_mean_mb | rss_max_mb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r1 | VALID | 1920 | 62.993 | 30.480 | 32.576 | 31.957 | 37.432 | 51.190 | 1.905 | 0 | 67.88 | 281.6 | 282.4 | 282.9 |
| r2 | VALID | 1921 | 63.015 | 30.485 | 32.574 | 31.946 | 39.453 | 52.943 | 1.365 | 0 | 68.84 | 279.0 | 280.2 | 280.6 |
| r3 | VALID | 1920 | 62.976 | 30.488 | 32.571 | 31.930 | 36.704 | 56.986 | 1.572 | 0 | 66.78 | 279.3 | 279.9 | 280.6 |

Command rate = `count(command_emitted=true) / duration_s`.
Dropped-frame rate = 0 on every valid run.

Run IDs:

- `phase3a-local-opencv-4be769ca6a0f-r1`
- `phase3a-local-opencv-4be769ca6a0f-r2`
- `phase3a-local-opencv-4be769ca6a0f-r3`

Artifacts:

- `docs/experiments/run_4be769ca6a0ffe02611a236b7cc4eac199c6c04c_r1/`
- `docs/experiments/run_4be769ca6a0ffe02611a236b7cc4eac199c6c04c_r2/`
- `docs/experiments/run_4be769ca6a0ffe02611a236b7cc4eac199c6c04c_r3/`

Each directory contains `instrumentation.jsonl`,
`instrumentation.run.json`, `debug_end.json`, `pip_freeze.txt`,
`uname.txt`, `config.json`, and `HEAD`.

---

## 6. Combined characterization

Report each run separately first (table above). The three runs are
**three process restarts on one host**, not independent statistical
samples of users.

**Latency.** Mean and median `total_server_ms` were tightly clustered
(mean 32.571–32.576 ms; median 31.930–31.957 ms). The tail is not
identical across restarts: P95 ranges **36.704–39.453 ms**; P99 ranges
**51.190–56.986 ms**. That run-to-run tail variation is part of the
result. It is not hidden by averaging.

**Processed FPS.** 30.480 / 30.485 / 30.488 JSONL rows per monotonic
second. That is the processed-frame rate in this window, near the
configured 30 FPS capture target. It is not a claim about camera
hardware FPS or system capacity.

**Command rate.** 1.905 / 1.365 / 1.572 commands per second. This
depends on what was in front of the live webcam (pose, cooldown, no-hand
frames). It is not a throughput or accuracy metric.

**CPU / RSS.** Process CPU mean 66.78–68.84% (process scope; can exceed
100 on multi-core, did not here). RSS stayed near 280–283 MiB.

**Funnel (measurement window only, from `exit_reason`).**

| run | no_hand | noise | temporal | cooldown | unmapped | command | n |
|---|---|---|---|---|---|---|---|
| r1 | 364 (0.190) | 194 (0.101) | 362 (0.189) | 880 (0.458) | 0 | 120 (0.0625) | 1920 |
| r2 | 383 (0.199) | 39 (0.020) | 582 (0.303) | 831 (0.433) | 0 | 86 (0.0448) | 1921 |
| r3 | 349 (0.182) | 73 (0.038) | 450 (0.234) | 949 (0.494) | 0 | 99 (0.0516) | 1920 |

Funnel rates move with the live scene. They are not recognition
accuracy.

---

## 7. Stage metrics

Non-null `*_ms` values in the measurement window. Classification
excludes rows where `classification_ms` is null. Command generation
includes only rows where `command_generation_ms` is present.
`total_server` includes every processed measurement-window frame.

| Stage | run | P50 | P95 | P99 | n |
|---|---|---|---|---|---|
| capture | r1 | 23.030 | 27.394 | 27.997 | 1920 |
| capture | r2 | 23.130 | 27.487 | 28.229 | 1921 |
| capture | r3 | 23.045 | 27.513 | 28.493 | 1920 |
| preprocess | r1 | 0.416 | 0.591 | 1.397 | 1920 |
| preprocess | r2 | 0.360 | 0.547 | 1.334 | 1921 |
| preprocess | r3 | 0.361 | 0.565 | 1.418 | 1920 |
| mediapipe | r1 | 8.079 | 22.640 | 26.394 | 1920 |
| mediapipe | r2 | 8.057 | 22.963 | 26.647 | 1921 |
| mediapipe | r3 | 8.086 | 17.363 | 26.261 | 1920 |
| landmark_extraction | r1 | 0.070 | 0.136 | 0.247 | 1556 |
| landmark_extraction | r2 | 0.070 | 0.141 | 0.263 | 1538 |
| landmark_extraction | r3 | 0.070 | 0.140 | 0.252 | 1571 |
| classification | r1 | 0.075 | 0.127 | 0.162 | 1556 |
| classification | r2 | 0.073 | 0.132 | 0.165 | 1538 |
| classification | r3 | 0.074 | 0.129 | 0.173 | 1571 |
| noise_filter | r1 | 0.008 | 0.035 | 0.055 | 1556 |
| noise_filter | r2 | 0.008 | 0.021 | 0.037 | 1538 |
| noise_filter | r3 | 0.007 | 0.032 | 0.040 | 1571 |
| temporal_filter | r1 | 0.016 | 0.032 | 0.045 | 1362 |
| temporal_filter | r2 | 0.015 | 0.029 | 0.041 | 1499 |
| temporal_filter | r3 | 0.016 | 0.032 | 0.047 | 1498 |
| command_generation | r1 | 0.016 | 0.034 | 0.048 | 120 |
| command_generation | r2 | 0.015 | 0.024 | 0.051 | 86 |
| command_generation | r3 | 0.015 | 0.033 | 0.043 | 99 |
| total_server | r1 | 31.957 | 37.432 | 51.190 | 1920 |
| total_server | r2 | 31.946 | 39.453 | 52.943 | 1921 |
| total_server | r3 | 31.930 | 36.704 | 56.986 | 1920 |

Capture P50 (~23 ms) is a large share of `total_server_ms`. That is
OpenCV `VideoCapture.read()` time inside `_process_frame`, not network
or browser time. MediaPipe P95 is the other visible contributor and
varies across restarts (r3 P95 17.4 ms vs r1/r2 ~22.6–23.0 ms).

---

## 8. Reproducibility metadata

| Item | Value |
|---|---|
| Git SHA | `4be769ca6a0ffe02611a236b7cc4eac199c6c04c` |
| Working tree | that SHA; untracked `dynamic_gestures/`, this result, and run dirs |
| Committed `config.json` SHA-256 | `1ac7460f3582dddd27bbe9cb44bc450122a522719d885a9ee7cbc6e909c12e48` |
| Live sidecar `config_sha256` | differs per run (includes `run_id` and `jsonl_path`) |
| Python | 3.10.12 |
| OpenCV version | 4.10.0 |
| OpenCV file | `/tmp/hgria-phase3a-venv/lib/python3.10/site-packages/cv2/__init__.py` |
| OpenCV distributions | `opencv-python-headless==4.10.0.84`, `opencv-contrib-python==4.10.0.84` |
| Environment vs `requirements.txt` | **matches** |
| OS | Linux 6.8.0-138-generic |
| CPU | Intel(R) Core(TM) i7-10750H CPU @ 2.60GHz, 12 CPUs |
| RAM | 38 GiB total |
| pip freeze | `docs/experiments/phase3a_pip_freeze.txt` |
| evaluation_mode | true |
| preview_enabled | false |
| strict_camera | true |
| dynamic_gestures.enabled | false |
| camera | OpenCV index 0, 640×480, 30 FPS, `colab_mode=false` |
| Run IDs | `phase3a-local-opencv-4be769ca6a0f-r{1,2,3}` |
| Validity | r1 VALID; r2 VALID; r3 VALID |

`GESTURE_RULES`, thresholds, smoothing, MediaPipe knobs, FSM, command
mapping, ONNX, Docker, and Kubernetes were not changed.

---

## 9. Limitations

This experiment measures local server-processing latency only.

- No end-to-end, browser, network, cloud, or scalability claim is made.
- No recognition accuracy or F1 is claimed.
- Processed FPS is not “camera FPS” or “system capacity.”
- Rule score is not a calibrated probability.
- The scene is a live webcam, not a pinned video corpus. Funnel counts
  and command rate are scene-dependent.
- MediaPipe `Hands(static_image_mode=False)` is stateful; per-frame
  `mediapipe_ms` values are not i.i.d.
- `cpu_percent` / `rss_mb` are 1 Hz process samples copied onto frame
  rows.
- `backend/main.py` still auto-starts ngrok when a local ngrok config
  exists. Tunnels were terminated before each measurement window. This
  run is still a **local server-processing** measurement, not a cloud
  or tunnel measurement.
- Debug `avg_total_server_ms` includes warmup; published latency uses
  measurement-window JSONL only.

---

## 10. Exact next phase

Phase 3A (local OpenCV server-processing baseline) is complete.

Do **not** treat this as permission to start local browser E2E, cloud,
ngrok-as-the-system-under-test, Docker, Kubernetes, ONNX/dynamic
evaluation, or accuracy/F1. Those require separate instrumentation and
a separate protocol.

The next experiment must be specified explicitly. Pre-Phase 3 still
marks browser E2E / cloud / scalability as not ready
(`webcam_bridge.js` frame correlation, client/HUD timers, and
deployment harnesses are not in this measurement).
