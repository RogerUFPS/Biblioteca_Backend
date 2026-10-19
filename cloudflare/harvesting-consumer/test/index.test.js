import { test } from "node:test";
import assert from "node:assert/strict";

import worker from "../src/index.js";

test("consumer calls backend and queues exactly the returned checkpoint", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });

  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return Response.json({
      harvest_id: 11,
      checkpoint: 5,
      state: "running",
      has_more: true,
    });
  };
  const queued = [];
  let acked = false;
  let retried = false;

  await worker.queue(
    {
      messages: [{
        body: { harvest_id: 11, checkpoint: 4 },
        ack: () => { acked = true; },
        retry: () => { retried = true; },
      }],
    },
    {
      BACKEND_BASE_URL: "https://backend.test/",
      HARVEST_WORKER_TOKEN: "secret",
      HARVEST_QUEUE: { send: async (job) => queued.push(job) },
    },
  );

  assert.equal(request.url.href, "https://backend.test/api/harvesting/worker/step/");
  assert.deepEqual(JSON.parse(request.options.body), { harvest_id: 11, checkpoint: 4 });
  assert.deepEqual(queued, [{ harvest_id: 11, checkpoint: 5 }]);
  assert.equal(acked, true);
  assert.equal(retried, false);
});

test("consumer retries a failed backend request", async (context) => {
  const originalFetch = globalThis.fetch;
  const originalError = console.error;
  context.after(() => {
    globalThis.fetch = originalFetch;
    console.error = originalError;
  });
  globalThis.fetch = async () => new Response("unavailable", { status: 503 });
  console.error = () => {};
  let retried = false;

  await worker.queue(
    {
      messages: [{
        body: { harvest_id: 11, checkpoint: 4 },
        ack: () => assert.fail("must not acknowledge"),
        retry: () => { retried = true; },
      }],
    },
    {
      BACKEND_BASE_URL: "https://backend.test",
      HARVEST_WORKER_TOKEN: "secret",
      HARVEST_QUEUE: { send: async () => assert.fail("must not enqueue") },
    },
  );

  assert.equal(retried, true);
});

test("consumer reports malformed backend URLs as actionable errors", async (context) => {
  const originalFetch = globalThis.fetch;
  const originalError = console.error;
  context.after(() => {
    globalThis.fetch = originalFetch;
    console.error = originalError;
  });
  globalThis.fetch = async () => assert.fail("must not call backend");
  const errors = [];
  console.error = (...args) => errors.push(args);
  let retried = false;

  await worker.queue(
    {
      messages: [{
        body: { harvest_id: 12, checkpoint: 0 },
        ack: () => assert.fail("must not acknowledge"),
        retry: () => { retried = true; },
      }],
    },
    {
      BACKEND_BASE_URL: "repositorio-biblioteca-backend.onrender.com",
      HARVEST_WORKER_TOKEN: "secret",
      HARVEST_QUEUE: { send: async () => assert.fail("must not enqueue") },
    },
  );

  assert.equal(retried, true);
  assert.equal(errors[0][0], "Harvest step failed");
  assert.match(errors[0][2], /Invalid URL/);
});
