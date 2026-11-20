// The Lunii export in the browser: the Telmi story walked back into a STUdio archive.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));

const { readZip } = await import("../../web/zip.js");
const { buildStoryFiles } = await import("../../web/convert.js");
const { buildStudioFiles, buildStudioZip } = await import("../../web/lunii.js");
const { installCanvasStub } = await import("./canvas-stub.mjs");

installCanvasStub();

const ASSET_NAME = /^[0-9A-F]{8}\.(png|mp3)$/;

async function story(cut = "chapter") {
  const silent = new Uint8Array(await readFile(join(ROOT, "web/silence.mp3")));
  const entries = await readZip(new Uint8Array(await readFile(join(ROOT, "gon-ruby-mp3.zip"))));
  return buildStoryFiles(entries, silent, () => {}, { cut });
}

test("the archive unfolds the Telmi story into stages and actions", async () => {
  const book = await story();
  const { storyJson, assets } = await buildStudioFiles(book);

  assert.equal(storyJson.format, "v1");
  assert.equal(storyJson.title, "ごんぎつね");
  assert.equal(storyJson.stageNodes[0].type, "cover");
  assert.equal(storyJson.stageNodes[0].squareOne, true);
  assert.equal(storyJson.stageNodes.length, 1 + 2 * book.book.chapters.length);
  // Six chapters: one menu action per chapter plus one play action each.
  assert.equal(storyJson.actionNodes.length, 1 + book.book.chapters.length);

  const media = new Set(
    book.files
      .map((file) => file.name.replace(`${book.dirName}/`, ""))
      .filter((name) => name.startsWith("audios/") || name.startsWith("images/") || name === "title.mp3" || name === "title.png"),
  );
  assert.equal(assets.length, media.size);
  assert.ok(assets.every((asset) => ASSET_NAME.test(asset.name)), "every asset is named with eight hex characters");
});

test("the ids and asset names match the desktop converter", async () => {
  const book = await story();
  const { storyJson, assets } = await buildStudioFiles(book);
  const byName = new Map(storyJson.stageNodes.map((node) => [node.name, node]));

  // Computed from the Python module over the same story uuid.
  assert.equal(storyJson.stageNodes[0].uuid, "fe3ea2d2-4b0d-55eb-b18a-9a4d143ae318");
  assert.equal(byName.get("m0").uuid, "e8bf7734-b82a-5308-9773-c0f2f394790c");
  assert.equal(byName.get("s5").uuid, "9937b974-e586-5613-af97-a8c5f6607c31");

  const named = new Map(assets.map((asset) => [asset.name.slice(0, 8), asset.name]));
  assert.ok(named.has("059CBA91"), "audios/s0.mp3 keeps the name the desktop converter gives it");
  assert.ok(named.has("B6F7B7A8"), "images/m0.png likewise");
  assert.ok(named.has("D8BAA9AC"), "title.mp3 likewise");
});

test("a card stage keeps home as the way out of the story", async () => {
  const book = await story();
  const { storyJson } = await buildStudioFiles(book);
  const cards = storyJson.stageNodes.filter((node) => node.name.startsWith("m"));
  assert.ok(cards.every((node) => node.controlSettings.home && node.homeTransition === null));
  assert.ok(cards.every((node) => node.controlSettings.ok && node.okTransition !== null));
});

test("converting the same story twice writes the same archive", async () => {
  const book = await story();
  const first = await buildStudioZip(book);
  const second = await buildStudioZip(book);
  assert.equal(first.length, second.length);

  const entries = await readZip(first);
  assert.equal(entries[0].name, "story.json");
  assert.equal(entries[1].name, "thumbnail.png");
  assert.ok(entries.every((entry) => entry.name === "story.json" || entry.name === "thumbnail.png" || entry.name.startsWith("assets/")));
  const storyJson = JSON.parse(new TextDecoder().decode(entries[0].data));
  assert.equal(storyJson.nightModeAvailable, false);
});

test("a story marked night-mode available joins the Lunii's bedtime playlist", async () => {
  const book = await story();
  const entries = await readZip(await buildStudioZip(book, true));
  const storyJson = JSON.parse(new TextDecoder().decode(entries[0].data));
  assert.equal(storyJson.nightModeAvailable, true);
});

test("a story cut to sentences still folds into stages", async () => {
  const book = await story("sentence");
  const { storyJson, assets } = await buildStudioFiles(book);
  const parts = book.book.chapters.length;

  assert.equal(storyJson.stageNodes.length, 1 + 2 * parts);
  assert.equal(storyJson.actionNodes.length, 1 + parts);
  // A short part's card points at the part itself, so the archive holds it once.
  const audios = assets.filter((asset) => asset.name.endsWith(".mp3")).length;
  assert.ok(audios < 1 + 2 * parts);
});
