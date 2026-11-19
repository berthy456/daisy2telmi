// The page dictionaries: every language carries the same keys as English.

import assert from "node:assert/strict";
import { test } from "node:test";

const { LANGUAGES, NAMES, RTL, UI, pickLanguage, text } = await import(
  "../../web/i18n.js"
);

test("every language translates every key", () => {
  const keys = Object.keys(UI.en).sort();
  for (const code of LANGUAGES) {
    assert.ok(UI[code], `${code} has no dictionary`);
    assert.deepEqual(Object.keys(UI[code]).sort(), keys, `${code} keys differ from en`);
  }
});

// "source" is French too, and Spanish writes `error:` the same way, so those two
// keys may match English; `card_number` is digits around a slash in every language;
// Telmi and the Flam are the players' names, which no language translates.
// Anything else that matches was left untranslated.
test("no language is left in English by accident", () => {
  const allowed = new Set(["footer_line", "log_error", "card_number", "fmt_telmi", "fmt_flam"]);
  for (const code of LANGUAGES) {
    if (code === "en") continue;
    const copied = Object.keys(UI.en).filter(
      (key) => UI[code][key] === UI.en[key] && !allowed.has(key),
    );
    assert.deepEqual(copied, [], `${code} copies English for ${copied.join(", ")}`);
  }
});

test("the picker names each language in itself", () => {
  assert.deepEqual(Object.keys(NAMES).sort(), [...LANGUAGES].sort());
  assert.equal(NAMES.fr, "Français");
});

test("the browser language picks the page language", () => {
  assert.equal(pickLanguage(null, "fr-FR"), "fr");
  assert.equal(pickLanguage(null, "zh-Hans-CN"), "zh");
  assert.equal(pickLanguage(null, "pt-BR"), "pt");
  assert.equal(pickLanguage(null, "sw"), "en");
  assert.equal(pickLanguage(null, undefined), "en");
});

test("a saved choice beats the browser", () => {
  assert.equal(pickLanguage("tr", "de-DE"), "tr");
  assert.equal(pickLanguage("klingon", "de-DE"), "de");
});

test("the card label fills its numbers", () => {
  assert.equal(text("en", "card_label", { n: 2, total: 23 }), "Chapter 2/23");
  assert.equal(text("ar", "card_label", { n: 2, total: 23 }), "الفصل 2/23");
});

test("an unknown key or language degrades instead of throwing", () => {
  assert.equal(text("nl", "no_such_key"), "no_such_key");
  assert.equal(text("xx", "card_label", { n: 1, total: 4 }), "Chapter 1/4");
});

test("Arabic is the only right-to-left language", () => {
  assert.ok(RTL.has("ar"));
  assert.ok(!RTL.has("ur"));
  assert.ok(!RTL.has("zh"));
});
