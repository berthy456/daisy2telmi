import { loadCoverFile, loadCoverUrl, previewDataUrl, searchUrl } from "./cover.js";
import { buildStoryZip } from "./convert.js";
import { LANGUAGES, NAMES, apply, pickLanguage, text } from "./i18n.js";
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

const silentMp3 = new Uint8Array(await (await fetch("./silence.mp3")).arrayBuffer());
const STORED_LANGUAGE = "daisy2telmi.language";

let source = null;
let cover = null;
let lang = "en";

const t = (key, values) => text(lang, key, values);

function log(line) {
  logView.textContent += `${line}\n`;
  logView.scrollTop = logView.scrollHeight;
}

function savedLanguage() {
  try {
    return localStorage.getItem(STORED_LANGUAGE);
  } catch {
    return null;
  }
}

function rememberLanguage(chosen) {
  try {
    localStorage.setItem(STORED_LANGUAGE, chosen);
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
  lang = apply(pickLanguage(savedLanguage(), navigator.language));
  langSelect.value = lang;
  langSelect.addEventListener("change", () => {
    lang = apply(langSelect.value);
    rememberLanguage(lang);
  });
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
  const chapters = story.book.chapters
    .map((chapter, index) => `${index + 1}. ${chapter.title}`)
    .join("\n");
  summary.textContent = `${story.dirName}\n${t("log_chapters", { n: story.book.chapters.length })}\n${chapters}`;
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
        t: (key) => t(key),
        cardLabel: (number, total) => t("card_label", { n: number, total }),
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
