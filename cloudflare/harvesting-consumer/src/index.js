function validJob(job) {
  return Number.isSafeInteger(job?.harvest_id)
    && job.harvest_id > 0
    && Number.isSafeInteger(job?.checkpoint)
    && job.checkpoint >= 0;
}

async function processMessage(message, env) {
  const job = message.body;
  try {
    if (!validJob(job) || !env.BACKEND_BASE_URL || !env.HARVEST_WORKER_TOKEN) {
      throw new Error("Invalid harvest job or missing consumer configuration.");
    }

    const backendUrl = new URL(env.BACKEND_BASE_URL);
    if (backendUrl.protocol !== "https:") {
      throw new Error("BACKEND_BASE_URL must use HTTPS.");
    }
    const response = await fetch(
      new URL("/api/harvesting/worker/step/", backendUrl),
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.HARVEST_WORKER_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(job),
      },
    );
    if (!response.ok) {
      throw new Error(`Harvest backend returned HTTP ${response.status}.`);
    }

    const result = await response.json();
    if (
      typeof result.has_more !== "boolean"
      || result.harvest_id !== job.harvest_id
      || !Number.isSafeInteger(result.checkpoint)
      || result.checkpoint < 0
    ) {
      throw new Error("Harvest backend returned an invalid checkpoint.");
    }
    if (result.has_more) {
      await env.HARVEST_QUEUE.send({
        harvest_id: result.harvest_id,
        checkpoint: result.checkpoint,
      });
    }
    message.ack();
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    const stack = error instanceof Error ? error.stack : undefined;
    console.error("Harvest step failed", job?.harvest_id, detail, stack);
    message.retry();
  }
}

export default {
  async queue(batch, env) {
    await Promise.all(batch.messages.map((message) => processMessage(message, env)));
  },
};
