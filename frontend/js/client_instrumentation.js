/**
 * HGRIA Phase 3B — browser client measurement log.
 *
 * Timestamps used for latency MUST come from performance.now() (or an
 * injected clock with the same monotonic semantics). Date.now() / ISO
 * strings are correlation-only and are never subtracted.
 *
 * Ping RTT (GameState.latencyMs / HUD Latency) is a different metric
 * and is not written here.
 */
(function (root, factory) {
    var api = factory();
    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
    if (typeof root !== "undefined") {
        root.HGRIAClientInstrumentation = api;
        if (!root.HGRIA_CLIENT_LOG) {
            root.HGRIA_CLIENT_LOG = api.createClientMeasurementLog();
        }
    }
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    function defaultNow() {
        if (typeof performance !== "undefined" && typeof performance.now === "function") {
            return performance.now();
        }
        throw new Error("performance.now() is required for client latency timestamps");
    }

    function wallIso() {
        return new Date().toISOString();
    }

    function isFiniteNumber(value) {
        return typeof value === "number" && Number.isFinite(value);
    }

    /**
     * E2E latency from the same browser monotonic clock.
     * Returns null when either timestamp is missing or the result is negative.
     * Never fabricates a value.
     */
    function computeE2E(tClientCmdRecv, tClientCapture) {
        if (!isFiniteNumber(tClientCmdRecv) || !isFiniteNumber(tClientCapture)) {
            return null;
        }
        var e2e = tClientCmdRecv - tClientCapture;
        if (e2e < 0) {
            return null;
        }
        return e2e;
    }

    function computeHttpRequestMs(tAck, tSend) {
        if (!isFiniteNumber(tAck) || !isFiniteNumber(tSend)) {
            return null;
        }
        var ms = tAck - tSend;
        if (ms < 0) {
            return null;
        }
        return ms;
    }

    function createClientMeasurementLog(options) {
        var opts = options || {};
        var nowFn = opts.now || defaultNow;
        var runId = opts.runId != null ? String(opts.runId) : "";
        var nextId = 0;
        var captures = Object.create(null);
        var records = [];
        var sink = typeof opts.sink === "function" ? opts.sink : null;
        var persistUrl = opts.persistUrl || "";

        function persist(record) {
            records.push(record);
            if (sink) {
                sink(record);
            }
            if (persistUrl && typeof fetch === "function") {
                fetch(persistUrl.replace(/\/$/, "") + "/api/client-log", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "ngrok-skip-browser-warning": "1",
                    },
                    body: JSON.stringify(record),
                }).catch(function () { /* measurement persist must not throw */ });
            }
        }

        function baseRecord(eventName, frameId) {
            return {
                event: eventName,
                run_id: runId,
                frame_id: frameId,
                wall_iso: wallIso(),
            };
        }

        return {
            setRunId: function (id) {
                runId = id == null ? "" : String(id);
            },
            setPersistUrl: function (url) {
                persistUrl = url == null ? "" : String(url);
            },
            getRunId: function () {
                return runId;
            },
            now: function () {
                return nowFn();
            },
            nextFrameId: function () {
                nextId += 1;
                return nextId;
            },
            lastFrameId: function () {
                return nextId;
            },
            recordCapture: function (frameId, tCapture) {
                var t = isFiniteNumber(tCapture) ? tCapture : nowFn();
                captures[String(frameId)] = t;
                var rec = baseRecord("client_capture", frameId);
                rec.t_client_capture = t;
                persist(rec);
                return rec;
            },
            recordHttp: function (frameId, tSend, tAck) {
                var rec = baseRecord("client_http", frameId);
                rec.t_client_http_send = tSend;
                rec.t_client_http_ack = tAck;
                var httpMs = computeHttpRequestMs(tAck, tSend);
                if (httpMs !== null) {
                    rec.http_request_ms = httpMs;
                }
                persist(rec);
                return rec;
            },
            recordCommandReceive: function (payload) {
                var data = payload || {};
                var frameId = data.frame_id;
                var tRecv = data.t_client_cmd_recv;
                var rec = baseRecord("client_command", frameId);
                rec.t_client_cmd_recv = tRecv;
                rec.command_received = true;
                if (frameId === undefined || frameId === null || frameId === "") {
                    persist(rec);
                    return rec;
                }
                var tCapture = captures[String(frameId)];
                var e2e = computeE2E(tRecv, tCapture);
                if (e2e !== null) {
                    rec.e2e_latency_ms = e2e;
                    rec.t_client_capture = tCapture;
                }
                persist(rec);
                return rec;
            },
            getCaptureTime: function (frameId) {
                var t = captures[String(frameId)];
                return t === undefined ? null : t;
            },
            getRecords: function () {
                return records.slice();
            },
            toJSONL: function () {
                return records.map(function (r) { return JSON.stringify(r); }).join("\n");
            },
            reset: function () {
                nextId = 0;
                captures = Object.create(null);
                records = [];
            },
        };
    }

    function buildFramePayload(imageBase64, frameId) {
        return { image: imageBase64, frame_id: frameId };
    }

    return {
        createClientMeasurementLog: createClientMeasurementLog,
        computeE2E: computeE2E,
        computeHttpRequestMs: computeHttpRequestMs,
        buildFramePayload: buildFramePayload,
        defaultNow: defaultNow,
    };
}));
