// The Lunii export: the same story as a STUdio archive, the format Lunii's own tools
// import. Port of src/daisy2telmi/lunii.py.
//
// A Telmi pack is a STUdio pack unfolded, so this walks it back: the cover node is
// rebuilt, the stages get UUIDs again, and the media is renamed to the eight hex
// characters STUdio uses.

import { uuid5 } from "./telmi.js";
import { writeZip } from "./zip.js";

const COVER_CONTROLS = { wheel: true, ok: true, home: false, pause: false, autoplay: false };
const IMAGE_EXTS = [".png", ".bmp", ".jpg", ".jpeg", ".gif", ".webp"];
const AUDIO_EXTS = [".mp3", ".ogg", ".wav", ".flac", ".m4a", ".aac"];

const extOf = (name) => {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot).toLowerCase();
};
const stemOf = (name) => {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? name : name.slice(0, dot);
};

async function sha1Hex(value) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-1", new TextEncoder().encode(value)));
  return [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** STUdio asset name: eight hex characters, like the published packs use. */
async function assetName(source, extension, taken) {
  const digest = (await sha1Hex(source)).toUpperCase();
  for (let offset = 0; offset < 25; offset++) {
    const name = digest.slice(offset, offset + 8);
    if (name.length === 8 && !taken.has(name)) {
      taken.add(name);
      return name + extension;
    }
  }
  throw new Error(`cannot name the asset ${source}`);
}

/**
 * story: what buildStoryFiles returns — {dirName, files, metadata, nodes}.
 * nightMode: tells the Lunii the story can be read with the screen off.
 */
export async function buildStudioFiles(story, nightMode = false) {
  const { dirName, metadata, nodes } = story;
  if (!metadata?.uuid) throw new Error(`the story has no usable uuid: ${metadata?.uuid}`);

  const stages = nodes?.stages || {};
  const actions = nodes?.actions || {};
  if (!Object.keys(stages).length || !Object.keys(actions).length) {
    throw new Error("nodes.json has no stages or actions");
  }

  const media = new Map();
  for (const file of story.files) {
    if (file.name.startsWith(`${dirName}/`)) media.set(file.name.slice(dirName.length + 1), file.data);
  }
  const find = (folder, name, exts) => {
    if (!name) return null;
    const direct = folder ? `${folder}/${name}` : name;
    if (media.has(direct)) return direct;
    for (const extension of exts) {
      const candidate = folder ? `${folder}/${stemOf(name)}${extension}` : `${stemOf(name)}${extension}`;
      if (media.has(candidate)) return candidate;
    }
    return null;
  };

  // Deterministic, so converting the same story twice writes the same archive.
  const stageUuids = {};
  for (const key of Object.keys(stages)) stageUuids[key] = await uuid5(metadata.uuid, `stage:${key}`);

  const taken = new Set();
  const assets = [];
  const named = new Map();
  const register = async (path, kind) => {
    if (path === null) return null;
    if (!named.has(path)) {
      const extension = kind === "image" ? ".png" : extOf(path);
      const name = await assetName(path, extension, taken);
      named.set(path, name);
      assets.push({ name, data: media.get(path) });
    }
    return named.get(path);
  };

  /** Telmi `{action, index}` becomes STUdio `{actionNode, optionIndex}`. */
  const transition = (move) =>
    move && actions[move.action] ? { actionNode: move.action, optionIndex: move.index ?? 0 } : null;

  const coverAudio = find(null, "title.mp3", AUDIO_EXTS);
  if (coverAudio === null) throw new Error("the story has no title.mp3, which a Lunii story starts on");

  const stageNodes = [
    {
      uuid: metadata.uuid,
      type: "cover",
      name: metadata.title || dirName,
      position: { x: 0, y: 0 },
      image: await register(find(null, "title.png", IMAGE_EXTS), "image"),
      audio: await register(coverAudio, "audio"),
      okTransition: transition(nodes.startAction),
      homeTransition: null,
      controlSettings: { ...COVER_CONTROLS },
      squareOne: true,
    },
  ];

  for (const [key, stage] of Object.entries(stages)) {
    const controls = stage.control || {};
    stageNodes.push({
      uuid: stageUuids[key],
      type: "stage",
      name: key,
      position: { x: 0, y: 0 },
      image: await register(find("images", stage.image, IMAGE_EXTS), "image"),
      audio: await register(find("audios", stage.audio, AUDIO_EXTS), "audio"),
      okTransition: transition(stage.ok),
      // A lit home with nothing behind it is the device's own way out of a story,
      // which is what Telmi's home button means too.
      homeTransition: transition(stage.home),
      controlSettings: {
        wheel: Boolean(controls.wheel),
        ok: Boolean(controls.ok),
        home: Boolean(controls.home),
        pause: Boolean(controls.pause),
        autoplay: Boolean(controls.autoplay),
      },
    });
  }

  const actionNodes = [];
  for (const [actionId, options] of Object.entries(actions)) {
    const targets = options.filter((option) => stageUuids[option.stage]).map((option) => stageUuids[option.stage]);
    if (targets.length) actionNodes.push({ id: actionId, name: actionId, position: { x: 0, y: 0 }, options: targets });
  }

  const known = new Set(actionNodes.map((action) => action.id));
  for (const node of stageNodes) {
    for (const field of ["okTransition", "homeTransition"]) {
      if (node[field] && !known.has(node[field].actionNode)) node[field] = null;
    }
  }

  const storyJson = {
    format: "v1",
    version: metadata.version || 1,
    title: metadata.title || dirName,
    description: metadata.description || "",
    nightModeAvailable: Boolean(nightMode),
    stageNodes,
    actionNodes,
  };
  if (metadata.age !== undefined && metadata.age !== null) storyJson.age = metadata.age;
  if (metadata.category) storyJson.category = metadata.category;

  const thumbnail = find(null, metadata.image || "cover.png", IMAGE_EXTS);
  return { storyJson, assets, thumbnail: thumbnail === null ? null : media.get(thumbnail) };
}

export async function buildStudioZip(story, nightMode = false) {
  const { storyJson, assets, thumbnail } = await buildStudioFiles(story, nightMode);
  const entries = [{ name: "story.json", data: new TextEncoder().encode(JSON.stringify(storyJson)) }];
  if (thumbnail !== null) entries.push({ name: "thumbnail.png", data: thumbnail });
  for (const asset of assets.sort((a, b) => (a.name < b.name ? -1 : 1))) {
    entries.push({ name: `assets/${asset.name}`, data: asset.data });
  }
  return writeZip(entries);
}
