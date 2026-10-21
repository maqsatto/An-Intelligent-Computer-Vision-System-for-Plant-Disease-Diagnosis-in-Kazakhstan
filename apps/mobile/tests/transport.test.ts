import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiClient, ApiError } from "../../../packages/api-client/src/index";
test("personal image requires same origin and current bearer", () => {
  let token = "first";
  const api = new ApiClient("https://api.example", () => token);
  assert.deepEqual(api.privateImage("/v1/photos/p/content"), {
    uri: "https://api.example/v1/photos/p/content",
    headers: { Authorization: "Bearer first" },
  });
  token = "second";
  assert.equal(api.privateImage("/x").headers.Authorization, "Bearer second");
  assert.throws(() => api.privateImage("https://other.example/image"));
  assert.throws(() => api.privateImage("//other.example/image"));
});
test("401 is surfaced and never blindly retried", async () => {
  const original = global.fetch;
  let calls = 0;
  global.fetch = async () => {
    calls++;
    return new Response(
      JSON.stringify({
        code: "session_expired",
        message: "expired",
        request_id: "r",
      }),
      { status: 401 },
    );
  };
  try {
    const api = new ApiClient("https://api.example", () => null);
    await assert.rejects(
      api.me(),
      (e) => e instanceof ApiError && e.status === 401 && e.requestId === "r",
    );
    assert.equal(calls, 1);
  } finally {
    global.fetch = original;
  }
});
test("assessment transport preserves idempotency key and bearer", async () => {
  const original = global.fetch;
  global.fetch = async (_url, init) => {
    const h = new Headers(init?.headers);
    assert.equal(h.get("Authorization"), "Bearer secret");
    assert.equal(h.get("Idempotency-Key"), "stable-key");
    assert.equal(
      init?.body,
      JSON.stringify({ observation_id: "o", primary_photo_id: "p" }),
    );
    return new Response(JSON.stringify({ id: "a" }), { status: 202 });
  };
  try {
    await new ApiClient("https://api.example", () => "secret").createAssessment(
      { observation_id: "o", primary_photo_id: "p" },
      "stable-key",
    );
  } finally {
    global.fetch = original;
  }
});
test("abort is forwarded to fetch", async () => {
  const original = global.fetch;
  const c = new AbortController();
  global.fetch = async (_url, init) => {
    assert.equal(init?.signal, c.signal);
    throw new DOMException("Aborted", "AbortError");
  };
  try {
    await assert.rejects(
      new ApiClient("https://api.example", () => null).me(c.signal),
      { name: "AbortError" },
    );
  } finally {
    global.fetch = original;
  }
});
