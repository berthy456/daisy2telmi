// Telmi story construction: folder naming, uuid, nodes.json, metadata.json, notes.json.
// Port of src/daisy2telmi/telmi_builder.py; the naming rules come from Telmi-Sync's
// Helpers/Strings.js and Helpers/Stories.js.

const UUID_NAMESPACE = "f0e2af62-201e-5155-80a5-f38f2108b694"; // uuid5(NAMESPACE_URL, daisy2telmi wiki url)

function stripDiacritics(value) {
  return [...value.normalize("NFD")]
    .filter((c) => {
      const code = c.codePointAt(0);
      return !(code >= 0x300 && code <= 0x36f);
    })
    .join("")
    .replace(/[̀-ͯ]/g, "");
}

export function normalizeFileName(value) {
  return stripDiacritics(value).replace(/[^a-zA-Z0-9\-.]+/g, " ");
}

export function slugify(value) {
  return stripDiacritics(value).toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

export function storyDirName(title, storyId, age = 0, category = "") {
  const ageText = (age < 10 ? "0" : "") + age;
  return [
    normalizeFileName(category).slice(0, 32),
    ageText,
    normalizeFileName(title).slice(0, 32),
    slugify(storyId).slice(0, 36),
  ].join("_");
}

function hexToBytes(hex) {
  const clean = hex.replace(/-/g, "");
  const out = new Uint8Array(16);
  for (let i = 0; i < 16; i++) out[i] = Number.parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  return out;
}

function bytesToUuid(bytes) {
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** RFC 4122 uuid5 over the daisy2telmi namespace, so the CLI and the page agree. */
export async function storyUuid(book) {
  const seed = book.identifier || `${book.title}|${book.author ?? ""}|${book.chapters.length}`;
  const input = new Uint8Array([...hexToBytes(UUID_NAMESPACE), ...new TextEncoder().encode(seed)]);
  const out = new Uint8Array(await crypto.subtle.digest("SHA-1", input)).subarray(0, 16);
  out[6] = (out[6] & 0x0f) | 0x50;
  out[8] = (out[8] & 0x3f) | 0x80;
  return bytesToUuid(out);
}

export function buildNodes(chapterNames) {
  if (!chapterNames.length) throw new Error("no chapters to build a story from");

  const stages = {};
  const actions = { m: chapterNames.map((_, k) => ({ stage: `m${k}` })) };
  const last = chapterNames.length - 1;

  chapterNames.forEach((_, k) => {
    stages[`m${k}`] = {
      image: `m${k}.png`,
      audio: null,
      ok: { action: `s${k}`, index: 0 },
      home: null,
      control: { ok: true, home: true, autoplay: false },
    };
    stages[`s${k}`] = {
      image: null,
      audio: `s${k}.mp3`,
      ok: k === last ? null : { action: "m", index: k + 1 },
      home: { action: "m", index: k },
      control: { ok: false, home: true, autoplay: true },
    };
    actions[`s${k}`] = [{ stage: `s${k}` }];
  });

  return { startAction: { action: "m", index: 0 }, stages, actions };
}

export function buildMetadata(book, uuid) {
  const details = book.chapters.map((chapter, index) => `- ${chapter.title} (${index + 1}/${book.chapters.length})`);
  const credits = [
    ["Author", book.author],
    ["Narrator", book.narrator],
    ["Publisher", book.publisher],
    ["Language", book.language],
  ]
    .filter(([, value]) => value)
    .map(([label, value]) => `${label}: ${value}`);

  return {
    title: book.title,
    uuid,
    image: "cover.png",
    category: "",
    version: 0,
    age: 0,
    description: credits.length ? `${credits.join(" - ")}\n${details.join("\n")}` : details.join("\n"),
  };
}

export function buildNotes(book) {
  const notes = {};
  book.chapters.forEach((chapter, k) => {
    notes[`m${k}`] = { title: `m${k}`, notes: chapter.title };
    notes[`s${k}`] = { title: chapter.title, notes: "" };
  });
  return notes;
}
