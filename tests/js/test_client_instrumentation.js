#!/usr/bin/env node
/**
 * Phase 3B client instrumentation unit tests (Node).
 * Exit 0 on success; print JSON summary.
 */
"use strict";

const path = require("path");
const assert = require("assert");
const api = require(path.join(__dirname, "../../frontend/js/client_instrumentation.js"));

let clock = 1000;
const log = api.createClientMeasurementLog({
    runId: "phase3b-test",
    now: () => clock,
});

const id1 = log.nextFrameId();
const id2 = log.nextFrameId();
const id3 = log.nextFrameId();
assert.strictEqual(id1, 1);
assert.strictEqual(id2, 2);
assert.strictEqual(id3, 3);
assert.ok(id1 < id2 && id2 < id3, "frame_id must increase monotonically");

clock = 1100.5;
const cap1 = log.recordCapture(id1, log.now());
assert.strictEqual(cap1.t_client_capture, 1100.5);
assert.strictEqual(cap1.frame_id, 1);
assert.strictEqual(cap1.run_id, "phase3b-test");
assert.strictEqual(cap1.event, "client_capture");
assert.ok(!("e2e_latency_ms" in cap1), "capture must not fabricate E2E");

clock = 1101.0;
const tSend = log.now();
clock = 1133.25;
const tAck = log.now();
const http1 = log.recordHttp(id1, tSend, tAck);
assert.strictEqual(http1.t_client_http_send, 1101.0);
assert.strictEqual(http1.t_client_http_ack, 1133.25);
assert.ok(Math.abs(http1.http_request_ms - 32.25) < 1e-9);

const payload = api.buildFramePayload("abc123", id1);
assert.strictEqual(payload.frame_id, 1);
assert.strictEqual(payload.image, "abc123");

clock = 1165.0;
const cmd1 = log.recordCommandReceive({
    frame_id: id1,
    t_client_cmd_recv: log.now(),
});
assert.strictEqual(cmd1.frame_id, 1);
assert.strictEqual(cmd1.t_client_cmd_recv, 1165.0);
assert.ok(Math.abs(cmd1.e2e_latency_ms - 64.5) < 1e-9);
assert.strictEqual(cmd1.command_received, true);

clock = 1200;
log.recordCapture(id2, log.now());
const unmatched = log.recordCommandReceive({
    frame_id: 999,
    t_client_cmd_recv: 1300,
});
assert.ok(!("e2e_latency_ms" in unmatched), "unmatched frame must not fabricate E2E");

log.recordCapture(id3, 2000);
const negative = log.recordCommandReceive({
    frame_id: id3,
    t_client_cmd_recv: 1500,
});
assert.ok(!("e2e_latency_ms" in negative), "negative E2E must be rejected");
assert.strictEqual(api.computeE2E(1500, 2000), null);
assert.strictEqual(api.computeE2E(2000, 1500), 500);

const records = log.getRecords();
assert.ok(records.every((r) => r.run_id === "phase3b-test"));
assert.ok(records.every((r) => !("latencyMs" in r) && !("ping_rtt" in r)));

console.log(JSON.stringify({
    ok: true,
    ids: [id1, id2, id3],
    e2e_latency_ms: cmd1.e2e_latency_ms,
    http_request_ms: http1.http_request_ms,
    record_count: records.length,
}));
