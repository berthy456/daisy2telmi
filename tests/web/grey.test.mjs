// The Lunii's four grey levels: which shade lands where, and which pictures get flattened.

import assert from "node:assert/strict";
import { test } from "node:test";

import { FLATTENS, installCanvasStub } from "./canvas-stub.mjs";

const { cardPng, coverPng, greyLevel } = await import("../../web/cover.js");

test("every brightness lands on one of the four levels", () => {
  const levels = new Set();
  for (let value = 0; value <= 255; value++) levels.add(greyLevel(value));
  assert.deepEqual([...levels].sort((a, b) => a - b), [0, 96, 192, 255]);
  assert.equal(greyLevel(0), 0);
  assert.equal(greyLevel(255), 255);
  // The card's white ground has to stay white: contrast 1.6 pushes 255 up, and
  // the top level is the ceiling.
  assert.equal(greyLevel(200), 255);
  // The cuts are set on the contrasted value, so the card's own shades move:
  // 72 is still black, 73 is the first grey.
  assert.equal(greyLevel(72), 0);
  assert.equal(greyLevel(73), 96);
});

test("a Lunii card is flattened, a colour card is left alone", async () => {
  installCanvasStub();

  FLATTENS.length = 0;
  await cardPng("Chapitre 1/6", "il etait une fois", null, "center", 640, 480, "bw");
  assert.deepEqual(FLATTENS.map(([width, height]) => [width, height]), [[640, 480]]);
  assert.deepEqual(FLATTENS[0][2].sort((a, b) => a - b), [0, 96, 192, 255]);

  FLATTENS.length = 0;
  await cardPng("Chapter 1/6", "once upon a time");
  assert.deepEqual(FLATTENS, [], "a Telmi card keeps its colour");
});

test("the Lunii cover is flattened too", async () => {
  installCanvasStub();
  const cover = { width: 1000, height: 1500, close: () => {} };

  FLATTENS.length = 0;
  await coverPng(cover, 512, 512, "top", "bw");
  assert.deepEqual(FLATTENS.map(([width, height]) => [width, height]), [[512, 512]]);

  FLATTENS.length = 0;
  await coverPng(cover, 512, 512, "top");
  assert.deepEqual(FLATTENS, []);
});
