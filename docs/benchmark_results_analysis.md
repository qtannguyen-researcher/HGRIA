No benchmark results are available to analyze. I searched this repo, nearby project folders, recent chats, and the terminal. There is a [benchmark protocol](639366b7-3fe6-49cf-b6e8-f4f7ca1790cd) from earlier, but no run tables, logs, CSVs, videos, or session stats. The analysis below is therefore about the absence of data, not about system performance.

## 1. Observations

- This checkout has no evaluation harness, no labeled corpus, and no result artifact (`*.csv`, logs, session dumps, recorded video).
- `temp_requirements.md` and the READMEs state **targets** (accuracy ≥ 85%, end-to-end latency ≤ 150 ms). Those are requirements, not measurements.
- Existing unit tests check rule/filter/command behavior on synthetic landmarks. They are not a benchmark run and were not treated as one.
- `Session.avg_latency_ms` is never written. `debug.log_pipeline_latency` is unused. Dynamic-path confidence is hardcoded to `1.0` when that path is used.
- No independent/dependent variable table, repetition count, seed, or environment block exists for a completed experiment.

## 2. Quantitative evidence

None from an experiment.

What exists instead:

| Quantity | Status |
|---|---|
| Per-class label match, thresholding rate, rule confusion | Not measured |
| Funnel rates (`frames_no_hand`, noise/temporal/cooldown drops, `commands_sent`) | Counters exist in code; no run recorded them |
| Command-queue latency, WebSocket RTT | Instrumented in code; no session sample |
| Capture-to-HUD latency, P50/P95 | Not implemented as a recorded metric |
| Test-suite pass/fail | Not a performance distribution |

No means, medians, confidence intervals, or effect sizes can be reported.

## 3. Possible explanations

These explain the **missing results**, not model quality:

- The benchmark was designed but not executed.
- Results were produced outside this workspace and not attached (file, paste, or image).
- Protocol B/C could not run: videos are gitignored; ONNX weights referenced in config are not in-tree.
- Protocol A was never scripted beyond the existing fixture tests.

## 4. Alternative explanations

- Results exist under a different name or machine and were not shared here.
- “These results” was meant to refer to the SRS/README numbers. Those numbers are not empirical outcomes of this checkout.
- Pytest output was intended as the dataset. That would still only support claims about fixture–rule agreement, not webcam recognition or latency.

## 5. Threats to validity

Without a completed experiment, internal/external validity of **performance claims** cannot be assessed. The threats that would apply *if* someone treated non-experimental sources as results:

- **Construct:** SRS targets and unit tests do not measure live recognition or end-to-end latency.
- **Internal:** `config.json` and `ConfigurationManager.DEFAULTS` disagree on several knobs; an unspecified config source would make later runs incomparable.
- **External:** No pinned hardware/software block, no versioned video, no user/lighting corpus.
- **Statistical:** No repetitions, no seeds (the static path is deterministic; MediaPipe tracking is not seeded), no sample size.

## 6. Claims that are NOT supported by the data

Because there is no experimental dataset, **none** of the following is supported:

- The system meets or misses ≥ 85% gesture accuracy.
- End-to-end command latency is ≤ 150 ms (or any other latency number).
- One config, path (static vs dual), threshold, window size, or cooldown is better than another.
- MediaPipe, the geometric rules, temporal filtering, or cooldown **cause** any observed error or delay.
- Dynamic gestures are more accurate than static ones (weights are absent; dynamic confidence is a constant).
- Results will generalize across users, lighting, cameras, Colab vs local, or machines.

I am not filling in numbers from the SRS or inventing a run. If you attach a results table, log, or CSV (or point to the file), I can redo all six sections from that data only.