import assert from "node:assert/strict";
import test from "node:test";
import { getBitMindScore } from "./bitmind-score.ts";

const result = (is_ai, confidence, status = "completed", provider_used = "bitmind") => ({
  provider_used, visual: { status, is_ai, confidence },
});

test("verdict determines direction, confidence determines distance from neutral", () => {
  assert.equal(getBitMindScore(result(true, 0.9)), 5);
  assert.equal(getBitMindScore(result(false, 0.9)), 95);
  for (const isAI of [true, false]) {
    assert.equal(getBitMindScore(result(isAI, 0)), 50);
    assert.equal(getBitMindScore(result(isAI, 1)), isAI ? 0 : 100);
    const scores = [0, 0.1, 0.5, 0.9, 1].map(c => getBitMindScore(result(isAI, c)));
    assert.ok(scores.every((score, i) => i === 0 || (isAI ? score <= scores[i - 1] : score >= scores[i - 1])));
  }
});

test("missing or invalid evidence never produces a number", () => {
  for (const confidence of [undefined, null, NaN, Infinity, -0.1, 1.1, "0.9"]) {
    assert.equal(getBitMindScore(result(true, confidence)), null);
  }
  assert.equal(getBitMindScore(result(undefined, 0.9)), null);
  assert.equal(getBitMindScore(result(true, 0.9, "unavailable")), null);
  assert.equal(getBitMindScore(result(true, 0.9, "completed", "offline")), null);
});
