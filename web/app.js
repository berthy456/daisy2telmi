import { loadCoverFile, loadCoverUrl, previewDataUrl, searchUrl } from "./cover.js";
import { buildStoryZip } from "./convert.js";
import { LANGUAGES, NAMES, apply, pickLanguage, text } from "./i18n.js";
import { cardAudio } from "./voices.js";
import { readZip } from "./zip.js";

const drop = document.getElementById("drop");
const picker = document.getElementById("picker");
const folderPicker = document.getElementById("folder-picker");
const convertButton = document.getElementById("convert");
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

const silentMp3 = new Uint8Array(await (await fetch("./silence.mp3")).arrayBuffer());
const STORED_LANGUAGE = "daisy2telmi.language";
const STORED_CUT = "daisy2telmi.cut";
// The summary lists the parts it starts; a book cut to the sentence level has hundreds.
const LISTED_PARTS = 30;

let source = null;
let cover = null;
let lang = "en";
let cut = "chapter";

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

function setCover(bitmap) {
  if (cover) cover.close();
  cover = bitmap;
  coverPreview.src = previewDataUrl(bitmap);
  coverPreview.hidden = false;
  coverClear.hidden = false;
  log(t("log_cover_set", { w: bitmap.width, h: bitmap.height }));
}

function clearCover() {
  if (cover) cover.close();
  cover = null;
  coverPreview.hidden = true;
  coverPreview.removeAttribute("src");
  coverClear.hidden = true;
  coverUrl.value = "";
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

async function convert() {
  if (!source) return;
  convertButton.disabled = true;
  downloadLink.hidden = true;
  downloadLink.removeAttribute("href");
  bar.hidden = false;
  bar.value = 0;

  try {
    const entries = await source.loader();
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
        cut,
        t: (key) => t(key),
        cardLabel: (number, total, worded) => t(worded ? "card_label" : "card_number", { n: number, total }),
        cardAudio: async (number) => {
          const voice = await cardAudio(lang, number);
          if (voice === null) log(t("log_card_silent", { n: number }));
          return voice;
        },
      },
    );

    showSummary(story);
    const url = URL.createObjectURL(new Blob([story.zip], { type: "application/zip" }));
    downloadLink.href = url;
    downloadLink.download = `${story.dirName}.zip`;
    downloadLink.hidden = false;
    bar.value = 1;
    log(t("log_ready", { name: `${story.dirName}.zip` }));
  } catch (error) {
    log(t("log_error", { message: error.message ?? error }));
    bar.hidden = true;
  } finally {
    convertButton.disabled = false;
  }
}

function setSource(name, loader) {
  source = { name, loader };
  convertButton.disabled = false;
  downloadLink.hidden = true;
  downloadLink.removeAttribute("href");
  logView.textContent = "";
  coverSearch.href = searchUrl(name.replace(/\.[^.]+$/, ""));
  coverSearch.hidden = false;
  log(t("log_loaded", { name }));
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
convertButton.addEventListener("click", convert);

startLanguage();
startCut();
