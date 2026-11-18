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
