import { CUT_LEVELS, cutChoices, extractBook } from "./daisy.js";
import { CROP_FOCUS, MAX_ZOOM, cropRect, loadCoverFile, loadCoverUrl, screen, searchUrl } from "./cover.js";
import { findCover } from "./covers.js";
import { buildStoryZip } from "./convert.js";
import { LANGUAGES, NAMES, apply, pickLanguage, text } from "./i18n.js";
import { buildStudioZip } from "./lunii.js";
import { cardAudio } from "./voices.js";
import { readZip } from "./zip.js";

const drop = document.getElementById("drop");
const picker = document.getElementById("picker");
const folderPicker = document.getElementById("folder-picker");
const saveButton = document.getElementById("save");
const downloadLink = document.getElementById("download");
const summary = document.getElementById("summary");
const bar = document.getElementById("bar");
const logView = document.getElementById("log");
const langSelect = document.getElementById("lang");
const coverPicker = document.getElementById("cover-picker");
const coverUrl = document.getElementById("cover-url");
const coverUse = document.getElementById("cover-use");
const coverClear = document.getElementById("cover-clear");
const coverSearch = document.getElementById("cover-search");
const cutInputs = [...document.querySelectorAll('input[name="cut"]')];
const cropBox = document.getElementById("crop-box");
const cropCanvas = document.getElementById("crop-canvas");
const cropInputs = [...document.querySelectorAll('input[name="crop"]')];
const cropZoom = document.getElementById("crop-zoom");
const cropReset = document.getElementById("crop-reset");
const formatInputs = [...document.querySelectorAll('input[name="format"]')];
const nightRow = document.getElementById("night-row");
const nightInput = document.getElementById("night-mode");
const partsBox = document.getElementById("parts");
const partsList = document.getElementById("parts-list");
const partsNote = document.getElementById("parts-note");
const partsAll = document.getElementById("parts-all");

const silentMp3 = new Uint8Array(await (await fetch("./silence.mp3")).arrayBuffer());
const STORED_LANGUAGE = "daisy2telmi.language";
const STORED_CUT = "daisy2telmi.cut";
const STORED_FORMAT = "daisy2telmi.format";
const STORED_CROP = "daisy2telmi.crop";
const STORED_NIGHT = "daisy2telmi.night";
// The summary lists the parts it starts; a book cut to the sentence level has hundreds.
const LISTED_PARTS = 30;
// A sentence-level book can run to thousands of parts: past this the page says
// how many there are instead of drawing a thousand checkboxes.
const LISTED_BOXES = 400;

// The crop box is drawn this wide, whatever the player's ratio: a 360 px frame
// shows a cover's lettering well enough to place it by eye.
const CROP_WIDTH = 360;

let source = null;
let cover = null;
let lang = "en";
let cut = "chapter";
let crop = "center";
let format = "telmi";
let night = true;
// Where the frame sits over the cover and how far it is enlarged. `focus` stays
// null while one of the three named bands is chosen, and takes over once the
// user moves the frame themselves.
let focus = null;
let zoom = 1;
// Part numbers left out of the story, in the numbering of the chosen cut level.
let dropped = new Set();
// Counts the lookups in flight, so an answer about a pack that has been replaced
// is thrown away instead of landing in the cover box.
let coverJob = 0;

const t = (key, values) => text(lang, key, values);

function log(line) {
  logView.textContent += `${line}\n`;
  logView.scrollTop = logView.scrollHeight;
}

function saved(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function remember(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // A blocked or full localStorage only costs the saved choice.
  }
}

function startLanguage() {
  for (const code of LANGUAGES) {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = NAMES[code];
    langSelect.append(option);
  }
  lang = apply(pickLanguage(saved(STORED_LANGUAGE), navigator.language));
  langSelect.value = lang;
  langSelect.addEventListener("change", () => {
    lang = apply(langSelect.value);
    remember(STORED_LANGUAGE, lang);
  });
}

function startCut() {
  const stored = saved(STORED_CUT);
  cut = cutInputs.some((input) => input.value === stored) ? stored : "chapter";
  for (const input of cutInputs) {
    input.checked = input.value === cut;
    input.addEventListener("change", () => {
      cut = input.value;
      remember(STORED_CUT, cut);
      showParts();
    });
  }
}

function startFormat() {
  const stored = saved(STORED_FORMAT);
  format = formatInputs.some((input) => input.value === stored) ? stored : "telmi";
  for (const input of formatInputs) {
    input.checked = input.value === format;
    input.addEventListener("change", () => {
      format = input.value;
      remember(STORED_FORMAT, format);
      showNight();
      drawCrop();
    });
  }
  showNight();
}

/** Night mode is a flag of the Lunii archive, so the box only shows for that player. */
function showNight() {
  nightRow.hidden = format !== "lunii";
}

function startNight() {
  night = saved(STORED_NIGHT) !== "0";
  nightInput.checked = night;
  nightInput.addEventListener("change", () => {
    night = nightInput.checked;
    remember(STORED_NIGHT, night ? "1" : "0");
  });
}

const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

/** The frame's place over the cover: the chosen band until the user moves it. */
function currentFocus() {
  return focus ?? CROP_FOCUS[crop];
}

function cropView() {
  return { crop, zoom, focus };
}

/**
 * The crop box drawn at the chosen player's ratio: what is inside this frame is
 * what the story will carry, so the choice is made on the picture rather than
 * described to it.
 */
function drawCrop() {
  if (!cover) return;
  const [scene] = screen(format);
  const width = CROP_WIDTH;
  const height = Math.round((width * scene[1]) / scene[0]);
  if (cropCanvas.width !== width || cropCanvas.height !== height) {
    cropCanvas.width = width;
    cropCanvas.height = height;
  }
  const ctx = cropCanvas.getContext("2d");
  ctx.clearRect(0, 0, width, height);
  const [x, y, drawnWidth, drawnHeight] = cropRect(cover, width, height, cropView());
  ctx.drawImage(cover, x, y, drawnWidth, drawnHeight);
}

/** A drag moves the cover, so the frame's place moves the other way. The canvas
 * is scaled down by CSS on a narrow screen, hence the divide. */
function moveFocus(from, dx, dy) {
  const width = cropCanvas.width;
  const height = cropCanvas.height;
  const scale = cropCanvas.clientWidth / width || 1;
  const [, , drawnWidth, drawnHeight] = cropRect(cover, width, height, { focus: from, zoom });
  const out = [...from];
  if (drawnWidth > width) out[0] = clamp(out[0] - dx / scale / (drawnWidth - width), 0, 1);
  if (drawnHeight > height) out[1] = clamp(out[1] - dy / scale / (drawnHeight - height), 0, 1);
  return out;
}

function setZoom(value) {
  zoom = clamp(value, 1, MAX_ZOOM);
  cropZoom.value = String(zoom);
  drawCrop();
}

/** A moved frame answers to no band, so the three radios let go of it. */
function setFocus(next) {
  focus = next;
  for (const input of cropInputs) input.checked = false;
  drawCrop();
}

function moveFrame(dx, dy) {
  setFocus(moveFocus(currentFocus(), dx, dy));
}

function resetCrop() {
  crop = "center";
  focus = null;
  zoom = 1;
  cropZoom.value = "1";
  for (const input of cropInputs) input.checked = input.value === crop;
  remember(STORED_CROP, crop);
  drawCrop();
}

function startCrop() {
  const stored = saved(STORED_CROP);
  crop = cropInputs.some((input) => input.value === stored) ? stored : "center";
  for (const input of cropInputs) {
    input.checked = input.value === crop;
    input.addEventListener("change", () => {
      crop = input.value;
      focus = null;
      remember(STORED_CROP, crop);
      drawCrop();
    });
  }
  cropZoom.max = String(MAX_ZOOM);
  cropZoom.addEventListener("input", () => setZoom(Number(cropZoom.value)));
  cropReset.addEventListener("click", resetCrop);

  let drag = null;
  cropCanvas.addEventListener("pointerdown", (event) => {
    if (!cover) return;
    cropCanvas.setPointerCapture(event.pointerId);
    drag = { x: event.clientX, y: event.clientY, focus: currentFocus() };
  });
  // A drag reports how far the pointer travelled from where it went down, so it
  // is measured against the frame as it was then, not as each move left it.
  cropCanvas.addEventListener("pointermove", (event) => {
    if (!drag) return;
    setFocus(moveFocus(drag.focus, event.clientX - drag.x, event.clientY - drag.y));
  });
  cropCanvas.addEventListener("pointerup", () => (drag = null));
  cropCanvas.addEventListener("pointercancel", () => (drag = null));
  cropCanvas.addEventListener(
    "wheel",
    (event) => {
      if (!cover) return;
      event.preventDefault();
      setZoom(zoom * (1 - event.deltaY / 400));
    },
    { passive: false },
  );
  // The keyboard reaches the same frame: the arrows move it, + and - enlarge it.
  cropCanvas.addEventListener("keydown", (event) => {
    const step = { ArrowLeft: [1, 0], ArrowRight: [-1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] }[event.key];
    if (step) {
      event.preventDefault();
      moveFrame(step[0] * CROP_WIDTH / 10, step[1] * CROP_WIDTH / 10);
    } else if (event.key === "+" || event.key === "=") setZoom(zoom * 1.2);
    else if (event.key === "-") setZoom(zoom / 1.2);
  });
}

function setCover(bitmap) {
  if (cover) cover.close();
  cover = bitmap;
  coverClear.hidden = false;
  cropBox.hidden = false;
  log(t("log_cover_set", { w: bitmap.width, h: bitmap.height }));
  drawCrop();
}

function clearCover() {
  if (cover) cover.close();
  cover = null;
  cropBox.hidden = true;
  cropCanvas.getContext("2d").clearRect(0, 0, cropCanvas.width, cropCanvas.height);
  coverClear.hidden = true;
  coverUrl.value = "";
  // The frame belongs to the cover that went away; the chosen band does not.
  focus = null;
  zoom = 1;
  cropZoom.value = "1";
}

/**
 * The cover the pack does not carry, asked for as soon as the pack is read. A
 * cover the user picked is never replaced by a suggestion, and a newer pack
 * cancels an answer that is still on its way.
 */
async function suggestCover() {
  const job = ++coverJob;
  if (cover) return;
  let bitmap = null;
  try {
    bitmap = await findCover(extractBook(await packEntries(), cut), location.href);
  } catch {
    bitmap = null;
  }
  if (job !== coverJob || cover) return;
  log(bitmap ? t("cover_found") : t("cover_none"));
  if (bitmap) setCover(bitmap);
}

function partSeconds(chapter) {
  return chapter.segments.reduce((sum, part) => sum + Math.max(0, (part.end ?? 0) - (part.begin ?? 0)), 0);
}

function formatSeconds(seconds) {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/**
 * The parts the pack was cut into, each with a box to leave it out. The numbers
 * belong to the chosen level, so changing level redraws the list and forgets the
 * parts left out of the old one.
 */
async function showParts() {
  if (!source) return;
  dropped.clear();
  partsAll.hidden = true;
  partsList.textContent = "";
  try {
    const { chapters } = extractBook(await packEntries(), cut);
    if (chapters.length > LISTED_BOXES) {
      partsNote.textContent = t("parts_too_many", { n: chapters.length });
      partsBox.hidden = false;
      return;
    }
    partsNote.textContent = "";
    chapters.forEach((chapter, index) => {
      const row = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = true;
      box.addEventListener("change", () => {
        if (box.checked) dropped.delete(index + 1);
        else dropped.add(index + 1);
        partsAll.hidden = dropped.size === 0;
      });
      const title = document.createElement("span");
      title.textContent = `${index + 1}. ${chapter.title}`;
      const length = document.createElement("span");
      length.className = "muted";
      length.textContent = formatSeconds(partSeconds(chapter));
      row.append(box, title, length);
      partsList.append(row);
    });
    partsBox.hidden = false;
  } catch {
    partsBox.hidden = true;
  }
}

function keepAllParts() {
  for (const box of partsList.querySelectorAll("input")) box.checked = true;
  dropped.clear();
  partsAll.hidden = true;
}

function showSummary(story) {
  const parts = story.book.chapters;
  const listed = parts.slice(0, LISTED_PARTS).map((part, index) => `${index + 1}. ${part.title}`).join("\n");
  const more = parts.length > LISTED_PARTS ? `\n${t("summary_more", { n: parts.length - LISTED_PARTS })}` : "";
  summary.textContent = `${story.dirName}\n${t("log_chapters", { n: parts.length })}\n${listed}${more}`;
  summary.hidden = false;
  coverSearch.href = searchUrl(story.book.title);
  coverSearch.hidden = false;
}

function clearResult() {
  downloadLink.hidden = true;
  downloadLink.removeAttribute("href");
}

/** One action: build the story for the chosen player and hand the zip over. */
async function saveStory() {
  if (!source) return;
  saveButton.disabled = true;
  clearResult();
  bar.hidden = false;
  bar.value = 0;

  try {
    const entries = await packEntries();
    log(t("log_files", { n: entries.length }));
    const story = await buildStoryZip(
      entries,
      silentMp3,
      (label, done, total) => {
        bar.value = done / total;
        log(label);
      },
      {
        cover,
        crop,
        zoom,
        focus,
        cut,
        drop: [...dropped],
        player: format,
        style: format === "lunii" ? "bw" : "colour",
        t: (key) => t(key),
        cardLabel: (number, total, worded) => t(worded ? "card_label" : "card_number", { n: number, total }),
        cardAudio: async (number) => {
          const voice = await cardAudio(lang, number);
          if (voice === null) log(t("log_card_silent", { n: number }));
          return voice;
        },
      },
    );

    // One archive, for the player chosen: a Lunii takes the STUdio form of the
    // same story, the Flam launcher imports the Telmi one.
    const studio = format === "lunii";
    const name = `${story.dirName}${studio ? "-lunii" : ""}.zip`;
    const bytes = studio ? await buildStudioZip(story, night) : story.zip;

    showSummary(story);
    downloadLink.href = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
    downloadLink.download = name;
    downloadLink.hidden = false;
    bar.value = 1;
    log(t("log_ready", { name }));
    // The button asked for the file, so it arrives without a second click. The
    // link stays on screen in case the browser wants one.
    downloadLink.click();
  } catch (error) {
    log(t("log_error", { message: error.message ?? error }));
    bar.hidden = true;
  } finally {
    saveButton.disabled = false;
  }
}

/** The pack read once: the cut levels need its outline, and the conversion needs the same files. */
function packEntries() {
  source.entries ??= source.loader();
  return source.entries;
}

/**
 * Open the cut levels this pack can cut at, once its outline has been read.
 * The counts come from the pack's own table of contents and its synced marks,
 * never from its audio, so a level the pack has nothing to cut at stays shut.
 */
async function openCutLevels() {
  for (const input of cutInputs) input.disabled = true;
  try {
    const entries = await packEntries();
    const choices = cutChoices(CUT_LEVELS.map((level) => extractBook(entries, level).chapters.length));
    if (!choices.includes(cut)) {
      cut = choices[Math.min(CUT_LEVELS.indexOf(cut), choices.length - 1)];
      remember(STORED_CUT, cut);
    }
    for (const input of cutInputs) {
      input.disabled = !choices.includes(input.value);
      input.checked = input.value === cut;
    }
    log(t("log_cut_levels", { levels: choices.map((level) => t(`cut_${level}`)).join(", ") }));
    await showParts();
  } catch (error) {
    log(t("log_error", { message: error.message ?? error }));
  }
}

function setSource(name, loader) {
  source = { name, loader, entries: null };
  saveButton.disabled = false;
  clearResult();
  partsBox.hidden = true;
  logView.textContent = "";
  coverSearch.href = searchUrl(name.replace(/\.[^.]+$/, ""));
  coverSearch.hidden = false;
  log(t("log_loaded", { name }));
  openCutLevels();
  suggestCover();
}

async function entriesFromZip(file) {
  return readZip(new Uint8Array(await file.arrayBuffer()));
}

async function entriesFromFolder(fileList) {
  const entries = [];
  for (const file of fileList) {
    entries.push({
      name: file.webkitRelativePath || file.name,
      data: new Uint8Array(await file.arrayBuffer()),
    });
  }
  return entries;
}

drop.addEventListener("dragover", (event) => {
  event.preventDefault();
  drop.classList.add("over");
});
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", async (event) => {
  event.preventDefault();
  drop.classList.remove("over");
  const file = event.dataTransfer.files[0];
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".zip")) {
    log(t("log_drop_zip"));
    return;
  }
  setSource(file.name, () => entriesFromZip(file));
});

picker.addEventListener("change", () => {
  const file = picker.files[0];
  if (file) setSource(file.name, () => entriesFromZip(file));
});

folderPicker.addEventListener("change", () => {
  if (folderPicker.files.length) setSource(`${folderPicker.files.length} files`, () => entriesFromFolder(folderPicker.files));
});

coverPicker.addEventListener("change", async () => {
  const file = coverPicker.files[0];
  if (!file) return;
  const bitmap = await loadCoverFile(file);
  if (bitmap) setCover(bitmap);
  else log(t("log_cover_bad"));
  coverPicker.value = "";
});

coverUse.addEventListener("click", async () => {
  const bitmap = await loadCoverUrl(coverUrl.value, location.href);
  if (bitmap) setCover(bitmap);
  else log(t("log_cover_url"));
});

coverClear.addEventListener("click", clearCover);
partsAll.addEventListener("click", keepAllParts);
saveButton.addEventListener("click", saveStory);

startLanguage();
startFormat();
startCut();
startCrop();
startNight();
