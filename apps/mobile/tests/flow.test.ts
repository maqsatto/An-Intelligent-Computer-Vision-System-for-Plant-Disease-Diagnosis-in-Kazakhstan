import { test } from "node:test";
import assert from "node:assert/strict";
import { runSubmission, pollAssessment, outcomeCopy, delay } from "../src/flow";
test("retry reuses all client IDs and skips uploaded photo", async () => {
  const calls: any[] = [];
  const draft: any = {
    observationId: "local-o",
    photoId: "local-p",
    key: "local-key",
    cropId: "tomato",
    capturedAt: "2026-10-21T12:00:00Z",
    notes: "",
    uri: "file://leaf.jpg",
  };
  const api: any = {
    createObservation: async (b: any) => {
      calls.push(b);
      return { id: "o" };
    },
    uploadPhoto: async () => ({ id: "p" }),
    createAssessment: async (b: any, key: string) => {
      calls.push(key);
      throw Error("network");
    },
  };
  await assert.rejects(
    runSubmission(api, draft, true, new AbortController().signal, () => {}),
  );
  assert.equal(draft.serverObservationId, "o");
  assert.equal(draft.serverPhotoId, "p");
  api.createAssessment = async (b: any, k: string) => {
    assert.equal(k, "local-key");
    return { id: "a", status: "queued" };
  };
  await runSubmission(api, draft, true, new AbortController().signal, () => {});
  assert.equal(calls.length, 2);
});
test("unsupported known crop saves without scheduling assessment", async () => {
  let scheduled = false;
  const api: any = {
    createObservation: async () => ({ id: "o" }),
    uploadPhoto: async () => ({ id: "p" }),
    createAssessment: async () => {
      scheduled = true;
    },
  };
  const r = await runSubmission(
    api,
    {
      observationId: "x",
      photoId: "y",
      key: "z",
      cropId: "maize",
      capturedAt: "now",
      notes: "",
      uri: "file://x",
    } as any,
    false,
    new AbortController().signal,
    () => {},
  );
  assert.equal(r.assessment, null);
  assert.equal(scheduled, false);
});
test("polling stops at terminal and respects abort", async () => {
  let n = 0;
  const api: any = {
    assessment: async () => {
      n++;
      return { id: "a", status: "completed" };
    },
  };
  await pollAssessment(
    api,
    "a",
    new AbortController().signal,
    () => {},
    async () => {},
  );
  assert.equal(n, 1);
  const c = new AbortController();
  c.abort();
  await assert.rejects(
    pollAssessment(
      api,
      "a",
      c.signal,
      () => {},
      async () => {},
    ),
  );
  assert.equal(n, 1);
});
test("every outcome and unknown reasons have safe copy", () => {
  for (const o of [
    "predicted",
    "inconclusive",
    "unsupported_input",
    "retake_photo",
  ])
    assert.ok(outcomeCopy(o).title);
  assert.equal(outcomeCopy("future_outcome").title, "Результат наблюдения");
});
test("long processing yields a recoverable pause rather than endless polling", async () => {
  let n = 0;
  const api: any = {
    assessment: async () => {
      n++;
      return { id: "a", status: "running" };
    },
  };
  await assert.rejects(
    pollAssessment(
      api,
      "a",
      new AbortController().signal,
      () => {},
      async () => {},
    ),
    /продолжается/,
  );
  assert.equal(n, 30);
});
test("React Native legacy AbortSignal works without throwIfAborted or reason", async () => {
  const legacy = { aborted: true } as AbortSignal;
  let called = false;
  const api: any = {
    assessment: async () => {
      called = true;
    },
  };
  await assert.rejects(
    pollAssessment(
      api,
      "a",
      legacy,
      () => {},
      async () => {},
    ),
    { name: "AbortError" },
  );
  assert.equal(called, false);
});
test("background cancellation interrupts pending native-compatible delay", async () => {
  let listener: () => void = () => {};
  const signal = {
    aborted: false,
    addEventListener: (_type: string, callback: () => void) => {
      listener = callback;
    },
    removeEventListener: () => {},
  } as unknown as AbortSignal;
  const pending = delay(10000, signal);
  (signal as any).aborted = true;
  listener();
  await assert.rejects(pending, { name: "AbortError" });
});
test("real research abstention explains model validation instead of claiming no inference happened", () => {
  const copy = outcomeCopy("inconclusive", ["research_model_unvalidated"]);
  assert.equal(copy.title, "Исследовательский результат");
  assert.match(copy.body, /рассчитала/);
  assert.match(copy.body, /не подтверждают болезнь/);
});
test("research unsupported scope does not claim model inference ran", () => {
  const copy = outcomeCopy("inconclusive", [
    "research_model_unvalidated",
    "unsupported_crop_or_organ",
  ]);
  assert.doesNotMatch(copy.body, /рассчитала/);
  assert.match(copy.body, /поддерживаемую/);
});
