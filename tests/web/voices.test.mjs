// The recorded card announcements the page ships, and how it picks them.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const { MAX_CARD, cardAudio, clipPath } = await import("../../web/voices.js");
const { LANGUAGES } = await import("../../web/i18n.js");

test("a chapter number becomes a two digit clip name", () => {
  assert.equal(clipPath("fr", 1), "./voices/fr/01.mp3");
  assert.equal(clipPath("zh", MAX_CARD), `./voices/zh/${String(MAX_CARD).padStart(2, "0")}.mp3`);
});

test("a number outside the recorded range has no clip", () => {
  for (const bad of [0, -1, MAX_CARD + 1, 2.5, NaN, undefined, "3"]) {
    assert.equal(clipPath("en", bad), null);
  }
});

test("a clip the page cannot fetch leaves the card silent", async () => {
  assert.equal(await cardAudio("en", 3, false, async () => null), null);
});

test("the prompt joins the question after the number", async () => {
  const silence = new Uint8Array(await readFile("web/silence.mp3"));
  const asked = [];
  const joined = await cardAudio("fr", 4, true, async (path) => {
    asked.push(path);
    return silence;
  });
  assert.deepEqual(asked, ["./voices/fr/04.mp3", "./voices/fr/next.mp3"]);
  assert.ok(joined.length > 0 && joined.length <= silence.length * 2);
});

test("every language ships its numbers and its prompt", async () => {
  for (const code of LANGUAGES) {
    for (const name of ["01.mp3", "07.mp3", `${String(MAX_CARD).padStart(2, "0")}.mp3`, "next.mp3"]) {
      const bytes = await readFile(`web/voices/${code}/${name}`);
      const tagged = bytes[0] === 0x49 && bytes[1] === 0x44 && bytes[2] === 0x33;
      const frame = (bytes[0] & 0xe0) === 0xe0;
      assert.ok(tagged || frame, `web/voices/${code}/${name} is not an MP3`);
    }
  }
});
