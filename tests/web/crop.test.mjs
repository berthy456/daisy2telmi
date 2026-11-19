// Which band of the cover each crop keeps, checked against the canvas calls.

import assert from "node:assert/strict";
import { test } from "node:test";

import { DRAWS, TEXTS, installCanvasStub } from "./canvas-stub.mjs";

installCanvasStub();

const { CARD_MARGIN, CROP_MODES, IMAGE_SIZE, coverPng, cropPreviews } = await import("../../web/cover.js");

// A tall cover: a centre-crop cuts its title off, which is the whole point of the choice.
const cover = { width: 1000, height: 1500, close: () => {} };

// drawImage(cover, x, y, width, height): the band is the y argument.
function drawn(crop) {
  DRAWS.length = 0;
  return coverPng(cover, ...IMAGE_SIZE, crop).then(() => DRAWS[0].args);
}

test("the three bands land where the cover says they do", async () => {
  // 640x480 from 1000x1500 scales by 0.64: 640 wide, 960 tall, so 480 px overflow.
  assert.equal((await drawn("top"))[2], 0);
  assert.equal((await drawn("center"))[2], -240);
  assert.equal((await drawn("bottom"))[2], -480);
  for (const mode of CROP_MODES) assert.equal((await drawn(mode))[1], 0);
});

test("the default crop is the middle band", async () => {
  DRAWS.length = 0;
  await coverPng(cover, ...IMAGE_SIZE);
  assert.equal(DRAWS[0].args[2], -240);
});

test("each preview is drawn at the card ratio", async () => {
  DRAWS.length = 0;
  const previews = await cropPreviews(cover);
  assert.deepEqual(Object.keys(previews), CROP_MODES);
  assert.deepEqual(DRAWS.map((draw) => [draw.width, draw.height]), [
    [160, 120],
    [160, 120],
    [160, 120],
  ]);
  assert.deepEqual(DRAWS.map((draw) => draw.args[2]), [0, -60, -120]);
  for (const bytes of Object.values(previews)) assert.ok(bytes.length > 0);
});

test("a card's thumbnail follows the same band", async () => {
  const { cardPng } = await import("../../web/cover.js");
  DRAWS.length = 0;
  await cardPng("Chapter 1/6", "Once upon a time", cover, "bottom");
  // The thumbnail is drawn onto the card canvas, so it is the wide argument that says which draw it is.
  const thumb = DRAWS.find((draw) => draw.args[3] === 160).args;
  // 160x120 from 1000x1500 scales by 0.16: 160 wide, 240 tall.
  assert.equal(thumb[2], CARD_MARGIN + (120 - 240));
});

test("a smaller card shrinks its margins with its screen", async () => {
  const { cardPng } = await import("../../web/cover.js");
  TEXTS.length = 0;
  await cardPng("1/6", "Once upon a time", null, "center", 320, 240);
  const [number, words] = TEXTS;
  assert.equal(number[3], 320, "the number is drawn on the Lunii card");
  assert.equal(number[1], 320 - 12, "its margin shrinks with the card");
  assert.equal(words[1], 12);
});
