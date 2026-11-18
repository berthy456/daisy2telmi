// DAISY zip in, Telmi story zip out, entirely in the browser.

import { extractBook, normalizePath } from "./daisy.js";
import { concatMp3 } from "./mp3.js";
import { chapterPng, placeholderPng } from "./png.js";
import { writeZip } from "./zip.js";
import { buildMetadata, buildNotes, buildNodes, storyDirName, storyUuid } from "./telmi.js";

const json = (value) => new TextEncoder().encode(`${JSON.stringify(value, null, 2)}\n`);

/**
 * entries: [{name, data}] of a DAISY pack.
 * silentMp3: bytes used for title.mp3 when the pack has no spoken front matter.
 * onProgress(label, done, total): optional progress callback.
 */
export async function buildStoryFiles(entries, silentMp3, onProgress = () => {}) {
  const book = extractBook(entries);
  if (!book.chapters.length) throw new Error("no chapter with audio found in this pack");

  const uuid = await storyUuid(book);
  const dirName = storyDirName(book.title, uuid);
  const byName = new Map(entries.map((entry) => [normalizePath(entry.name), entry]));
  const files = [];
  const total = book.chapters.length + 3;
  let done = 0;

  const step = (label) => {
    done += 1;
    onProgress(label, done, total);
  };

  for (const [k, chapter] of book.chapters.entries()) {
    const audio = concatMp3(chapter.segments.map((segment) => byName.get(segment.src).data));
    files.push({ name: `${dirName}/audios/s${k}.mp3`, data: audio });
    files.push({ name: `${dirName}/images/m${k}.png`, data: await chapterPng(k + 1) });
    step(`chapter ${k + 1}/${book.chapters.length}: ${chapter.title}`);
  }

  files.push({
    name: `${dirName}/title.mp3`,
    data: book.frontMatter.length
      ? concatMp3(book.frontMatter.map((segment) => byName.get(segment.src).data))
      : silentMp3,
  });
  step("title audio");

  files.push({ name: `${dirName}/title.png`, data: await placeholderPng(640, 480) });
  files.push({ name: `${dirName}/cover.png`, data: await placeholderPng(512, 512) });
  step("title images");

  files.push({ name: `${dirName}/metadata.json`, data: json(buildMetadata(book, uuid)) });
  files.push({ name: `${dirName}/nodes.json`, data: json(buildNodes(book.chapters.map((_, k) => `s${k}`))) });
  files.push({ name: `${dirName}/notes.json`, data: json(buildNotes(book)) });
  step("story metadata");

  return { dirName, uuid, book, files };
}

export async function buildStoryZip(entries, silentMp3, onProgress) {
  const story = await buildStoryFiles(entries, silentMp3, onProgress);
  return { ...story, zip: await writeZip(story.files) };
}
