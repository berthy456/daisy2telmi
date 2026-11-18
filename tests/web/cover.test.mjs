// The cover helpers that work without a canvas.

import assert from "node:assert/strict";
import { test } from "node:test";

const { COVER_SIZE, IMAGE_SIZE, isReadableUrl, searchUrl } = await import("../../web/cover.js");

test("the search link is a Google image search for the title", () => {
  const url = new URL(searchUrl("ごんぎつね Ruby"));
  assert.equal(url.host, "www.google.com");
  assert.equal(url.searchParams.get("tbm"), "isch");
  assert.equal(url.searchParams.get("q"), "ごんぎつね Ruby");
});

test("only http(s) links are fetched", () => {
  const base = "https://berthy456.github.io/daisy2telmi/";
  assert.ok(isReadableUrl("https://example.com/cover.jpg", base));
  assert.ok(isReadableUrl("/local/cover.png", base));
  assert.ok(isReadableUrl("cover.png", base));
  assert.ok(!isReadableUrl("file:///etc/passwd", base));
  assert.ok(!isReadableUrl("javascript:alert(1)", base));
  assert.ok(!isReadableUrl("data:image/png;base64,AAA", base));
  assert.ok(!isReadableUrl("", base));
  assert.ok(!isReadableUrl("not a url at all", "not a base either"));
});

test("the image sizes are the ones Telmi uses", () => {
  assert.deepEqual(IMAGE_SIZE, [640, 480]);
  assert.deepEqual(COVER_SIZE, [512, 512]);
});
