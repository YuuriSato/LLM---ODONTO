import assert from "node:assert/strict";
import test from "node:test";
import worker from "./index.mjs";

const env = {
  UPSTREAM_ORIGIN: "https://dashboard.trycloudflare.com",
  MODEL_ORIGIN: "https://model.trycloudflare.com",
};
const base = "https://observability-okta7.okta7.workers.dev";

async function withFetch(mock, action) {
  const original = globalThis.fetch;
  globalThis.fetch = mock;
  try { return await action(); } finally { globalThis.fetch = original; }
}

test("model routes use the model origin and keep the bearer header", async () => {
  const seen = [];
  await withFetch(async (request) => {
    seen.push(request);
    return Response.json({ object: "list" });
  }, async () => {
    const response = await worker.fetch(new Request(base + "/v1/models", {
      headers: { Authorization: "Bearer test-secret" },
    }), env);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
  });
  assert.equal(seen.length, 1);
  assert.equal(seen[0].url, "https://model.trycloudflare.com/v1/models");
  assert.equal(seen[0].headers.get("Authorization"), "Bearer test-secret");
});

test("dashboard routes keep their existing origin and redirect behavior", async () => {
  await withFetch(async (request) => {
    assert.equal(request.url, "https://dashboard.trycloudflare.com/login");
    return new Response(null, { status: 302, headers: { Location: "/dashboard" } });
  }, async () => {
    const response = await worker.fetch(new Request(base + "/login"), env);
    assert.equal(response.status, 302);
    assert.equal(response.headers.get("Location"), base + "/dashboard");
  });
});

test("model POST works for server clients without an Origin header", async () => {
  await withFetch(async (request) => {
    assert.equal(request.url, "https://model.trycloudflare.com/v1/chat/completions");
    assert.equal(request.headers.get("Authorization"), "Bearer test-secret");
    return Response.json({ choices: [{ message: { content: "ok" } }] });
  }, async () => {
    const response = await worker.fetch(new Request(base + "/v1/chat/completions", {
      method: "POST", headers: { Authorization: "Bearer test-secret" }, body: "{}",
    }), env);
    assert.equal(response.status, 200);
  });
});

test("dashboard write protection remains intact", async () => {
  const response = await worker.fetch(new Request(base + "/api/settings", {
    method: "POST", body: "{}",
  }), env);
  assert.equal(response.status, 403);
});

test("model routes reject unsupported methods and missing origin binding", async () => {
  assert.equal((await worker.fetch(new Request(base + "/v1/models", { method: "POST" }), env)).status, 405);
  assert.equal((await worker.fetch(new Request(base + "/v1/models"), { ...env, MODEL_ORIGIN: "" })).status, 503);
});
