# Phase 3B Result

## 1. Status

`PHASE_3B_COMPLETE`

Three independent process restarts produced valid local browser E2E
measurements (10 s warmup discarded, ≥60 s measurement, ≥1000
client-submitted frames). Application code was not modified during
collection. The benchmark SHA is the tree that produced the data.

This experiment measures local browser capture → HTTP POST → server
processing → Socket.IO → browser command-receive only.

It does **not** measure one-way network latency, ping RTT as E2E, cloud
latency, tunnel latency, scalability, multi-client capacity, recognition
accuracy, F1, or dynamic/ONNX performance.

Percentiles use `numpy.percentile(..., method="linear")`. High-latency
samples were not removed. Join key is `run_id + frame_id` only.

---

## 2. Experimental objective

Measure **local browser E2E** on one host:

| Metric | Definition | Name used here |
|---|---|---|
| A | `total_server_ms` | server processing |
| B | `t_client_http_ack - t_client_http_send` | browser HTTP request/ack latency |
| D | `t_client_cmd_recv - t_client_capture` | browser E2E (primary new metric) |

D is computed only from matching `performance.now()` timestamps in the
same browser process. Server `perf_counter()` is never subtracted from
browser clocks.

Phase 3A used OpenCV capture. Phase 3B uses browser JPEG capture/upload.
Those capture paths are not interchangeable.

---

## 3. Environment

Clean venv: `/tmp/hgria-phase3a-venv`

- `include-system-site-packages = false`
- `site.ENABLE_USER_SITE = False`
- `PYTHONNOUSERSITE=1`
- loaded `cv2` is inside the venv, not user-site 4.11.0

| Check | Result |
|---|---|
| Git SHA | `8764213c5c568fe20e01a1f387d8a80c8269aa64` |
| Frozen Phase 3A SHA | `4be769ca6a0ffe02611a236b7cc4eac199c6c04c` |
| `python3 --version` | Python 3.10.12 |
| `cv2.__version__` | **4.10.0** |
| `cv2.__file__` | `/tmp/hgria-phase3a-venv/lib/python3.10/site-packages/cv2/__init__.py` |
| `opencv-python-headless` | 4.10.0.84 |
| `opencv-contrib-python` | 4.10.0.84 |
| `mediapipe` / `numpy` / `scipy` / `flask` | 0.10.14 / 1.26.4 / 1.15.3 / 3.0.3 |
| OS / kernel | Linux 6.8.0-138-generic |
| CPU | Intel Core i7-10750H, 12 CPUs |
| RAM | 38 GiB |
| Camera | Acer HD Webcam (`/dev/video0`), 640×480, ~30 FPS |
| Browser | Playwright Chromium (real HD Webcam; no fake video device) |
| Page | `http://localhost:5000/index.html?evaluation=true` |
| committed `config/config.json` SHA-256 | `1ac7460f3582dddd27bbe9cb44bc450122a522719d885a9ee7cbc6e909c12e48` |
| live merged config SHA-256 | `365394d6fbbbadc716a230fe3b5a3eb653e2fc26047f0e46fb13275573ee64bd` |

`/` returns 404 on this Flask static layout. The evaluation frontend was
opened as `/index.html?evaluation=true`. Origin is `localhost` so CSP
`connect-src 'self'` allows `/api/frame`, `/api/client-log`, and
Socket.IO. Application code was not changed to work around this.

Committed `config/config.json` defaults were not edited. Temporary
overrides were environment variables only:

```
HGRIA_EVALUATION_MODE=true
HGRIA_EVALUATION_PREVIEW_ENABLED=false
HGRIA_EVALUATION_STRICT_CAMERA=true
HGRIA_CAMERA_BROWSER_SOURCE=true
HGRIA_INSTRUMENTATION_RUN_ID=phase3b-local-browser-<SHA>-rN
HGRIA_INSTRUMENTATION_JSONL_PATH=docs/experiments/run_<SHA>_rN/instrumentation.jsonl
HGRIA_INSTRUMENTATION_CLIENT_JSONL_PATH=docs/experiments/run_<SHA>_rN/client_instrumentation.jsonl
```

`backend/main.py` still auto-opened ngrok from the machine config. Each
tunnel was killed after debug confirm and **before** the timed window.
Tunnel traffic is not part of this experiment.

Before each window, `/api/debug` showed `evaluation_mode=true`,
`preview_enabled=false`, `strict_camera=true`, `browser_source=true`,
`colab_mode=false`, `colab_fallback=false`,
`dynamic_gestures_enabled=false`. After the browser started, `fuser`
showed Chrome holding `/dev/video0`. The server PID did not hold the
device.

Per-run artifacts: `docs/experiments/run_8764213c5c568fe20e01a1f387d8a80c8269aa64_r{1,2,3}/`
(includes server/client JSONL, sidecar, `debug_end.json`, `pip_freeze.txt`,
`environment.txt`, `HEAD`, `config.json`).

---

## 4. Run validity

| run | validity | client frames | server frames | unmatched | matched E2E | duration_s |
|---|---|---:|---:|---:|---:|---:|
| r1 | **VALID** | 1911 | 1910 | 1 | 25 | 63.000 |
| r2 | **VALID** | 1911 | 1910 | 1 | 35 | 62.997 |
| r3 | **VALID** | 1911 | 1910 | 1 | 0 | 62.998 |

All three runs satisfy the validity criteria: clean venv, OpenCV 4.10.0 /
4.10.0.84, user site disabled, evaluation/preview/strict/browser flags,
`colab_mode=false`, `colab_fallback=false`, `dynamic=false`, no debug /
keyboard / UI_BYPASS / test-emit injection, ≥1000 client frames, ≥60 s,
no application-code changes during the run.

Unmatched client frames (1 per run) are last-write-wins FrameStore
overwrites. They are reported, not fabricated into server rows. Browser
instrumentation continued producing increasing `frame_id` values through
each window, so the runs are not invalidated.

r3 emitted **zero** commands because the live scene was entirely
`no_hand`. That is a scene observation. It does not make the run
invalid. E2E `n=0` for r3 is reported as such.

---

## 5. Server processing

Measurement-window server JSONL only. Same inclusion rule as Phase 3A:
every processed window row; no outlier removal.

| run | FPS | mean | median | P95 | P99 | CPU % | RSS mean MiB | drops |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| r1 | 30.317 | 21.635 | 21.559 | 33.427 | 39.745 | 85.49 | 284.3 | 0 |
| r2 | 30.319 | 16.713 | 14.937 | 25.833 | 31.892 | 71.12 | 286.3 | 0 |
| r3 | 30.319 | 20.760 | 20.420 | 23.476 | 26.721 | 81.34 | 280.0 | 0 |

Processed FPS is JSONL rows per monotonic second, near the 30 FPS
target. It is not camera FPS and not system capacity.

Command rate (window commands / duration): r1 **0.397 /s**, r2
**0.556 /s**, r3 **0.000 /s**. This follows the live webcam scene. It is
not recognition accuracy and not throughput capacity.

For matched command frames only, server `total_server_ms` was:

| run | n | mean | median | P95 | P99 |
|---|---:|---:|---:|---:|---:|
| r1 | 25 | 14.515 | 14.184 | 17.766 | 19.766 |
| r2 | 35 | 14.251 | 13.908 | 16.946 | 18.350 |
| r3 | 0 | — | — | — | — |

`E2E − server` is **not** one-way network latency. The E2E interval
contains browser capture, HTTP transfer, server processing, Socket.IO
delivery, and browser scheduling.

---

## 6. HTTP request/ack

Browser HTTP request/ack latency:
`t_client_http_ack − t_client_http_send`.

This is **not** pure network latency, upload latency, or one-way
network latency. The interval includes browser request handling and the
empty 204 response.

| run | mean | median | P95 | P99 | n |
|---|---:|---:|---:|---:|---:|
| r1 | 3.188 | 3.100 | 3.600 | 4.690 | 1911 |
| r2 | 3.078 | 3.000 | 3.400 | 4.191 | 1910 |
| r3 | 2.889 | 2.800 | 3.200 | 3.600 | 1910 |

---

## 7. E2E latency

`E2E_latency_ms = t_client_cmd_recv − t_client_capture`

A sample is included only when client capture, matching server row,
`command_emitted=true`, browser command receive, matching `frame_id` and
`run_id`, and E2E ≥ 0 all hold. Negative E2E samples rejected: 0.

| run | mean | median | P95 | P99 | min | max | n |
|---|---:|---:|---:|---:|---:|---:|---:|
| r1 | 32.008 | 29.500 | 41.580 | 41.676 | 23.300 | 41.700 | 25 |
| r2 | 31.226 | 30.700 | 41.740 | 45.996 | 22.600 | 47.900 | 35 |
| r3 | — | — | — | — | — | — | 0 |

This is capture-to-command-receive in the browser, not physical gesture
onset. r3 has no E2E samples because no command was emitted.

---

## 8. Frame correlation

Join: `run_id + frame_id` only. No row-order, timestamp-proximity,
gesture-name, or nearest-frame matching.

| run | submitted | processed | unmatched | command emitted | command received | matched E2E |
|---|---:|---:|---:|---:|---:|---:|
| r1 | 1911 | 1910 | 1 | 25 | 25 | 25 |
| r2 | 1911 | 1910 | 1 | 35 | 35 | 35 |
| r3 | 1911 | 1910 | 1 | 0 | 0 | 0 |

`server_rows_without_client_capture`: 0 / 0 / 0.

Client `frame_id` ranges in the measurement window: r1 354–2264, r2
353–2263, r3 352–2262. IDs increased through each window.

---

## 9. Funnel

System-processing funnel from server `exit_reason` (window only).
These are **not** accuracy, precision, recall, or F1.

| run | no_hand | noise | temporal | cooldown | unmapped | command |
|---|---:|---:|---:|---:|---:|---:|
| r1 | 1354 | 409 | 1 | 121 | 0 | 25 |
| r2 | 584 | 1025 | 32 | 234 | 0 | 35 |
| r3 | 1910 | 0 | 0 | 0 | 0 | 0 |

JPEG browser frames use blur threshold 30 (`colab_mode=false`; the
Colab `30/4` divisor was not applied). That can increase the noise bin
versus Colab. Thresholds were not changed.

---

## 10. Phase 3A comparison

Phase 3A uses **OpenCV capture**.
Phase 3B uses **browser JPEG capture/upload**.

The difference between the two experiments is **not** pure network
overhead.

### Comparable: server processing

Phase 3A local OpenCV (`4be769ca6a0ffe02611a236b7cc4eac199c6c04c`):

| run | FPS | mean server ms | median | P95 | P99 | CPU % | RSS mean MiB | drops |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| r1 | 30.480 | 32.576 | 31.957 | 37.432 | 51.190 | 67.88 | 282.4 | 0 |
| r2 | 30.485 | 32.574 | 31.946 | 39.453 | 52.943 | 68.84 | 280.2 | 0 |
| r3 | 30.488 | 32.571 | 31.930 | 36.704 | 56.986 | 66.78 | 279.9 | 0 |

Phase 3B local browser JPEG (this experiment):

| run | FPS | mean server ms | median | P95 | P99 | CPU % | RSS mean MiB | drops |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| r1 | 30.317 | 21.635 | 21.559 | 33.427 | 39.745 | 85.49 | 284.3 | 0 |
| r2 | 30.319 | 16.713 | 14.937 | 25.833 | 31.892 | 71.12 | 286.3 | 0 |
| r3 | 30.319 | 20.760 | 20.420 | 23.476 | 26.721 | 81.34 | 280.0 | 0 |

Both stay near 30 processed FPS with zero drops. Phase 3B
`total_server_ms` is lower because FrameStore capture replaces
`VideoCapture.read` (~23 ms in Phase 3A). CPU is higher on the browser
path (JPEG decode + Chrome + pipeline on the same host). These are not
identical workloads.

### Not comparable as the same metric: HTTP and E2E

Phase 3A did not measure browser HTTP request/ack or capture-to-command
receive. Those appear only in Phase 3B (sections 6 and 7).

---

## 11. Limitations

- HTTP request/ack is not pure upload latency and not one-way network
  latency.
- There is no exact one-way network latency. `D − A` is not that
  quantity.
- No cloud measurement.
- No tunnel measurement (ngrok was terminated before each window).
- No scalability or multi-client capacity claim.
- Live webcam scene affects command rate and the funnel. r3 was
  entirely `no_hand`.
- E2E is capture-to-command-receive, not physical gesture onset.
- Browser scheduling and Socket.IO delivery are included in E2E.
- Browser JPEG vs OpenCV capture means Phase 3A and Phase 3B server
  times are comparable only as server-processing on different capture
  paths.
- `/` 404 required `/index.html`; CSP requires the `localhost` origin.
- `webcam_bridge.js` was not the live file; `webcam_capture.js` was.

---

## 12. Conclusion

The experiment establishes a reproducible local browser
capture-to-command-receive measurement. It does not establish cloud
latency, one-way network latency, scalability, or recognition accuracy.

Exact next phase: do **not** start cloud, Docker, Kubernetes, ngrok
evaluation, ONNX/dynamic measurement, or accuracy/F1 unless that
experiment is specified separately.
