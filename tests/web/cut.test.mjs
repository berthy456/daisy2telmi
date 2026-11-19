// Which cut levels a pack can be cut at, from the part counts its own outline gives.

import assert from "node:assert/strict";
import { test } from "node:test";

import { CUT_LEVELS, cutChoices } from "../../web/daisy.js";

test("a pack with one outline level only offers chapters", () => {
  assert.deepEqual(cutChoices([6, 6, 6]), ["chapter"]);
});

test("a pack that goes deeper at every level offers all three", () => {
  assert.deepEqual(cutChoices([6, 24, 120]), [...CUT_LEVELS]);
});

test("a level is offered on its own when it adds parts the one below it did not", () => {
  assert.deepEqual(cutChoices([6, 6, 120]), ["chapter", "sentence"]);
});

test("an empty pack still offers chapters", () => {
  assert.deepEqual(cutChoices([0, 0, 0]), []);
  assert.deepEqual(cutChoices([1, 0, 0]), ["chapter"]);
});
