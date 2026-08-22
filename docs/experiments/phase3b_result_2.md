# PHASE_3B_MEASUREMENT_RESULT

## 1. Status

**PHASE_3B_COMPLETE**

Three independent process restarts produced valid local browser E2E measurements (10 s warmup discarded, ≥60 s, ≥1000 client frames). Application code was not modified. Full write-up: `docs/experiments/phase3b_result.md`.

This is local browser capture → HTTP → server → Socket.IO → command-receive only. It is not cloud, tunnel, one-way network, scalability, or accuracy.

## 2. Frozen SHA

`8764213c5c568fe20e01a1f387d8a80c8269aa64`

Phase 3A SHA (unchanged semantics): `4be769ca6a0ffe02611a236b7cc4eac199c6c04c`

All three run `HEAD` files match this SHA. No backend/frontend/config edits during collection.

## 3. Environment

Clean venv `/tmp/hgria-phase3a-venv` (`ENABLE_USER_SITE=False`, `PYTHONNOUSERSITE=1`).

| Check | Result |
|---|---|
| Python | 3.10.12 |
| `cv2` | **4.10.0** from `/tmp/hgria-phase3a-venv/lib/python3.10/site-packages/cv2/__init__.py` |
| Distributions | `opencv-python-headless==4.10.0.84`, `opencv-contrib-python==4.10.0.84` |
| Pins | mediapipe 0.10.14, numpy 1.26.4, scipy 1.15.3, flask 3.0.3 |
| Host | Linux 6.8.0-138-generic, i7-10750H 12 CPUs, 38 GiB |
| Camera | Acer HD Webcam, Chrome held `/dev/video0`; server PID did not |
| Page | `http://localhost:5000/index.html?evaluation=true` (Flask `/` is 404) |
| Flags | evaluation=true, preview=false, strict_camera=true, browser_source=true, colab=false, dynamic=false |
| Ngrok | auto-started, killed before each timed window |

Committed `config.json` was not edited. Env overrides only.

## 4. Run validity

| run | validity | client frames | server frames | unmatched | matched E2E | duration_s |
|---|---|---:|---:|---:|---:|---:|
| r1 | **VALID** | 1911 | 1910 | 1 | 25 | 63.000 |
| r2 | **VALID** | 1911 | 1910 | 1 | 35 | 62.997 |
| r3 | **VALID** | 1911 | 1910 | 1 | 0 | 62.998 |

r3 is valid: instrumentation kept producing increasing `frame_id`s. The live scene was entirely `no_hand`, so E2E `n=0`. Unmatched frames (1/run) are last-write-wins, reported not fabricated.

## 5. Server processing

| run | FPS | mean | median | P95 | P99 | CPU % | RSS mean MiB | drops |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| r1 | 30.317 | 21.635 | 21.559 | 33.427 | 39.745 | 85.49 | 284.3 | 0 |
| r2 | 30.319 | 16.713 | 14.937 | 25.833 | 31.892 | 71.12 | 286.3 | 0 |
| r3 | 30.319 | 20.760 | 20.420 | 23.476 | 26.721 | 81.34 | 280.0 | 0 |

Command rate: 0.397 / 0.556 / 0.000 per second. Scene-dependent. Not accuracy.

Matched-command subset `total_server_ms`: r1 n=25 mean 14.515 ms; r2 n=35 mean 14.251 ms; r3 n=0.

## 6. HTTP request/ack

Browser HTTP request/ack latency. Not pure network latency, not upload latency, not one-way network latency.

| run | mean | median | P95 | P99 | n |
|---|---:|---:|---:|---:|---:|
| r1 | 3.188 | 3.100 | 3.600 | 4.690 | 1911 |
| r2 | 3.078 | 3.000 | 3.400 | 4.191 | 1910 |
| r3 | 2.889 | 2.800 | 3.200 | 3.600 | 1910 |

## 7. E2E latency

`t_client_cmd_recv − t_client_capture`. Join only by `run_id + frame_id`.

| run | mean | median | P95 | P99 | n |
|---|---:|---:|---:|---:|---:|
| r1 | 32.008 | 29.500 | 41.580 | 41.676 | 25 |
| r2 | 31.226 | 30.700 | 41.740 | 45.996 | 35 |
| r3 | — | — | — | — | 0 |

This is capture-to-command-receive, not physical gesture onset. Not ping RTT.

## 8. Frame correlation

| run | submitted | processed | unmatched | command emitted | command received | matched E2E |
|---|---:|---:|---:|---:|---:|---:|
| r1 | 1911 | 1910 | 1 | 25 | 25 | 25 |
| r2 | 1911 | 1910 | 1 | 35 | 35 | 35 |
| r3 | 1911 | 1910 | 1 | 0 | 0 | 0 |

`server_rows_without_client_capture`: 0 / 0 / 0.

## 9. Funnel

System-processing counts. Not accuracy. Not F1.

| run | no_hand | noise | temporal | cooldown | unmapped | command |
|---|---:|---:|---:|---:|---:|---:|
| r1 | 1354 | 409 | 1 | 121 | 0 | 25 |
| r2 | 584 | 1025 | 32 | 234 | 0 | 35 |
| r3 | 1910 | 0 | 0 | 0 | 0 | 0 |

## 10. Phase 3A vs Phase 3B

Phase 3A uses OpenCV capture. Phase 3B uses browser JPEG capture/upload. The difference is not pure network overhead.

Comparable (server processing): both ~30 processed FPS, 0 drops. Phase 3B mean `total_server_ms` is lower (16.7–21.6 vs Phase 3A ~32.6) because FrameStore replace `VideoCapture.read` (~23 ms in 3A). Phase 3B CPU is higher (same host also runs Chrome + JPEG decode).

Not the same metric: HTTP request/ack and browser E2E exist only in Phase 3B. Do not compare them to Phase 3A server latency as identical quantities. `E2E − server` is not one-way network latency.

## 11. Limitations

- HTTP request/ack is not pure upload latency.
- No exact one-way network latency.
- No cloud.
- No tunnel (ngrok killed before each window).
- No scalability.
- Live webcam scene affects command rate (r3 was all `no_hand`).
- E2E is capture-to-command-receive, not physical gesture onset.
- Browser scheduling and Socket.IO delivery are included in E2E.

## 12. Exact next phase

Phase 3B local browser measurement is done. Do **not** start cloud, Docker, Kubernetes, tunnel evaluation, ONNX/dynamic measurement, or accuracy/F1 unless that experiment is specified separately.