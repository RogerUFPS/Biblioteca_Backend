import { test } from "node:test";
import assert from "node:assert/strict";

import worker from "../src/index.js";

test("producer authenticates and enqueues only the checkpoint", async () => {
  const sent = [];
  const response = await worker.fetch(
    new Request("https://producer.test/", {
      method: "POST",
      headers: { Authorization: "Bearer secret" },
      body: JSON.stringify({ harvest_id: 8, checkpoint: 3, ignored: "data" }),
    }),
    { HARVEST_WORKER_TOKEN: "secret", HARVEST_QUEUE: { send: async (job) => sent.push(job) } },
  );

  assert.equal(response.status, 202);
  assert.deepEqual(sent, [{ harvest_id: 8, checkpoint: 3 }]);
});

test("producer rejects invalid credentials and invalid checkpoints", async () => {
  const queue = { send: async () => assert.fail("must not enqueue") };
  const unauthorized = await worker.fetch(
    new Request("https://producer.test/", { method: "POST" }),
    { HARVEST_WORKER_TOKEN: "secret", HARVEST_QUEUE: queue },
  );
  assert.equal(unauthorized.status, 401);

  const invalid = await worker.fetch(
    new Request("https://producer.test/", {
      method: "POST",
      headers: { Authorization: "Bearer secret" },
      body: JSON.stringify({ harvest_id: 8, checkpoint: -1 }),
    }),
    { HARVEST_WORKER_TOKEN: "secret", HARVEST_QUEUE: queue },
  );
  assert.equal(invalid.status, 400);
});
