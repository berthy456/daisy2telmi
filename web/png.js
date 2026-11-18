// Placeholder images, written by hand so the page needs no canvas and no image library.
// Port of the Python placeholder_png / chapter_png in telmi_builder.py.

import { crc32 } from "./zip.js";

const BACKGROUND = [26, 30, 42];
const BAND = [78, 92, 122];
const FOREGROUND = [214, 222, 238];

const DIGITS = {
  0: ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
  1: ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
  2: ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
  3: ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
  4: ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
  5: ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
  6: ["01110", "10001", "10000", "11110", "10001", "10001", "01110"],
  7: ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
  8: ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
  9: ["01110", "10001", "10001", "01111", "00001", "10001", "01110"],
};

function fill(rgb, count) {
  const out = new Uint8Array(rgb.length * count);
  for (let i = 0; i < count; i++) out.set(rgb, i * rgb.length);
  return out;
}

function concat(parts) {
  const total = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let at = 0;
  for (const part of parts) {
    total.set(part, at);
    at += part.length;
  }
  return total;
}

async function chunk(tag, payload) {
  const body = concat([new TextEncoder().encode(tag), payload]);
  const header = new Uint8Array(4);
  new DataView(header.buffer).setUint32(0, payload.length, false);
  const crc = new Uint8Array(4);
  new DataView(crc.buffer).setUint32(0, crc32(body), false);
  return concat([header, body, crc]);
}

async function png(width, height, rows) {
  const rawRows = rows.map((row) => concat([new Uint8Array([0]), row]));
  const raw = concat(rawRows);

  const ihdr = new Uint8Array(13);
  const view = new DataView(ihdr.buffer);
  view.setUint32(0, width, false);
  view.setUint32(4, height, false);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 2; // truecolour RGB

  const deflated = new Uint8Array(
    await new Response(new Blob([raw]).stream().pipeThrough(new CompressionStream("deflate"))).arrayBuffer(),
  );

  return concat([
    new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    await chunk("IHDR", ihdr),
    await chunk("IDAT", deflated),
    await chunk("IEND", new Uint8Array(0)),
  ]);
}

export async function placeholderPng(width = 640, height = 480) {
  const bandTop = Math.floor(height / 2) - 48;
  const bandBottom = Math.floor(height / 2) + 48;
  const rows = [];
  for (let y = 0; y < height; y++) rows.push(fill(y >= bandTop && y < bandBottom ? BAND : BACKGROUND, width));
  return png(width, height, rows);
}

export async function chapterPng(number, width = 640, height = 480) {
  const glyph = Array.from({ length: 7 }, (_, y) =>
    String(number)
      .split("")
      .map((d) => DIGITS[d][y])
      .join(" "),
  );
  const scale = Math.min(24, Math.floor((width * 2) / 3 / glyph[0].length), Math.floor((height * 2) / 3 / glyph.length));
  const blockWidth = glyph[0].length * scale;
  const blockHeight = glyph.length * scale;
  const left = Math.floor((width - blockWidth) / 2);
  const top = Math.floor((height - blockHeight) / 2);

  const rows = Array.from({ length: top }, () => fill(BACKGROUND, width));
  for (const glyphRow of glyph) {
    const strip = concat(
      [...glyphRow].map((ink) => fill(ink === "1" ? FOREGROUND : BACKGROUND, scale)),
    );
    const row = concat([fill(BACKGROUND, left), strip, fill(BACKGROUND, width - left - blockWidth)]);
    for (let k = 0; k < scale; k++) rows.push(row);
  }
  for (let k = rows.length; k < height; k++) rows.push(fill(BACKGROUND, width));
  return png(width, height, rows);
}
