// Which number the page asks a cover service with, and what it does with the answer.
// The picture itself needs a canvas, so it is cover.test.mjs's business, not this file's.

import assert from "node:assert/strict";
import { test } from "node:test";

const { coverUrl, isbnOf } = await import("../../web/covers.js");

// Values from the Rachel pack: dc:identifier is the DAISY edition's own number,
// dc:source is the print book's ISBN.
const DAISY_ID = "FR-ADV-1310715633";
const PRINT_ISBN = "979-10-363-6487-7";

const book = (over = {}) => ({ title: "Wesh la fée", identifier: DAISY_ID, source: PRINT_ISBN, ...over });

/** Stand in for the network: record what was asked, reply with what a test wants. */
function asked(replies, fail = false) {
  const urls = [];
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    if (fail) throw new TypeError("failed to fetch");
    for (const [part, body] of Object.entries(replies ?? {})) {
      if (String(url).includes(part)) return { json: async () => body };
    }
    throw new Error(`unexpected request: ${url}`);
  };
  return urls;
}

test("the print book's ISBN is the one in dc:source", () => {
  assert.equal(isbnOf(book()), "9791036364877");
});

test("a DAISY identifier is not taken for an ISBN", () => {
  assert.equal(isbnOf(book({ source: null })), null);
});

test("an ISBN-10 keeps its check letter", () => {
  assert.equal(isbnOf(book({ source: "0-140-44918-0", identifier: null })), "0140449180");
  assert.equal(isbnOf(book({ source: "081269018x", identifier: null })), "081269018X");
});

test("an ISBN written as a URN is still an ISBN", () => {
  assert.equal(isbnOf(book({ source: "urn:isbn:9780140449185", identifier: null })), "9780140449185");
});

test("an ISBN points straight at the cover", async () => {
  const urls = asked({});
  assert.equal(await coverUrl(book()), "https://covers.openlibrary.org/b/isbn/9791036364877-L.jpg");
  assert.deepEqual(urls, [], "an ISBN needs no search");
});

test("without an ISBN the title and author are asked", async () => {
  const urls = asked({ "search.json": { docs: [{ cover_i: 12123878 }] } });
  const url = await coverUrl(book({ source: null, author: "Rachel Corenblit" }));
  const query = new URL(urls[0]).searchParams;
  assert.equal(url, "https://covers.openlibrary.org/b/id/12123878-L.jpg");
  assert.deepEqual(query.getAll("title"), ["Wesh la fée"]);
  assert.deepEqual(query.getAll("author"), ["Rachel Corenblit"]);
});

test("a work with no cover is no suggestion", async () => {
  asked({ "search.json": { docs: [{ title: "Wesh la fée" }] } });
  assert.equal(await coverUrl(book({ source: null })), null);
});

test("a book with neither ISBN nor title asks nothing", async () => {
  const urls = asked({});
  assert.equal(await coverUrl(book({ source: null, identifier: null, title: "" })), null);
  assert.deepEqual(urls, []);
});

test("an unreachable service is no error, only no cover", async () => {
  asked({}, true);
  assert.equal(await coverUrl(book({ source: null })), null);
});
