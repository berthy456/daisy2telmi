import { CUT_LEVELS, cutChoices, extractBook } from "./daisy.js";
import { cropPreviews, loadCoverFile, loadCoverUrl, previewDataUrl, screen, searchUrl } from "./cover.js";
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
const coverPreview = document.getElementById("cover-preview");
const coverSearch = document.getElementById("cover-search");
const cutInputs = [...document.querySelectorAll('input[name="cut"]')];
const cropRow = document.getElementById("crop-row");
const cropInputs = [...document.querySelectorAll('input[name="crop"]')];
const formatInputs = [...document.querySelectorAll('input[name="format"]')];
const nightRow = document.getElementById("night-row");
const nightInput = document.getElementById("night-mode");

const silentMp3 = new Uint8Array(await (await fetch("./silence.mp3")).arrayBuffer());
const STORED_LANGUAGE = "daisy2telmi.language";
const STORED_CUT = "daisy2telmi.cut";
const STORED_FORMAT = "daisy2telmi.format";
const STORED_CROP = "daisy2telmi.crop";
const STORED_NIGHT = "daisy2telmi.night";
// The summary lists the parts it starts; a book cut to the sentence level has hundreds.
const LISTED_PARTS = 30;

let source = null;
let cover = null;
let lang = "en";
let cut = "chapter";
let crop = "center";
let format = "telmi";
let night = true;
let cropUrls = [];

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
      refreshCrops();
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

function startCrop() {
  const stored = saved(STORED_CROP);
  crop = cropInputs.some((input) => input.value === stored) ? stored : "center";
  for (const input of cropInputs) {
    input.checked = input.value === crop;
    input.addEventListener("change", () => {
      crop = input.value;
      remember(STORED_CROP, crop);
    });
  }
}

/** Each crop band drawn small under the cover picker: which band a tall cover
 * loses is not something a word can tell you. The box keeps the chosen player's
 * ratio, so it shows what that player will show. */
async function showCrops(bitmap) {
  const previews = await cropPreviews(bitmap, screen(format)[0]);
  for (const url of cropUrls) URL.revokeObjectURL(url);
  cropUrls = [];
  for (const input of cropInputs) {
    const url = URL.createObjectURL(new Blob([previews[input.value]], { type: "image/png" }));
    cropUrls.push(url);
    input.closest("label").querySelector("img").src = url;
  }
  cropRow.hidden = false;
}

/** Redraw the crop bands, for a new cover or for a new player's screen. */
function refreshCrops() {
  if (!cover) return;
  showCrops(cover).catch(() => {
    cropRow.hidden = true;
  });
}

function setCover(bitmap) {
  if (cover) cover.close();
  cover = bitmap;
  coverPreview.src = previewDataUrl(bitmap);
  coverPreview.hidden = false;
  coverClear.hidden = false;
  log(t("log_cover_set", { w: bitmap.width, h: bitmap.height }));
  refreshCrops();
}

function clearCover() {
  if (cover) cover.close();
  cover = null;
  coverPreview.hidden = true;
  coverPreview.removeAttribute("src");
  coverClear.hidden = true;
  coverUrl.value = "";
  cropRow.hidden = true;
  for (const url of cropUrls) URL.revokeObjectURL(url);
  cropUrls = [];
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
        cut,
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
  } catch (error) {
    log(t("log_error", { message: error.message ?? error }));
  }
}

function setSource(name, loader) {
  source = { name, loader, entries: null };
  saveButton.disabled = false;
  clearResult();
  logView.textContent = "";
  coverSearch.href = searchUrl(name.replace(/\.[^.]+$/, ""));
  coverSearch.hidden = false;
  log(t("log_loaded", { name }));
  openCutLevels();
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
saveButton.addEventListener("click", saveStory);

startLanguage();
startFormat();
startCut();
startCrop();
startNight();
