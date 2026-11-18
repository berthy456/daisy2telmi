// Cover images: read one from a file or a link, then draw it at Telmi's sizes.
//
// The canvas does the work the desktop build hands to ffmpeg: centre-crop to the
// target ratio and write the chapter number over it in white with a black
// border, which is what stays legible on an unknown photograph.

export const IMAGE_SIZE = [640, 480];
export const COVER_SIZE = [512, 512];

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

/** The cover, cropped to width x height, with `label` drawn across the middle. */
export async function coverPng(cover, width, height, label = "") {
  const canvas = surface(width, height);
  const ctx = canvas.getContext("2d");
  const scale = Math.max(width / cover.width, height / cover.height);
  const drawnWidth = cover.width * scale;
  const drawnHeight = cover.height * scale;
  ctx.drawImage(cover, (width - drawnWidth) / 2, (height - drawnHeight) / 2, drawnWidth, drawnHeight);

  if (label) {
    ctx.font = `bold ${Math.round(height / 7)}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.lineJoin = "round";
    ctx.miterLimit = 2;
    ctx.lineWidth = Math.max(6, Math.round(height / 40));
    ctx.strokeStyle = "#000";
    ctx.strokeText(label, width / 2, height / 2);
    ctx.fillStyle = "#fff";
    ctx.fillText(label, width / 2, height / 2);
  }
  return toPng(canvas);
}
