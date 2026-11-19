// Cover images: read one from a file or a link, then draw it at the chosen
// player's sizes.
//
// The canvas does the work the desktop build hands to ffmpeg: centre-crop to the
// target ratio and write the chapter number over it in white with a black
// border, which is what stays legible on an unknown photograph.

export const IMAGE_SIZE = [640, 480];
export const COVER_SIZE = [512, 512];
export const CARD_MARGIN = 24;
export const CARD_LINES = 3;
export const CARD_WORDS = 20;

// What each player's screen shows, so the picture is drawn where it will be seen:
// a cover cropped for a 320x240 Lunii keeps the band that Lunii displays.
const SCREENS = {
  telmi: [IMAGE_SIZE, COVER_SIZE],
  lunii: [
    [320, 240],
    [320, 240],
  ],
  flam: [
    [320, 212],
    [104, 136],
  ],
};

/** The scene and cover sizes of one player. */
export function screen(player) {
  return SCREENS[player];
}

/** The margin and thumbnail of a card this wide: a smaller screen shrinks both. */
function layout(width) {
  const step = width / IMAGE_SIZE[0];
  const thumb = Math.floor(width / 4);
  return {
    margin: Math.max(6, Math.round(CARD_MARGIN * step)),
    thumb: [thumb, Math.floor((thumb * 3) / 4)],
  };
}

// A Lunii that is not a Flam has no colour panel: four grey levels, and the light
// end of them, so its cards are drawn the other way round — white ground, black ink.
export const STYLES = ["colour", "bw"];
const PALETTE = {
  colour: { background: "#1a1e2a", ink: "#fff", border: "#000" },
  bw: { background: "#fff", ink: "#000", border: "#fff" },
};
const GREY_LEVELS = [0, 96, 192, 255];
const GREY_CUTS = [40, 110, 185];

/**
 * One of the four levels, from a 0-255 luminance. The contrast and the levels
 * match the desktop build's ffmpeg chain, so both draw the same card.
 */
export function greyLevel(luminance) {
  const contrast = (luminance - 128) * 1.6 + 128;
  return GREY_LEVELS[GREY_CUTS.filter((cut) => contrast >= cut).length];
}

/** Flatten a finished picture to the four levels a plain Lunii shows. */
function toGreys(ctx, width, height) {
  const image = ctx.getImageData(0, 0, width, height);
  for (let at = 0; at < image.data.length; at += 4) {
    // The weights are the ones the device's own converter uses, so the card
    // that reaches its screen is the one drawn here.
    const grey = greyLevel(0.299 * image.data[at] + 0.587 * image.data[at + 1] + 0.114 * image.data[at + 2]);
    image.data[at] = image.data[at + 1] = image.data[at + 2] = grey;
  }
  ctx.putImageData(image, 0, 0);
}

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

/** Each crop band, small, as PNG bytes: what the page shows under the cover picker.
 * The box keeps the ratio of the player chosen, so it shows what that player shows. */
export async function cropPreviews(cover, scene = IMAGE_SIZE, width = 160) {
  const height = Math.round((width * scene[1]) / scene[0]);
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
export async function cardPng(
  label,
  text,
  cover = null,
  crop = "center",
  width = IMAGE_SIZE[0],
  height = IMAGE_SIZE[1],
  style = "colour",
) {
  const canvas = surface(width, height);
  const ctx = canvas.getContext("2d");
  const { margin, thumb } = layout(width);
  ctx.fillStyle = PALETTE[style].background;
  ctx.fillRect(0, 0, width, height);
  ctx.lineJoin = "round";
  ctx.miterLimit = 2;
  ctx.textBaseline = "top";
  if (cover) drawCover(ctx, cover, margin, margin, ...thumb, crop);

  ctx.textAlign = "right";
  ctx.font = `bold ${Math.round(height / 11)}px system-ui, sans-serif`;
  ctx.lineWidth = 6;
  ctx.strokeStyle = PALETTE[style].border;
  ctx.fillStyle = PALETTE[style].ink;
  ctx.strokeText(label, width - margin, margin);
  ctx.fillText(label, width - margin, margin);

  const size = Math.round(height / 17);
  ctx.textAlign = "left";
  ctx.font = `${size}px system-ui, sans-serif`;
  ctx.lineWidth = 4;
  const pitch = Math.round(size * 1.3);
  for (const [index, line] of cardWords(ctx, text, width - 2 * margin).entries()) {
    const top = margin + thumb[1] + margin + index * pitch;
    ctx.strokeText(line, margin, top);
    ctx.fillText(line, margin, top);
  }
  // Flattened last, once the cover and the letters are all down, so a card
  // cannot pick up a fifth grey where two layers meet.
  if (style === "bw") toGreys(ctx, width, height);
  return toPng(canvas);
}

/** The cover, cropped to width x height. */
export async function coverPng(cover, width, height, crop = "center", style = "colour") {
  const canvas = surface(width, height);
  const ctx = canvas.getContext("2d");
  drawCover(ctx, cover, 0, 0, width, height, crop);
  if (style === "bw") toGreys(ctx, width, height);
  return toPng(canvas);
}
