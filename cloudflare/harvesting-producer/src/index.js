function authorized(request, token) {
  const supplied = request.headers.get("Authorization") || "";
  const expected = `Bearer ${token}`;
  if (!token || supplied.length !== expected.length) {
    return false;
  }

  let difference = 0;
  for (let index = 0; index < expected.length; index += 1) {
    difference |= supplied.charCodeAt(index) ^ expected.charCodeAt(index);
  }
  return difference === 0;
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return Response.json({ detail: "Method not allowed." }, { status: 405 });
    }
    if (!authorized(request, env.HARVEST_WORKER_TOKEN)) {
      return Response.json({ detail: "Invalid worker credentials." }, { status: 401 });
    }

    let job;
    try {
      job = await request.json();
    } catch {
      return Response.json({ detail: "Invalid JSON body." }, { status: 400 });
    }

    if (
      !Number.isSafeInteger(job.harvest_id)
      || job.harvest_id < 1
      || !Number.isSafeInteger(job.checkpoint)
      || job.checkpoint < 0
    ) {
      return Response.json({ detail: "Invalid harvest job." }, { status: 400 });
    }

    try {
      await env.HARVEST_QUEUE.send({
        harvest_id: job.harvest_id,
        checkpoint: job.checkpoint,
      });
    } catch (error) {
      console.error("Unable to enqueue harvest", job.harvest_id, error);
      return Response.json({ detail: "Unable to enqueue harvest." }, { status: 503 });
    }

    return Response.json(
      { harvest_id: job.harvest_id, checkpoint: job.checkpoint, queued: true },
      { status: 202 },
    );
  },
};
