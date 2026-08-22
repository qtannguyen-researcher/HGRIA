**PHASE_3A_COMPLETE**

This experiment measures local server-processing latency only. It does not measure end-to-end gesture-to-command latency, browser latency, network latency, cloud latency, scalability, multi-client capacity, recognition accuracy, or F1.

The webcam is now present (`/dev/video0`, Acer HD Webcam). Three valid OpenCV runs completed. Report: `docs/experiments/phase3a_result.md`.

---

### 1. Status

**PHASE_3A_COMPLETE** — 3 valid process restarts (10 s warmup discarded, ≥60 s measurement, ≥1000 processed rows, `dropped_frames=0`).

---

### 2. Environment verification

Clean venv `/tmp/hgria-phase3a-venv` (`ENABLE_USER_SITE=False`). User-site OpenCV 4.11 was not used.

| Check | Result |
|---|---|
| Python | 3.10.12 |
| `cv2.__version__` | **4.10.0** |
| `cv2.__file__` | `/tmp/hgria-phase3a-venv/lib/python3.10/site-packages/cv2/__init__.py` |
| Distributions | `opencv-python-headless==4.10.0.84`, `opencv-contrib-python==4.10.0.84` |
| vs `requirements.txt` | **matches** |
| Camera | `VideoCapture(0)` opened, 640×480, 30 FPS |

---

### 3. Test result

```
154 passed in 1.23s
```

---

### 4. Run validity

Before each window, `/api/debug` showed `evaluation_mode=true`, `preview_enabled=false`, `strict_camera=true`, `dynamic_gestures_enabled=false`, `colab_mode=false`, `colab_fallback=false`.

| run | validity | processed_frames | duration_s |
|---|---|---|---|
| r1 | **VALID** | 1920 | 62.993 |
| r2 | **VALID** | 1921 | 63.015 |
| r3 | **VALID** | 1920 | 62.976 |

`backend/main.py` still auto-opened ngrok from the machine config. Each tunnel was killed after debug confirm and **before** the measurement window.

---

### 5. Per-run metrics

Measurement-window rows only. Percentiles: `numpy.percentile(..., method="linear")`. No outlier removal.

| run | validity | processed_frames | duration_s | processed_fps | mean_server_ms | median_server_ms | p95_server_ms | p99_server_ms | command_rate | dropped_frames | cpu_mean_percent | rss_min_mb | rss_mean_mb | rss_max_mb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r1 | VALID | 1920 | 62.993 | 30.480 | 32.576 | 31.957 | 37.432 | 51.190 | 1.905 | 0 | 67.88 | 281.6 | 282.4 | 282.9 |
| r2 | VALID | 1921 | 63.015 | 30.485 | 32.574 | 31.946 | 39.453 | 52.943 | 1.365 | 0 | 68.84 | 279.0 | 280.2 | 280.6 |
| r3 | VALID | 1920 | 62.976 | 30.488 | 32.571 | 31.930 | 36.704 | 56.986 | 1.572 | 0 | 66.78 | 279.3 | 279.9 | 280.6 |

---

### 6. Combined characterization

These are three process restarts on one host, not samples of users.

- Mean / median `total_server_ms` clustered tightly (~32.57 / ~31.93–31.96 ms).
- The tail is **not** identical: P95 **36.704–39.453 ms**, P99 **51.190–56.986 ms**.
- Processed FPS ~30.48 is JSONL rows per monotonic second, near the 30 FPS target. It is not camera FPS or system capacity.
- Command rate **1.365–1.905 /s** follows the live scene (cooldown, no-hand). It is not accuracy or throughput capacity.

Funnel (`exit_reason`, window only):

| run | no_hand | noise | temporal | cooldown | unmapped | command |
|---|---|---|---|---|---|---|
| r1 | 364 (0.190) | 194 (0.101) | 362 (0.189) | 880 (0.458) | 0 | 120 (0.0625) |
| r2 | 383 (0.199) | 39 (0.020) | 582 (0.303) | 831 (0.433) | 0 | 86 (0.0448) |
| r3 | 349 (0.182) | 73 (0.038) | 450 (0.234) | 949 (0.494) | 0 | 99 (0.0516) |

---

### 7. Stage metrics

| Stage | run | P50 | P95 | P99 | n |
|---|---|---|---|---|---|
| capture | r1 / r2 / r3 | 23.030 / 23.130 / 23.045 | 27.394 / 27.487 / 27.513 | 27.997 / 28.229 / 28.493 | 1920 / 1921 / 1920 |
| preprocess | r1 / r2 / r3 | 0.416 / 0.360 / 0.361 | 0.591 / 0.547 / 0.565 | 1.397 / 1.334 / 1.418 | 1920 / 1921 / 1920 |
| mediapipe | r1 / r2 / r3 | 8.079 / 8.057 / 8.086 | 22.640 / 22.963 / 17.363 | 26.394 / 26.647 / 26.261 | 1920 / 1921 / 1920 |
| landmark_extraction | r1 / r2 / r3 | 0.070 / 0.070 / 0.070 | 0.136 / 0.141 / 0.140 | 0.247 / 0.263 / 0.252 | 1556 / 1538 / 1571 |
| classification | r1 / r2 / r3 | 0.075 / 0.073 / 0.074 | 0.127 / 0.132 / 0.129 | 0.162 / 0.165 / 0.173 | 1556 / 1538 / 1571 |
| noise_filter | r1 / r2 / r3 | 0.008 / 0.008 / 0.007 | 0.035 / 0.021 / 0.032 | 0.055 / 0.037 / 0.040 | 1556 / 1538 / 1571 |
| temporal_filter | r1 / r2 / r3 | 0.016 / 0.015 / 0.016 | 0.032 / 0.029 / 0.032 | 0.045 / 0.041 / 0.047 | 1362 / 1499 / 1498 |
| command_generation | r1 / r2 / r3 | 0.016 / 0.015 / 0.015 | 0.034 / 0.024 / 0.033 | 0.048 / 0.051 / 0.043 | 120 / 86 / 99 |
| total_server | r1 / r2 / r3 | 31.957 / 31.946 / 31.930 | 37.432 / 39.453 / 36.704 | 51.190 / 52.943 / 56.986 | 1920 / 1921 / 1920 |

Capture (`VideoCapture.read`) is the largest named share of `total_server_ms`. MediaPipe is the other visible term; its P95 moved across restarts.

---

### 8. Reproducibility metadata

| Item | Value |
|---|---|
| Git SHA | `4be769ca6a0ffe02611a236b7cc4eac199c6c04c` |
| config.json SHA-256 | `1ac7460f3582dddd27bbe9cb44bc450122a522719d885a9ee7cbc6e909c12e48` |
| Python / OpenCV | 3.10.12 / 4.10.0 |
| OS / CPU / RAM | Linux 6.8.0-138-generic / i7-10750H 12 CPUs / 38 GiB |
| pip freeze | `docs/experiments/phase3a_pip_freeze.txt` |
| Evaluation | mode=true, preview=false, strict_camera=true, dynamic=false |
| Camera | OpenCV index 0, 640×480, 30 FPS, colab_mode=false |
| Run IDs | `phase3a-local-opencv-4be769ca6a0f-r{1,2,3}` |
| Validity | all VALID |

---

### 9. Limitations

This experiment measures local server-processing latency only.

- No e2e / browser / network / cloud / scalability / accuracy claim.
- Live webcam, not a pinned video; funnel and command rate are scene-dependent.
- MediaPipe tracking is stateful.
- Ngrok auto-start was terminated before each window; this is still not a tunnel measurement.

---

### 10. Exact next phase

Phase 3A is done. Do **not** start browser E2E, cloud, Docker/Kubernetes, ONNX/dynamic evaluation, or accuracy/F1 until that experiment is specified separately. Pre-Phase 3 still marks those as not instrumented.