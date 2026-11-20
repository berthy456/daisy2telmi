// Which part of the cover a crop keeps: the three bands, a moved frame, a zoomed one.

import assert from "node:assert/strict";
import { test } from "node:test";

import { DRAWS, FILLS, TEXTS, installCanvasStub } from "./canvas-stub.mjs";

installCanvasStub();

const { CARD_MARGIN, CROP_MODES, IMAGE_SIZE, coverPng } = await import("../../web/cover.js");

// A tall cover: a centre-crop cuts its title off, which is the whole point of the choice.
const cover = { width: 1000, height: 1500, close: () => {} };

// drawImage(cover, x, y, width, height): the band is the y argument.
function drawn(view) {
  DRAWS.length = 0;
  return coverPng(cover, ...IMAGE_SIZE, view).then(() => DRAWS[0].args);
}

test("the three bands land where the cover says they do", async () => {
  // 640x480 from 1000x1500 scales by 0.64: 640 wide, 960 tall, so 480 px overflow.
  assert.equal((await drawn({ crop: "top" }))[2], 0);
  assert.equal((await drawn({ crop: "center" }))[2], -240);
  assert.equal((await drawn({ crop: "bottom" }))[2], -480);
  for (const mode of CROP_MODES) assert.equal((await drawn({ crop: mode }))[1], 0);
});

test("the default crop is the middle band", async () => {
  DRAWS.length = 0;
  await coverPng(cover, ...IMAGE_SIZE);
  assert.equal(DRAWS[0].args[2], -240);
});

test("a moved frame slides along the overflow it has", async () => {
  // The tall cover overflows a 640x480 frame by 480 px and not at all sideways.
  assert.equal((await drawn({ focus: [0, 0.25] }))[2], -120);
  assert.equal((await drawn({ focus: [1, 1] }))[2], -480, "the bottom edge of the cover");
  for (const x of [0, 1]) assert.equal((await drawn({ focus: [x, 0.5] }))[1], 0, "no sideways room to move in");
});

test("zooming enlarges the cover and opens room to move", async () => {
  const args = await drawn({ zoom: 2 });
  assert.equal(args[3], 1280, "twice the 640 px a plain crop needs");
  assert.equal(args[4], 1920);
  assert.equal(args[2], -720, "still centred, so twice the overflow");
  assert.equal(args[1], -320, "and room to move sideways, which a plain crop has none of");
  assert.equal((await drawn({ zoom: 2, focus: [0, 0] }))[1], 0, "the sideways move lands on the cover's left edge");
});

test("a zoom below one is no zoom at all", async () => {
  assert.deepEqual(await drawn({ zoom: 0.2 }), await drawn({ zoom: 1 }));
});

test("a card's thumbnail follows the same band", async () => {
  const { cardPng } = await import("../../web/cover.js");
  DRAWS.length = 0;
  await cardPng("Chapter 1/6", "Once upon a time", cover, { crop: "bottom" });
  // The thumbnail is drawn onto the card canvas, so it is the wide argument that says which draw it is.
  const thumb = DRAWS.find((draw) => draw.args[3] === 160).args;
  // 160x120 from 1000x1500 scales by 0.16: 160 wide, 240 tall.
  assert.equal(thumb[2], CARD_MARGIN + (120 - 240));
});

test("a smaller card shrinks its margins with its screen", async () => {
  const { cardPng } = await import("../../web/cover.js");
  TEXTS.length = 0;
  await cardPng("1/6", "Once upon a time", null, { crop: "center" }, 320, 240);
  const [number, words] = TEXTS;
  assert.equal(number[3], 320, "the number is drawn on the Lunii card");
  assert.equal(number[1], 320 - 12, "its margin shrinks with the card");
  assert.equal(words[1], 12);
});

test("a four-grey card fills its screen with the cover and centres its lettering", async () => {
  const { cardPng } = await import("../../web/cover.js");
  DRAWS.length = 0;
  TEXTS.length = 0;
  FILLS.length = 0;
  await cardPng("1/6", "Once upon a time", cover, { crop: "center" }, 320, 240, "bw");

  const full = DRAWS.find((draw) => draw.args[3] === 320);
  assert.ok(full, "the cover is drawn across the whole card, not in a corner");
  assert.ok(full.args[4] >= 240, "and it reaches the bottom of it");

  const [number, ...words] = TEXTS;
  assert.equal(number[1], 160, "the number is centred along the top");
  assert.ok(words.length > 0, "the words are still on the card");
  for (const line of words) assert.equal(line[1], 160, "and they are centred too");

  const strips = FILLS.filter(([, , width, height, card]) => card === 320 && width === 320 && height < 240);
  assert.equal(strips.length, 2, "one strip behind the number, one behind the words");
  assert.equal(strips[0][1], 0, "the number's strip starts at the top of the screen");
  assert.equal(strips[1][1] + strips[1][3], 240, "the words' strip reaches the bottom");
});

test("a colour card keeps its corner number, its thumbnail and no strips", async () => {
  const { cardPng } = await import("../../web/cover.js");
  TEXTS.length = 0;
  FILLS.length = 0;
  await cardPng("1/6", "Once upon a time", cover, { crop: "center" }, 320, 240, "colour");
  assert.equal(TEXTS[0][1], 320 - 12, "the number stays in the corner");
  assert.equal(
    FILLS.filter(([, , width, height, card]) => card === 320 && width === 320 && height < 240).length,
    0,
    "a colour card draws no strip behind its lettering",
  );
});
