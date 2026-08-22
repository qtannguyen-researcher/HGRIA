# HGRIA Phase 2 — server-side instrumentation

This document describes **how** the static MediaPipe / rule-based pipeline is
timed and logged. It is **not** a results paper.

- JSONL lines are **raw observations**, not benchmark results.
- No performance claim is made in this phase.
- WebSocket ping RTT is **not** end-to-end gesture latency.
- The rule `score` / command `confidence` field is a **geometric rule score**,
  not a calibrated probability.

Record the git SHA of the tree you actually ran:

```bash
git rev-parse HEAD
```

---

## Purpose

Make the **existing static pipeline** measurable without changing recognition
behaviour. Dynamic ONNX timing is out of scope: `dynamic_gestures.enabled=false`
and ONNX durations are not recorded even if that path is later turned on.

---

## Clock

| Use | Clock | Function |
|---|---|---|
| All duration calculations | Monotonic, high-resolution | `time.perf_counter()` via `backend.utils.instrumentation.mono_now()` |
| JSONL `timestamp`, command `server_emitted_at`, existing `Command.timestamp` | UTC wall clock | `datetime.now(timezone.utc)` / `wall_iso()` |

**Do not** subtract wall-clock timestamps to compute latency.

`time.perf_counter()` is process-local and not comparable across machines or
reboots. It is the correct clock for stage durations on one run.

---

## frame_id

Every captured / submitted frame gets a unique `frame_id` so we can correlate:

```
client frame  →  server processing  →  command emission
```

| Path | Where assigned | Rule |
|---|---|---|
| OpenCV `CameraModule.capture()` | Server | Incrementing integer from `SERVER_FRAME_IDS` |
| Browser / Colab `POST /api/frame` | Client, if present | `data.frame_id` is stored on `FrameStore.put()` and reused at consume |
| Browser / Colab, no client id | Server | Same incrementing integer as OpenCV |

`POST /api/frame` is unchanged when `frame_id` is omitted (still HTTP 204).
The field is optional.

`frontend/js/webcam_bridge.js` is intended to send an incrementing `frame_id`.
If that file cannot be edited in a given checkout (for example it is
root-owned), the server still assigns an ID. Correlation then starts at
server receive, not at the browser capture call.

---

## Timestamps (monotonic)

All `t_*` values are `time.perf_counter()` seconds.

| Timestamp | Where captured | Meaning |
|---|---|---|
| `t_capture` | Start of `CameraModule.capture()` (before `strategy.read()`) | Server begins acquiring this frame |
| `t_server_received` | OpenCV: same instant as `t_capture`. Colab: `FrameStore.put()` | First server sighting of the frame bytes |
| `t_preprocess_done` | Return of `FramePreprocessor.process()` | BGR→RGB / CLAHE finished |
| `t_mediapipe_done` | Return of `HandDetector.detect()` | MediaPipe Hands returned |
| `t_classification_done` | Return of `GestureClassifier.classify()` | Rule scores computed |
| `t_command_generated` | Return of `CommandGenerator.generate()` | Command object created |
| `t_command_emitted` | Immediately after `socketio.emit("gesture_command", …)` | Payload left the server emit call |

Stages that did not run on a given frame leave the corresponding timestamp
`null` (for example no hand → no classification / command timestamps).

For the Colab path, `t_server_received` can be **earlier** than `t_capture`
because `put()` happens on the HTTP thread and `capture()` happens later in
the pipeline thread. That is expected. `total_server_ms` is still measured
from `t_server_received`.

---

## Latency metrics (formulas)

Durations are milliseconds from the monotonic clock.

| Metric | Formula | Call timed |
|---|---|---|
| `capture_ms` | `(t_after_capture − t_before_capture) × 1000` | `CameraModule.capture()` |
| `preprocess_ms` | `(t_preprocess_done − t_preprocess_start) × 1000` | `FramePreprocessor.process()` |
| `mediapipe_ms` | `(t_mediapipe_done − t_mediapipe_start) × 1000` | `HandDetector.detect()` |
| `landmark_extraction_ms` | `(t_extract_done − t_extract_start) × 1000` | `LandmarkExtractor.extract_all()` |
| `classification_ms` | `(t_classification_done − t_classify_start) × 1000` | `GestureClassifier.classify()` |
| `noise_filter_ms` | `(t_noise_done − t_noise_start) × 1000` | `NoiseFilter.filter()` |
| `temporal_filter_ms` | `(t_temporal_done − t_temporal_start) × 1000` | `TemporalFilter.update()` |
| `command_generation_ms` | `(t_command_generated − t_generate_start) × 1000` | `CommandGenerator.generate()` |
| `total_server_ms` | `(t_end − t_server_received) × 1000` | End of `_process_frame` (including early exits after capture) |

`t_end` is `time.perf_counter()` in `FrameTiming.finish()`, called from the
`finally` block of `_process_frame`.

These identities follow if a stage ran:

```
preprocess_ms          = (t_preprocess_done − t_preprocess_start) × 1000
mediapipe_ms           = (t_mediapipe_done − t_mediapipe_start) × 1000
classification_ms      = (t_classification_done − t_classify_start) × 1000
command_generation_ms  = (t_command_generated − t_generate_start) × 1000
```

Later metrics that are **not** computed in this phase (derive from JSONL):

| Metric | How to compute later |
|---|---|
| P50 / P95 / P99 of a duration | Percentile of that field over selected JSONL rows |
| Frames processed per second | `count(records) / (last.timestamp − first.timestamp)` using a defined window, or count of records per monotonic span |
| Commands generated per second | `count(command_emitted == true) / window` |
| Dropped frames | `dropped_frames` on the last record, or `FrameStore.dropped_frames` |

`GET /api/debug` reports `avg_total_server_ms` as an **arithmetic mean** of
`total_server_ms` in this process. It does **not** report P50/P95/P99.

---

## JSONL schema

Configurable path: `instrumentation.jsonl_path` (default `logs/instrumentation.jsonl`,
relative to process CWD). Do not use a machine-specific absolute default.

One JSON object per **processed** frame (capture succeeded). Disabled when
`instrumentation.enabled` is false (no file I/O).

```json
{
  "frame_id": 123,
  "timestamp": "2026-08-22T02:00:00.000+00:00",
  "t_capture": 123.456,
  "t_server_received": 123.456,
  "t_preprocess_done": 123.457,
  "t_mediapipe_done": 123.465,
  "t_classification_done": 123.466,
  "t_command_generated": 123.466,
  "t_command_emitted": 123.467,
  "capture_ms": 2.1,
  "preprocess_ms": 1.0,
  "mediapipe_ms": 8.4,
  "landmark_extraction_ms": 0.1,
  "classification_ms": 0.2,
  "noise_filter_ms": 0.05,
  "temporal_filter_ms": 0.03,
  "command_generation_ms": 0.04,
  "total_server_ms": 12.2,
  "gesture": "open_palm",
  "score": 0.91,
  "command_emitted": true,
  "dropped_frames": 0,
  "cpu_percent": 12.5,
  "rss_mb": 256.0
}
```

| Field | Type | Notes |
|---|---|---|
| `frame_id` | int or string | Correlation key |
| `timestamp` | string | Wall-clock ISO-8601 UTC — **not** for durations |
| `t_*` | float or null | `perf_counter()` seconds |
| `*_ms` | float or null | Stage duration; null if the stage did not run |
| `gesture` | string or null | Last known gesture name on this frame |
| `score` | float or null | Rule score (`Prediction.confidence`). **Not** a probability |
| `command_emitted` | bool | Whether `gesture_command` was emitted |
| `dropped_frames` | int | Cumulative FrameStore overwrites at this record |
| `cpu_percent` | float or null | Last 1 Hz **process** CPU sample (see below) |
| `rss_mb` | float or null | Last 1 Hz process RSS sample |

`cpu_percent` / `rss_mb` are **copied** from a 1 Hz sampler onto the frame
record. They are not measured per frame.

---

## Command payload (additive)

`gesture_command` still contains the original fields. Added:

| Field | Meaning |
|---|---|
| `frame_id` | Frame that produced the command |
| `server_emitted_at` | UTC wall-clock ISO-8601 at emit time (log correlation) |

`confidence` is unchanged in name and semantics: it is the rule score, not a
calibrated probability. Command type / value mapping is unchanged.

---

## Dropped-frame definition

A **dropped frame** is an unread `FrameStore` slot overwritten by a later
`put()`.

```
if store already holds an unread frame:
    dropped_frames += 1
store[latest] = new_frame    # last-write-wins, unchanged
```

This is **not** a MediaPipe miss, a noise-filter reject, a temporal-filter
hold, or a cooldown suppress. Those remain the existing `PipelineRunner.stats`
funnel counters.

OpenCV capture does not use `FrameStore.put()`, so its dropped-frame count
stays 0 unless something else writes the store.

---

## CPU / RSS measurement

Implemented in `backend.utils.instrumentation.ResourceSampler`.

| Field | What it is | What it is not |
|---|---|---|
| `cpu_percent` | This **process**: `Δ time.process_time() / Δ time.perf_counter() × 100` | System-wide CPU, per-core breakdown, GPU |
| `rss_mb` | This process resident set (Linux `/proc/self/statm` pages; fallback `resource.ru_maxrss` in KiB / 1024) | System RAM, peak-only if `/proc` is missing |

Sampling interval: `instrumentation.resource_sample_interval_s` (default 1.0).
The first interval after start has `cpu_percent = null` because a rate needs
two samples.

GPU measurement is not implemented.

---

## Debug endpoint

`GET /api/debug` now also returns:

- `processed_frames` (`stats.frames_captured`)
- `commands_sent`
- `dropped_frames`
- `latest_timing` (last processed frame’s stage durations)
- `avg_total_server_ms` (arithmetic mean of `total_server_ms` this process)
- `instrumentation` (same fields plus `jsonl_enabled`, `jsonl_path`, `cpu_scope`)

P50/P95/P99 are **not** computed here. Use the JSONL later.

---

## Configuration

```json
"instrumentation": {
  "enabled": true,
  "jsonl_path": "logs/instrumentation.jsonl",
  "resource_sample_interval_s": 1.0
}
```

| Key | Default | Notes |
|---|---|---|
| `enabled` | `true` | `false` skips JSONL writes; recognition path is the same |
| `jsonl_path` | `logs/instrumentation.jsonl` | Relative to CWD |
| `resource_sample_interval_s` | `1.0` | Minimum 0.1 s |

Helper: `ConfigurationManager.is_instrumentation_enabled()`.

---

## Limitations

1. WebSocket `ping` / `pong` RTT is **not** end-to-end gesture latency and is
   not part of these timers.
2. Rule `score` is **not** a calibrated probability.
3. JSONL rows are raw observations, not benchmark results. No performance
   claim is made in this phase.
4. `total_server_ms` is server-side only (receive/capture → end of
   `_process_frame`). It excludes client capture, network upload of JPEGs,
   and client HUD apply time.
5. Preview JPEG encode (`_maybe_emit_preview`) is **inside** `total_server_ms`
   when it runs (~10 Hz) and is **not** a named stage.
6. Cooldown `check()` is not a named stage duration.
7. Dynamic / ONNX time is not recorded (baseline path is static-only).
8. MediaPipe `Hands(static_image_mode=False)` is stateful; per-frame
   `mediapipe_ms` is not an independent i.i.d. sample.
9. `cpu_percent` is process CPU, can exceed 100 on multi-core, and is a 1 Hz
   snapshot copied onto frame records.
10. `FrameStore` dropped-frame counting applies to the last-write-wins browser
    store only. Behaviour was not changed.
11. Client `webcam_bridge.js` may still send `{image}` only if that file was
    not updated; the server then generates `frame_id`.
12. `Session.avg_latency_ms` is still unused. Do not report it.

---

## Exact next step

Use this instrumentation (JSONL + debug counters) to run a **defined
measurement experiment** (window, hardware block, git SHA). Do **not** start
Docker, cloud deployment, Kubernetes, load testing, ONNX, new gestures, or
accuracy/F1 evaluation until that experiment is specified.
