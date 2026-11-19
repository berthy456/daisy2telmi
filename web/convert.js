// DAISY zip in, Telmi story zip out, entirely in the browser.

import { COVER_SIZE, IMAGE_SIZE, cardPng, coverPng } from "./cover.js";
import { extractBook, normalizePath } from "./daisy.js";
import { concatSegments } from "./mp3.js";
import { placeholderPng } from "./png.js";
import { writeZip } from "./zip.js";
import { buildMetadata, buildNotes, buildNodes, storyDirName, storyUuid } from "./telmi.js";

const json = (value) => new TextEncoder().encode(`${JSON.stringify(value, null, 2)}\n`);

// A part cut below chapter level has no title that says which part it is, so its
// card plays the sound it opens with instead of a spoken number.
const CARD_SNIPPET_SECONDS = 3;

/** The first seconds of a part, cut at MP3 frame boundaries. */
function firstSeconds(segments, bytesOf, seconds) {
  let budget = seconds;
  const kept = [];
  for (const segment of segments) {
    if (budget <= 0) break;
    const begin = segment.begin ?? 0;
    const end = Math.min(segment.end ?? begin + budget, begin + budget);
    kept.push(bytesOf({ ...segment, begin, end }));
    budget -= end - begin;
  }
  return concatSegments(kept);
}

/**
 * entries: [{name, data}] of a DAISY pack.
 * silentMp3: bytes used for title.mp3 when the pack has no spoken front matter.
 * onProgress(label, done, total): optional progress callback.
 * options.cut: "chapter", "paragraph" or "sentence" — where to cut the book.
 * options.cover: an ImageBitmap to crop into every scene image.
 * options.crop: "top", "center" or "bottom" — the band of the cover to keep.
 * options.style: "colour", or "bw" for a plain Lunii's four grey levels.
 * options.cardLabel(number, total, worded): the words drawn on a card.
 * options.cardAudio(number): bytes for the card to say, or null to leave it silent.
 */
export async function buildStoryFiles(entries, silentMp3, onProgress = () => {}, options = {}) {
  const cut = options.cut ?? "chapter";
  const book = extractBook(entries, cut);
  if (!book.chapters.length) throw new Error("no chapter with audio found in this pack");

  const uuid = await storyUuid(book);
  const dirName = storyDirName(book.title, uuid);
  const byName = new Map(entries.map((entry) => [normalizePath(entry.name), entry]));
  const bytesOf = (segment) => ({ ...segment, data: byName.get(segment.src).data });
  const files = [];
  const total = book.chapters.length + 3;
  const partCount = book.chapters.length;
  const cover = options.cover ?? null;
  const crop = options.crop ?? "center";
  const style = options.style ?? "colour";
  const cardLabel = options.cardLabel ?? ((number, count) => `Chapter ${number}/${count}`);
  const say = options.t ?? ((key) => key);
  const spoken = options.cardAudio ?? (async () => null);
  const cards = [];
  let done = 0;

  const step = (label) => {
    done += 1;
    onProgress(label, done, total);
  };

  for (const [k, chapter] of book.chapters.entries()) {
    const audio = concatSegments(chapter.segments.map(bytesOf));
    files.push({ name: `${dirName}/audios/s${k}.mp3`, data: audio });
    files.push({
      name: `${dirName}/images/m${k}.png`,
      data: await cardPng(
        cardLabel(k + 1, partCount, cut === "chapter"),
        chapter.text,
        cover,
        crop,
        ...IMAGE_SIZE,
        style,
      ),
    });

    let card = null;
    if (cut === "chapter") {
      const voice = await spoken(k + 1);
      if (voice !== null) {
        files.push({ name: `${dirName}/audios/c${k}.mp3`, data: voice });
        card = `c${k}.mp3`;
      }
    } else {
      const snippet = firstSeconds(chapter.segments, bytesOf, CARD_SNIPPET_SECONDS);
      // A part shorter than the snippet needs no second copy: its card plays the part.
      card = snippet.length === 0 ? null : snippet.length === audio.length ? `s${k}.mp3` : `c${k}.mp3`;
      if (card === `c${k}.mp3`) files.push({ name: `${dirName}/audios/c${k}.mp3`, data: snippet });
    }
    cards[k] = card;

    step(`${k + 1}/${partCount}: ${chapter.title}`);
  }

  files.push({
    name: `${dirName}/title.mp3`,
    data: book.frontMatter.length ? concatSegments(book.frontMatter.map(bytesOf)) : silentMp3,
  });
  step(say("prog_title_audio"));

  files.push({
    name: `${dirName}/title.png`,
    data: cover ? await coverPng(cover, ...IMAGE_SIZE, crop, style) : await placeholderPng(...IMAGE_SIZE, style),
  });
  files.push({
    name: `${dirName}/cover.png`,
    data: cover ? await coverPng(cover, ...COVER_SIZE, crop, style) : await placeholderPng(...COVER_SIZE, style),
  });
  step(say("prog_title_images"));

  const metadata = buildMetadata(book, uuid);
  const nodes = buildNodes(book.chapters.map((_, k) => `s${k}`), cards);
  files.push({ name: `${dirName}/metadata.json`, data: json(metadata) });
  files.push({ name: `${dirName}/nodes.json`, data: json(nodes) });
  files.push({ name: `${dirName}/notes.json`, data: json(buildNotes(book)) });
  step(say("prog_metadata"));

  return { dirName, uuid, book, files, metadata, nodes };
}

export async function buildStoryZip(entries, silentMp3, onProgress, options) {
  const story = await buildStoryFiles(entries, silentMp3, onProgress, options);
  return { ...story, zip: await writeZip(story.files) };
}
