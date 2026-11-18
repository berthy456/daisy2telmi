// DAISY zip in, Telmi story zip out, entirely in the browser.

import { COVER_SIZE, IMAGE_SIZE, coverPng } from "./cover.js";
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
 * options.cover: an ImageBitmap to crop into every scene image.
 * options.cardLabel(number, total): the words drawn on a chapter card.
 */
export async function buildStoryFiles(entries, silentMp3, onProgress = () => {}, options = {}) {
  const book = extractBook(entries);
  if (!book.chapters.length) throw new Error("no chapter with audio found in this pack");

  const uuid = await storyUuid(book);
  const dirName = storyDirName(book.title, uuid);
  const byName = new Map(entries.map((entry) => [normalizePath(entry.name), entry]));
  const files = [];
  const total = book.chapters.length + 3;
  const chapterCount = book.chapters.length;
  const cover = options.cover ?? null;
  const cardLabel = options.cardLabel ?? ((number, count) => `Chapter ${number}/${count}`);
  const say = options.t ?? ((key) => key);
  let done = 0;

  const step = (label) => {
    done += 1;
    onProgress(label, done, total);
  };

  for (const [k, chapter] of book.chapters.entries()) {
    const audio = concatMp3(chapter.segments.map((segment) => byName.get(segment.src).data));
    files.push({ name: `${dirName}/audios/s${k}.mp3`, data: audio });
    const card = cover
      ? await coverPng(cover, ...IMAGE_SIZE, cardLabel(k + 1, chapterCount))
      : await chapterPng(k + 1);
    files.push({ name: `${dirName}/images/m${k}.png`, data: card });
    step(`${k + 1}/${chapterCount}: ${chapter.title}`);
  }

  files.push({
    name: `${dirName}/title.mp3`,
    data: book.frontMatter.length
      ? concatMp3(book.frontMatter.map((segment) => byName.get(segment.src).data))
      : silentMp3,
  });
  step(say("prog_title_audio"));

  files.push({
    name: `${dirName}/title.png`,
    data: cover ? await coverPng(cover, ...IMAGE_SIZE) : await placeholderPng(...IMAGE_SIZE),
  });
  files.push({
    name: `${dirName}/cover.png`,
    data: cover ? await coverPng(cover, ...COVER_SIZE) : await placeholderPng(...COVER_SIZE),
  });
  step(say("prog_title_images"));

  files.push({ name: `${dirName}/metadata.json`, data: json(buildMetadata(book, uuid)) });
  files.push({ name: `${dirName}/nodes.json`, data: json(buildNodes(book.chapters.map((_, k) => `s${k}`))) });
  files.push({ name: `${dirName}/notes.json`, data: json(buildNotes(book)) });
  step(say("prog_metadata"));

  return { dirName, uuid, book, files };
}

export async function buildStoryZip(entries, silentMp3, onProgress, options) {
  const story = await buildStoryFiles(entries, silentMp3, onProgress, options);
  return { ...story, zip: await writeZip(story.files) };
}
