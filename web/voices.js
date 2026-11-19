// Chapter-card announcements, recorded ahead of time under web/voices/.
//
// A browser tab can play speech but cannot capture it into a file, so the page
// ships the phrases instead of synthesising them. `tools/make_web_voices.py`
// regenerates them with espeak-ng.

import { concatMp3 } from "./mp3.js";

export const MAX_CARD = 50;

const clips = new Map();

/** Path of the clip saying the chapter number, or null when it was never recorded. */
export function clipPath(language, number) {
  if (!Number.isInteger(number) || number < 1 || number > MAX_CARD) return null;
  return `./voices/${language}/${String(number).padStart(2, "0")}.mp3`;
}

async function load(path) {
  if (clips.has(path)) return clips.get(path);
  const response = await fetch(path);
  if (!response.ok) return null;
  const data = new Uint8Array(await response.arrayBuffer());
  clips.set(path, data);
  return data;
}

/**
 * Bytes of the card announcement for chapter `number`, or null when the number
 * is beyond the recorded range. `prompt` adds the "next chapter?" question.
 */
export async function cardAudio(language, number, prompt = false, get = load) {
  const phrase = await get(clipPath(language, number));
  if (phrase === null) return null;
  if (!prompt) return phrase;
  const ask = await get(`./voices/${language}/next.mp3`);
  return ask === null ? phrase : concatMp3([phrase, ask]);
}
