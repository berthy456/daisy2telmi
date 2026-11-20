// The cover a DAISY audio pack does not carry.
//
// A 2.02 pack has no image, but its metadata names the print book it was read
// from: `dc:source` holds that book's ISBN. Open Library serves the cover for it
// with no key and with `Access-Control-Allow-Origin: *`, which is why the page
// asks it rather than isbndb.com, whose key costs money.

import { loadCoverUrl } from "./cover.js";

/**
 * The print book's ISBN. `dc:identifier` is the DAISY edition's own number, and
 * one such as `FR-ADV-1310715633` still leaves ten digits when its letters are
 * stripped, so the shape is checked before anything is stripped: digits, spaces
 * and hyphens, with an X only as the last character.
 */
export function isbnOf(book) {
  for (const value of [book.source, book.identifier]) {
    const text = (value ?? "").trim().toUpperCase().replace(/^URN:ISBN:/, "");
    if (!/^[0-9][0-9 -]*[0-9X]$/.test(text)) continue;
    const digits = text.replace(/[ -]/g, "");
    if (/^\d{13}$/.test(digits) || /^\d{9}[0-9X]$/.test(digits)) return digits;
  }
  return null;
}

/** Where Open Library keeps this book's cover, or null when there is nothing to ask. */
export async function coverUrl(book) {
  const isbn = isbnOf(book);
  if (isbn) return `https://covers.openlibrary.org/b/isbn/${isbn}-L.jpg`;
  if (!book.title) return null;
  const params = new URLSearchParams({ title: book.title, limit: "5", fields: "cover_i" });
  if (book.author) params.set("author", book.author);
  for (const doc of await search(`https://openlibrary.org/search.json?${params}`)) {
    if (doc.cover_i) return `https://covers.openlibrary.org/b/id/${doc.cover_i}-L.jpg`;
  }
  return null;
}

async function search(url) {
  try {
    return (await (await fetch(url)).json()).docs ?? [];
  } catch {
    // A blocked or offline lookup only costs the suggestion.
    return [];
  }
}

/**
 * The picture itself, or null. Open Library answers a book it has no cover for
 * with a 1x1 GIF, which is a picture of nothing.
 */
export async function findCover(book, base) {
  const url = await coverUrl(book);
  if (!url) return null;
  const bitmap = await loadCoverUrl(url, base);
  return bitmap !== null && bitmap.width > 1 ? bitmap : null;
}
