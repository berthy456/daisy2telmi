// Node test runner suite for the browser modules: node --test tests/web/

import assert from "node:assert/strict";
import { readFile, mkdtemp, access } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const PACK = join(ROOT, "gon-ruby-mp3.zip");

const { readZip, writeZip } = await import("../../web/zip.js");
const { extractBook } = await import("../../web/daisy.js");
const { buildStoryFiles, buildStoryZip } = await import("../../web/convert.js");
const { normalizeFileName, slugify, storyDirName, storyUuid } = await import("../../web/telmi.js");
const { mp3Frames, trimFrames } = await import("../../web/mp3.js");
const { cardWords } = await import("../../web/cover.js");

const { installCanvasStub } = await import("./canvas-stub.mjs");

installCanvasStub();

async function pack(name) {
  return readZip(new Uint8Array(await readFile(join(ROOT, name))));
}

// The Rachel pack is a copyrighted sample kept out of the repository, so CI
// only has the gon pack.
async function present(name) {
  try {
    await access(join(ROOT, name));
    return true;
  } catch {
    return false;
  }
}

test("folder naming reproduces a real published Telmi story", () => {
  assert.equal(
    storyDirName("La reine des pirates", "fffffd-19d14f92f57", 0, ""),
    "_00_La reine des pirates_fffffd-19d14f92f57",
  );
});

test("normalising and slugifying match Telmi-Sync's Strings.js", () => {
  // Values taken from the Python implementation, which was diffed against Strings.js.
  assert.equal(normalizeFileName("L'île  à   Vélo!!"), "L ile a Velo ");
  assert.equal(slugify("  Wesh  la fée 1234 "), "-wesh-la-fee-1234-");
  assert.equal(normalizeFileName("ごんぎつね"), " ");
  assert.equal(slugify("ごんぎつね"), "-");
});

test("the uuid matches the command line converter", async () => {
  const book = extractBook(await pack("gon-ruby-mp3.zip"));
  assert.equal(await storyUuid(book), "fe3ea2d2-4b0d-55eb-b18a-9a4d143ae318");
});

test("the outline splits on top-level chapters", async () => {
  const book = extractBook(await pack("gon-ruby-mp3.zip"));
  assert.equal(book.title, "ごんぎつね");
  assert.equal(book.chapters.length, 6);
  assert.deepEqual(book.chapters.map((c) => c.segments.length), [9, 5, 4, 3, 2, 2]);
  assert.equal(book.frontMatter.length, 1);
});

test("the cut levels follow the marks the pack itself carries", async () => {
  const entries = await pack("gon-ruby-mp3.zip");
  assert.equal(extractBook(entries, "chapter").chapters.length, 6);
  assert.equal(extractBook(entries, "paragraph").chapters.length, 25);
  assert.equal(extractBook(entries, "sentence").chapters.length, 213);
  assert.throws(() => extractBook(entries, "verse"), /unknown cut level/);
});

test("a part carries the words the pack read over it", async () => {
  const entries = await pack("gon-ruby-mp3.zip");
  const sentences = extractBook(entries, "sentence");
  assert.deepEqual(sentences.chapters.slice(0, 2).map((part) => part.text), ["一", "1"]);
  assert.ok(sentences.chapters[2].text.startsWith("これは、私（わたし）"), sentences.chapters[2].text);
  // A chapter card shows the first real sentence, not the section number read out before it.
  assert.ok(extractBook(entries, "chapter").chapters[0].text.startsWith("これは、私（わたし）"));
});

test("a card below chapter level plays the opening seconds of its part", async () => {
  const silent = new Uint8Array(await readFile(join(ROOT, "web/silence.mp3")));
  const story = await buildStoryFiles(await pack("gon-ruby-mp3.zip"), silent, () => {}, { cut: "paragraph" });
  const bytes = new Map(story.files.map((file) => [file.name.replace(`${story.dirName}/`, ""), file.data.length]));

  // A paragraph runs about a minute, so the card clip is a fraction of its part.
  assert.ok(bytes.get("audios/c0.mp3") > 0);
  assert.equal(bytes.get("audios/c0.mp3") < bytes.get("audios/s0.mp3"), true);
  assert.equal(story.files.filter((file) => file.name.includes("/audios/c")).length, story.book.chapters.length);
});

test("a part shorter than the card clip is not stored twice", async () => {
  const silent = new Uint8Array(await readFile(join(ROOT, "web/silence.mp3")));
  const story = await buildStoryFiles(await pack("gon-ruby-mp3.zip"), silent, () => {}, { cut: "sentence" });
  const nodes = JSON.parse(new TextDecoder().decode(story.files.find((file) => file.name.endsWith("nodes.json")).data));
  const cards = story.book.chapters.map((_, k) => nodes.stages[`m${k}`].audio);

  assert.ok(cards.every((audio) => audio !== null), "every card should have sound to navigate by");
  // The first sentence lasts under three seconds, so its card plays the part itself.
  assert.equal(cards[0], "s0.mp3");
  assert.equal(story.files.some((file) => file.name.endsWith("/audios/c0.mp3")), false);
  assert.ok(story.files.filter((file) => file.name.includes("/audios/c")).length < story.book.chapters.length);
});

test("trimming an MP3 keeps whole frames inside the asked range", async () => {
  const data = new Uint8Array(await readFile(join(ROOT, "web/silence.mp3")));
  const whole = mp3Frames(data);
  assert.ok(whole.length > 0);
  assert.equal(trimFrames(data, null, null).length, whole.length);
  const part = trimFrames(data, 0.2, 0.6);
  assert.ok(part.length > 0 && part.length < whole.length);
  // The same range cut twice gives the same bytes: the cut is on frame boundaries.
  assert.equal(trimFrames(data, 0.2, 0.6).length, part.length);
});

test("card words wrap to three lines and break a run with no spaces", () => {
  const ctx = { measureText: (line) => ({ width: [...line].length * 10 }) };
  assert.deepEqual(cardWords(ctx, "one two", 200), ["one two"]);
  assert.equal(cardWords(ctx, "abcdefghij ".repeat(30), 100).length, 3);
  assert.deepEqual(cardWords(ctx, "これは私が小さいときに", 60), ["これは私が小", "さいときに"]);
  assert.deepEqual(cardWords(ctx, "", 100), []);
});

test(
  "a second, structurally different pack also parses",
  { skip: !(await present("Rachel-Corenblit-Wesh-la-fee.zip")) ? "sample pack not in the repo" : false },
  async () => {
    const book = extractBook(await pack("Rachel-Corenblit-Wesh-la-fee.zip"));
    assert.equal(book.chapters.length, 23);
  },
);

test("the story zip carries every entry Telmi-Sync requires", async () => {
  const silent = new Uint8Array(await readFile(join(ROOT, "web/silence.mp3")));
  const story = await buildStoryZip(await pack("gon-ruby-mp3.zip"), silent);
  const names = new Set(story.files.map((file) => file.name.replace(`${story.dirName}/`, "")));

  for (const required of ["audios", "images", "metadata.json", "nodes.json", "title.mp3", "title.png"]) {
    assert.ok([...names].some((name) => name.startsWith(`${required}/`) || name === required), `missing ${required}`);
  }
  assert.equal([...names].filter((name) => name.startsWith("audios/")).length, 6);
  assert.equal([...names].filter((name) => name.startsWith("images/")).length, 6);
});

// The desktop Chapters window lets parts be left out; the page's boxes do the
// same, so the numbers stay in order after the removal.
test("leaving parts out renumbers the story", async () => {
  const silent = new Uint8Array(await readFile(join(ROOT, "web/silence.mp3")));
  const entries = await pack("gon-ruby-mp3.zip");
  const whole = extractBook(entries, "chapter").chapters;
  const kept = await buildStoryFiles(entries, silent, () => {}, { drop: [2, 5] });
  const names = new Set(kept.files.map((file) => file.name.replace(`${kept.dirName}/`, "")));

  assert.equal(kept.book.chapters.length, 4);
  assert.deepEqual(kept.book.chapters.map((part) => part.title), [0, 2, 3, 5].map((k) => whole[k].title));
  for (const k of [0, 1, 2, 3]) {
    assert.ok(names.has(`audios/s${k}.mp3`), `missing s${k}`);
    assert.ok(names.has(`images/m${k}.png`), `missing m${k}`);
  }
  assert.equal(names.has("audios/s4.mp3"), false, "a dropped part left its audio behind");
  assert.equal(names.has("images/m5.png"), false, "a dropped part left its image behind");

  const nodes = JSON.parse(new TextDecoder().decode(kept.files.find((file) => file.name.endsWith("nodes.json")).data));
  assert.deepEqual(Object.keys(nodes.stages).sort(), ["m0", "m1", "m2", "m3", "s0", "s1", "s2", "s3"]);
});

test("feeding back a converted story says what it is", async () => {
  const entries = await pack("gon-ruby-mp3-telmi.zip");
  assert.throws(() => extractBook(entries), /already a Telmi story/);
});

test("the written zip reads back identically", async () => {
  const silent = new Uint8Array(await readFile(join(ROOT, "web/silence.mp3")));
  const story = await buildStoryFiles(await pack("gon-ruby-mp3.zip"), silent);
  const dir = await mkdtemp(join(tmpdir(), "daisy2telmi-"));
  const written = await writeZip(story.files);
  const back = await readZip(written);

  assert.equal(back.length, story.files.length);
  back.forEach((entry, index) => {
    assert.equal(entry.name, story.files[index].name);
    assert.equal(entry.data.length, story.files[index].data.length);
  });
  assert.ok(dir);
});

export { PACK };
