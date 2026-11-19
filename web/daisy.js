// DAISY 2.02 reader over zip entries: find the pack, read the outline, resolve each
// chapter's audio. Port of src/daisy2telmi/{detector,extractor}.py.

import { parseXml, parseClock } from "./xml.js";

const HEADING_LEVELS = { h1: 1, h2: 2, h3: 3, h4: 4, h5: 5, h6: 6 };
const MERGE_EPSILON = 0.005;

export function normalizePath(path) {
  const out = [];
  for (const part of path.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") out.pop();
    else out.push(part);
  }
  return out.join("/");
}

export function dirName(path) {
  const at = path.lastIndexOf("/");
  return at < 0 ? "" : path.slice(0, at);
}

function isIgnored(name) {
  const parts = name.split("/");
  return parts.includes("__MACOSX") || parts[parts.length - 1].startsWith("._");
}

function decodeEntryName(bytes) {
  return new TextDecoder("utf-8").decode(bytes);
}

function textOf(element) {
  let out = "";
  const walk = (node) => {
    if (node.tagName === "#text") out += node.value;
    for (const child of node.children) walk(child);
  };
  walk(element);
  return out.trim();
}

/** Locate the pack root: the shallowest folder holding ncc.html or a .ncx. */
export function findPack(entries) {
  const byDir = new Map();
  for (const entry of entries) {
    if (isIgnored(entry.name)) continue;
    const dir = dirName(entry.name);
    if (!byDir.has(dir)) byDir.set(dir, []);
    byDir.get(dir).push(entry);
  }

  const dirs = [...byDir.keys()].sort((a, b) => a.split("/").length - b.split("/").length);
  for (const dir of dirs.slice(0, 32)) {
    const files = byDir.get(dir);
    const baseName = (entry) => entry.name.split("/").pop().toLowerCase();
    const ncc = files.find((f) => baseName(f) === "ncc.html");
    const ncx = files.filter((f) => baseName(f).endsWith(".ncx")).sort((a, b) => a.name.localeCompare(b.name))[0];
    if (!ncc && !ncx) continue;
    const opf = files.find((f) => f.name.split("/").pop().toLowerCase() === "package.opf");
    return { root: dir, toc: ncc ?? ncx, opf, isNcc: Boolean(ncc) };
  }
  return null;
}

const TELMI_MARKERS = ["metadata.json", "nodes.json", "title.mp3", "title.png"];

/** The folder holding every Telmi story marker, when the input is already a Telmi pack. */
export function findTelmiDir(entries) {
  const byDir = new Map();
  for (const entry of entries) {
    if (isIgnored(entry.name)) continue;
    const dir = dirName(entry.name);
    if (!byDir.has(dir)) byDir.set(dir, new Set());
    byDir.get(dir).add(entry.name.split("/").pop().toLowerCase());
  }
  for (const [dir, names] of byDir) {
    if (TELMI_MARKERS.every((name) => names.has(name))) return dir;
  }
  return null;
}

function npt(value) {
  if (!value) return null;
  let text = value.trim();
  if (text.slice(0, 3).toLowerCase() === "npt") text = text.slice(3).replace(/^=/, "").trim();
  if (!text || text.toLowerCase() === "indefinite") return null;
  const parts = text.split(":");
  const num = (s) => Number.parseFloat(s.replace(/s$/i, ""));
  if (parts.length === 3) return Number(parts[0]) * 3600 + Number(parts[1]) * 60 + num(parts[2]);
  if (parts.length === 2) return Number(parts[0]) * 60 + num(parts[1]);
  const seconds = num(text);
  return Number.isFinite(seconds) ? seconds : null;
}

function merge(segments) {
  const out = [];
  for (const segment of segments) {
    const previous = out[out.length - 1];
    const contiguous =
      previous &&
      previous.src === segment.src &&
      previous.end != null &&
      segment.begin != null &&
      Math.abs(previous.end - segment.begin) < MERGE_EPSILON;
    if (contiguous) out[out.length - 1] = { src: previous.src, begin: previous.begin, end: segment.end };
    else out.push(segment);
  }
  return out;
}

function metaValues(root) {
  const out = new Map();
  for (const meta of root.find("meta")) {
    const name = meta.get("name");
    if (name) {
      const key = name.toLowerCase();
      if (!out.has(key)) out.set(key, (meta.get("content") ?? "").trim());
    }
  }
  return out;
}

export class DaisyError extends Error {}

/** Where to cut the book: at its chapter headings, at every heading, or at every synced mark. */
export const CUT_LEVELS = ["chapter", "paragraph", "sentence"];

/**
 * Which cut levels a pack can actually cut at, from the part counts its own
 * outline gives at each level. A level that adds no parts over the one above it
 * only repeats that level, so there is nothing there to cut; the audio is never
 * asked, which is what keeps a silent stretch from looking like a boundary.
 */
export function cutChoices(parts) {
  const available = [];
  let count = 0;
  for (const [index, level] of CUT_LEVELS.entries()) {
    if (parts[index] > count) {
      available.push(level);
      count = parts[index];
    }
  }
  return available;
}

/** Entries as [{name, data}] from a DAISY 2.02 pack; returns the book structure. */
export function extractBook(entries, level = "chapter") {
  if (!CUT_LEVELS.includes(level)) throw new DaisyError(`unknown cut level: ${level}`);
  const pack = findPack(entries);
  if (!pack) {
    if (findTelmiDir(entries)) {
      throw new DaisyError(
        "this is already a Telmi story (metadata.json, nodes.json, title.mp3, title.png), not a DAISY 2.02 pack. " +
          "A Telmi zip goes straight onto the story teller; convert the original DAISY pack instead."
      );
    }
    throw new DaisyError("no DAISY 2.02 table of contents (ncc.html or *.ncx) found");
  }

  const decoder = new TextDecoder("utf-8");
  const byName = new Map(entries.map((entry) => [normalizePath(entry.name), entry]));
  const parse = (name) => {
    const entry = byName.get(name);
    return entry ? parseXml(decoder.decode(entry.data)) : null;
  };

  const tocRoot = parse(normalizePath(pack.toc.name));
  if (!tocRoot) throw new DaisyError("could not read the table of contents");

  const entries_ = pack.isNcc ? nccEntries(tocRoot) : ncxEntries(tocRoot);
  const metadata = metaValues(tocRoot);

  if (pack.opf) {
    const opf = parse(normalizePath(pack.opf.name));
    if (opf) {
      for (const tag of ["title", "language", "creator", "publisher", "identifier", "description"]) {
        const found = opf.find(tag)[0];
        const key = `dc:${tag}`;
        if (found && !metadata.has(key)) metadata.set(key, textOf(found));
      }
    }
  }

  const smilCache = new Map();
  const audioOf = (element, smilName) => {
    const src = element.get("src");
    if (!src) return null;
    const target = normalizePath(`${dirName(smilName)}/${decodeURIComponent(src)}`);
    return byName.has(target) ? target : null;
  };

  const smilSegments = (smilName) => {
    if (smilCache.has(smilName)) return smilCache.get(smilName);
    const root = parse(smilName);
    const found = [];
    if (root) {
      for (const audio of root.find("audio")) {
        const target = audioOf(audio, smilName);
        if (!target) continue;
        found.push({ src: target, begin: npt(audio.get("clip-begin")), end: npt(audio.get("clip-end")) });
      }
    }
    const result = merge(found);
    smilCache.set(smilName, result);
    return result;
  };

  // The pack's own words at a `text.html#id` anchor, which is what a card can show.
  const textCache = new Map();
  const textAt = (src, base) => {
    const raw = decodeURIComponent(src ?? "");
    const hash = raw.indexOf("#");
    const filePart = hash < 0 ? raw : raw.slice(0, hash);
    const anchor = hash < 0 ? "" : raw.slice(hash + 1);
    if (!filePart || !anchor) return "";
    const name = normalizePath(`${base}/${filePart}`);
    if (!textCache.has(name)) textCache.set(name, parse(name));
    const root = textCache.get(name);
    if (!root) return "";
    let found = null;
    const walk = (node) => {
      for (const child of node.children) {
        if (!found && child.get("id") === anchor) found = child;
        walk(child);
      }
    };
    walk(root);
    return found ? textOf(found).replace(/\s+/g, " ") : "";
  };

  // Each clip of a SMIL with the line the pack synced over it: the sentence level's parts.
  const marksCache = new Map();
  const smilMarks = (smilName) => {
    if (marksCache.has(smilName)) return marksCache.get(smilName);
    const root = parse(smilName);
    const found = [];
    if (root) {
      for (const par of root.find("par")) {
        const audio = par.find("audio")[0];
        const target = audio ? audioOf(audio, smilName) : null;
        if (!target) continue;
        const words = par.find("text")[0];
        found.push({
          segments: [{ src: target, begin: npt(audio.get("clip-begin")), end: npt(audio.get("clip-end")) }],
          text: textAt(words ? words.get("src") ?? "" : "", dirName(smilName)),
        });
      }
    }
    const result = found.length
      ? found
      : smilSegments(smilName).map((segment) => ({ segments: [segment], text: "" }));
    marksCache.set(smilName, result);
    return result;
  };

  // The first words read out in a part; a section number read aloud first is not worth a card.
  const openingText = (marks) => marks.find((mark) => mark.text.length >= 5)?.text ?? marks[0]?.text ?? "";

  const chapterLevel = Math.min(...entries_.filter((e) => !e.frontMatter).map((e) => e.level), 6);
  const chapters = [];
  let frontMatter = [];

  for (const entry of entries_) {
    const filePart = decodeURIComponent(entry.target.split("#")[0]).trim();
    if (!filePart || !filePart.toLowerCase().endsWith(".smil")) continue;
    const smilName = normalizePath(`${dirName(pack.toc.name)}/${filePart}`);
    if (!byName.has(smilName)) continue;
    const segments = smilSegments(smilName);
    if (entry.frontMatter) {
      frontMatter = frontMatter.concat(segments);
    } else if (level === "sentence") {
      for (const mark of smilMarks(smilName)) chapters.push({ title: "", segments: [...mark.segments], text: mark.text });
    } else if (level === "chapter" && entry.level > chapterLevel && chapters.length > 0) {
      chapters[chapters.length - 1].segments.push(...segments);
    } else {
      chapters.push({
        title: entry.title || `Part ${chapters.length + 1}`,
        segments: [...segments],
        text: openingText(smilMarks(smilName)),
      });
    }
  }

  return {
    title: metadata.get("dc:title") || pack.root.split("/").pop() || "Untitled",
    author: metadata.get("dc:creator") || null,
    language: metadata.get("dc:language") || null,
    publisher: metadata.get("dc:publisher") || null,
    narrator: metadata.get("ncc:narrator") || null,
    identifier: metadata.get("dc:identifier") || null,
    totalTime: parseClock(metadata.get("ncc:totaltime")),
    chapters: chapters
      .filter((c) => c.segments.length)
      .map((c, index) => ({ title: c.title || `Part ${index + 1}`, text: c.text ?? "", segments: merge(c.segments) })),
    frontMatter: merge(frontMatter),
  };
}

function nccEntries(root) {
  const body = root.find("body")[0];
  if (!body) return [];
  const out = [];
  const walk = (node) => {
    for (const child of node.children) {
      const level = HEADING_LEVELS[child.tagName.toLowerCase()];
      if (level) {
        const anchor = child.find("a")[0] ?? (child.tagName === "a" ? child : null);
        const href = anchor?.get("href") ?? child.get("href") ?? "";
        out.push({
          level,
          title: textOf(anchor ?? child),
          target: href,
          frontMatter: (child.get("class") ?? "").toLowerCase().split(/\s+/).includes("title"),
        });
      }
      walk(child);
    }
  };
  walk(body);
  return out;
}

function ncxEntries(root, level = 1) {
  const out = [];
  for (const navPoint of root.children) {
    if (navPoint.tagName.toLowerCase() !== "navpoint") continue;
    const declared = navPoint.get("playLevel") ?? navPoint.get("level");
    const current = declared && /^\d+$/.test(declared) ? Number(declared) : level;
    const text = navPoint.children.find((c) => c.tagName.toLowerCase() === "text");
    const content = navPoint.children.find((c) => c.tagName.toLowerCase() === "content");
    const title = text ? (text.get("value") ?? textOf(text)).trim() : "";
    const target = content ? content.get("src") ?? "" : "";
    if (target) out.push({ level: current, title, target, frontMatter: false });
    out.push(...ncxEntries(navPoint, current + 1));
  }
  return out;
}
