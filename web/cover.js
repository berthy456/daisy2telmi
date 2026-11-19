// Cover images: read one from a file or a link, then draw it at Telmi's sizes.
//
// The canvas does the work the desktop build hands to ffmpeg: centre-crop to the
// target ratio and write the chapter number over it in white with a black
// border, which is what stays legible on an unknown photograph.

export const IMAGE_SIZE = [640, 480];
export const COVER_SIZE = [512, 512];
export const CARD_THUMB = [160, 120];
export const CARD_MARGIN = 24;
export const CARD_LINES = 3;
export const CARD_WORDS = 20;

const BACKGROUND = "#1a1e2a";

/** Where the user goes to find a cover; Google offers no keyless image API. */
export function searchUrl(query) {
  return `https://www.google.com/search?tbm=isch&q=${encodeURIComponent(query)}`;
}

/** Only http(s) links: a pasted file:, data: or javascript: is not a cover. */
export function isReadableUrl(value, base) {
  if (!value.trim()) return false;
  try {
    const url = new URL(value, base);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export async function loadCoverFile(file) {
  try {
    return await createImageBitmap(file);
  } catch {
    return null;
  }
}

/**
 * A link only works when the other site allows this page to read it, which most
 * do not. The caller reports that as a reason to download the file instead.
 */
export async function loadCoverUrl(value, base) {
  if (!isReadableUrl(value, base)) return null;
  try {
    const response = await fetch(new URL(value, base), { mode: "cors" });
    if (!response.ok) return null;
    return await createImageBitmap(await response.blob());
  } catch {
    return null;
  }
}

function surface(width, height) {
  if (typeof OffscreenCanvas === "function") return new OffscreenCanvas(width, height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

async function toPng(canvas) {
  const blob = canvas.convertToBlob
    ? await canvas.convertToBlob({ type: "image/png" })
    : await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  return new Uint8Array(await blob.arrayBuffer());
}

/** A small copy for the page, so the user sees the cover they picked. */
export function previewDataUrl(cover, width = 160) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = Math.max(1, Math.round((width * cover.height) / cover.width));
  canvas.getContext("2d").drawImage(cover, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/png");
}

export const CROP_MODES = ["top", "center", "bottom"];

/** The cover, cropped into the box at (left, top). */
function drawCover(ctx, cover, left, top, width, height, crop = "center") {
  const scale = Math.max(width / cover.width, height / cover.height);
  const drawnWidth = cover.width * scale;
  const drawnHeight = cover.height * scale;
  const offset = crop === "top" ? 0 : crop === "bottom" ? height - drawnHeight : (height - drawnHeight) / 2;
  ctx.drawImage(cover, left + (width - drawnWidth) / 2, top + offset, drawnWidth, drawnHeight);
}

/** Each crop band, small, as PNG bytes: what the page shows under the cover picker. */
export async function cropPreviews(cover, width = 160) {
  const height = Math.round((width * IMAGE_SIZE[1]) / IMAGE_SIZE[0]);
  const previews = {};
  for (const mode of CROP_MODES) {
    const canvas = surface(width, height);
    drawCover(canvas.getContext("2d"), cover, 0, 0, width, height, mode);
    previews[mode] = await toPng(canvas);
  }
  return previews;
}

/**
 * The opening words of a part, as the three lines a card can show.
 * A run with no spaces (a CJK sentence) is broken where it stops fitting.
 */
export function cardWords(ctx, text, width) {
  const pieces = [];
  for (const word of (text ?? "").trim().split(/\s+/).slice(0, CARD_WORDS)) {
    if (!word) continue;
    if (ctx.measureText(word).width <= width) {
      pieces.push(word);
      continue;
    }
    let run = "";
    for (const character of word) {
      if (run && ctx.measureText(run + character).width > width) {
        pieces.push(run);
        run = character;
      } else {
        run += character;
      }
    }
    if (run) pieces.push(run);
  }

  const lines = [];
  let line = "";
  for (const piece of pieces) {
    const joined = line ? `${line} ${piece}` : piece;
    if (line && ctx.measureText(joined).width > width) {
      lines.push(line);
      line = piece;
    } else {
      line = joined;
    }
    if (lines.length === CARD_LINES) break;
  }
  if (line && lines.length < CARD_LINES) lines.push(line);
  return lines;
}

/**
 * One card: the part's number, its opening words, and a thumbnail of the cover when there is one.
 *
 * A book cut to the sentence level has hundreds of cards, so a card keeps a small
 * thumbnail rather than the whole cover: that is what keeps the zip importable.
 */
export async function cardPng(label, text, cover = null, crop = "center", width = IMAGE_SIZE[0], height = IMAGE_SIZE[1]) {
  const canvas = surface(width, height);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = BACKGROUND;
  ctx.fillRect(0, 0, width, height);
  ctx.lineJoin = "round";
  ctx.miterLimit = 2;
  ctx.textBaseline = "top";
  if (cover) drawCover(ctx, cover, CARD_MARGIN, CARD_MARGIN, ...CARD_THUMB, crop);

  ctx.textAlign = "right";
  ctx.font = `bold ${Math.round(height / 11)}px system-ui, sans-serif`;
  ctx.lineWidth = 6;
  ctx.strokeStyle = "#000";
  ctx.fillStyle = "#fff";
  ctx.strokeText(label, width - CARD_MARGIN, CARD_MARGIN);
  ctx.fillText(label, width - CARD_MARGIN, CARD_MARGIN);

  const size = Math.round(height / 17);
  ctx.textAlign = "left";
  ctx.font = `${size}px system-ui, sans-serif`;
  ctx.lineWidth = 4;
  const pitch = Math.round(size * 1.3);
  for (const [index, line] of cardWords(ctx, text, width - 2 * CARD_MARGIN).entries()) {
    const top = CARD_MARGIN + CARD_THUMB[1] + CARD_MARGIN + index * pitch;
    ctx.strokeText(line, CARD_MARGIN, top);
    ctx.fillText(line, CARD_MARGIN, top);
  }
  return toPng(canvas);
}

/** The cover, cropped to width x height. */
export async function coverPng(cover, width, height, crop = "center") {
  const canvas = surface(width, height);
  drawCover(canvas.getContext("2d"), cover, 0, 0, width, height, crop);
  return toPng(canvas);
}
