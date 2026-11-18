import { readZip } from "./zip.js";
import { buildStoryZip } from "./convert.js";

const drop = document.getElementById("drop");
const picker = document.getElementById("picker");
const folderPicker = document.getElementById("folder-picker");
const convertButton = document.getElementById("convert");
const downloadLink = document.getElementById("download");
const summary = document.getElementById("summary");
const bar = document.getElementById("bar");
const logView = document.getElementById("log");

const silentMp3 = new Uint8Array(await (await fetch("./silence.mp3")).arrayBuffer());

let source = null;

function log(line) {
  logView.textContent += `${line}\n`;
  logView.scrollTop = logView.scrollHeight;
}

function setSource(name, loader) {
  source = { name, loader };
  convertButton.disabled = false;
  downloadLink.hidden = true;
  downloadLink.removeAttribute("href");
  logView.textContent = "";
  log(`loaded ${name}`);
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

function showSummary(story) {
  const chapters = story.book.chapters
    .map((chapter, index) => `${index + 1}. ${chapter.title}`)
    .join("\n");
  summary.textContent = `${story.dirName}\n${story.book.chapters.length} chapter(s)\n${chapters}`;
  summary.hidden = false;
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
    log(`reading ${entries.length} file(s)`);
    const story = await buildStoryZip(entries, silentMp3, (label, done, total) => {
      bar.value = done / total;
      log(label);
    });

    showSummary(story);
    const url = URL.createObjectURL(new Blob([story.zip], { type: "application/zip" }));
    downloadLink.href = url;
    downloadLink.download = `${story.dirName}.zip`;
    downloadLink.hidden = false;
    bar.value = 1;
    log(`ready: ${story.dirName}.zip`);
  } catch (error) {
    log(`error: ${error.message ?? error}`);
    bar.hidden = true;
  } finally {
    convertButton.disabled = false;
  }
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
    log("error: drop a .zip pack, or use the folder button");
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

convertButton.addEventListener("click", convert);
