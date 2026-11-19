"""Write the pack a Lunii takes: a STUdio archive, the format Lunii's own tools import.

A Telmi pack is a STUdio pack unfolded — Telmi Sync's converter strips the cover
node into `metadata.json` + `title.mp3` + `startAction` and renames the stages to
`s0`, `a0`, `0.mp3`. This walks that back: the cover node is rebuilt, the stages
get UUIDs again, and the media is renamed to the eight hex characters STUdio uses.

The device layout (`ri`, `si`, `li`, `ni` and `rf/`, `sf/` on the SD card) is what
Lunii.QT writes from this archive; it needs the device's own key for the `bt`
authorisation file, so it is not something a converter can produce on its own.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Mapping
from uuid import UUID, uuid5

IMAGE_EXTS = (".png", ".bmp", ".jpg", ".jpeg", ".gif", ".webp")
AUDIO_EXTS = (".mp3", ".ogg", ".wav", ".flac", ".m4a", ".aac")

# Read off a genuine story on a device: the wheel turns between stories, OK starts
# the one in front of you, and nothing chains on its own.
COVER_CONTROLS = {"wheel": True, "ok": True, "home": False, "pause": False, "autoplay": False}


class LuniiError(RuntimeError):
    """Raised when a story folder cannot be turned into a STUdio archive."""


def _asset_name(source: str, extension: str, taken: set[str]) -> str:
    """STUdio asset name: eight hex characters, like the published packs use."""
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest().upper()
    for offset in range(0, 25):
        name = digest[offset : offset + 8]
        if len(name) == 8 and name not in taken:
            taken.add(name)
            return name + extension
    raise LuniiError(f"cannot name the asset {source}")


def _media(story_dir: Path, subdir: str, name: str | None, exts: tuple[str, ...]) -> Path | None:
    """Locate a media file; the declared extension is not always the real one."""
    if not name:
        return None
    direct = story_dir / subdir / name
    if direct.is_file():
        return direct
    stem = Path(name).stem
    for extension in exts:
        candidate = story_dir / subdir / (stem + extension)
        if candidate.is_file():
            return candidate
    return None


def build_story_json(
    metadata: Mapping, nodes: Mapping, story_dir: Path, night_mode: bool = False
) -> tuple[dict, dict[str, Path]]:
    """The STUdio `story.json` and the assets to copy beside it.

    `metadata` and `nodes` are the Telmi pack's own two files, which is what makes
    the two archives describe the same story.
    """
    story_dir = Path(story_dir)
    try:
        story_uuid = UUID(str(metadata.get("uuid")))
    except (TypeError, ValueError) as exc:
        raise LuniiError(f"the story has no usable uuid: {metadata.get('uuid')!r}") from exc

    stages = nodes.get("stages") or {}
    actions = nodes.get("actions") or {}
    if not stages or not actions:
        raise LuniiError("nodes.json has no stages or actions")

    # Deterministic, so converting the same story twice writes the same archive.
    stage_uuids = {key: str(uuid5(story_uuid, f"stage:{key}")) for key in stages}

    assets: dict[str, Path] = {}
    taken: set[str] = set()
    names: dict[str, str] = {}

    def register(path: Path | None, kind: str) -> str | None:
        if path is None:
            return None
        key = str(path)
        if key not in names:
            extension = ".png" if kind == "image" else path.suffix.lower()
            relative = str(path.relative_to(story_dir))
            names[key] = _asset_name(relative, extension, taken)
            assets[names[key]] = path
        return names[key]

    def transition(move: Mapping | None) -> dict | None:
        """Telmi `{action, index}` becomes STUdio `{actionNode, optionIndex}`."""
        if not move or move.get("action") not in actions:
            return None
        return {"actionNode": move["action"], "optionIndex": int(move.get("index") or 0)}

    cover_audio = _media(story_dir, ".", "title.mp3", AUDIO_EXTS)
    if cover_audio is None:
        raise LuniiError(f"{story_dir} has no title.mp3, which a Lunii story starts on")

    stage_nodes = [
        {
            "uuid": str(story_uuid),
            "type": "cover",
            "name": metadata.get("title") or story_dir.name,
            "position": {"x": 0, "y": 0},
            "image": register(_media(story_dir, ".", "title.png", IMAGE_EXTS), "image"),
            "audio": register(cover_audio, "audio"),
            "okTransition": transition(nodes.get("startAction")),
            "homeTransition": None,
            "controlSettings": dict(COVER_CONTROLS),
            "squareOne": True,
        }
    ]

    for key, stage in stages.items():
        controls = stage.get("control") or {}
        stage_nodes.append(
            {
                "uuid": stage_uuids[key],
                "type": "stage",
                "name": key,
                "position": {"x": 0, "y": 0},
                "image": register(_media(story_dir, "images", stage.get("image"), IMAGE_EXTS), "image"),
                "audio": register(_media(story_dir, "audios", stage.get("audio"), AUDIO_EXTS), "audio"),
                "okTransition": transition(stage.get("ok")),
                # A lit home with nothing behind it is the device's own way out of a
                # story, which is what Telmi's home button means too.
                "homeTransition": transition(stage.get("home")),
                "controlSettings": {
                    "wheel": bool(controls.get("wheel")),
                    "ok": bool(controls.get("ok")),
                    "home": bool(controls.get("home")),
                    "pause": bool(controls.get("pause")),
                    "autoplay": bool(controls.get("autoplay")),
                },
            }
        )

    action_nodes = []
    for action_id, options in actions.items():
        targets = [stage_uuids[option["stage"]] for option in options if option.get("stage") in stage_uuids]
        if targets:
            action_nodes.append(
                {"id": action_id, "name": action_id, "position": {"x": 0, "y": 0}, "options": targets}
            )

    known = {action["id"] for action in action_nodes}
    for node in stage_nodes:
        for field in ("okTransition", "homeTransition"):
            if node[field] and node[field]["actionNode"] not in known:
                node[field] = None

    story_json = {
        "format": "v1",
        "version": int(metadata.get("version") or 1) or 1,
        "title": metadata.get("title") or story_dir.name,
        "description": metadata.get("description") or "",
        "nightModeAvailable": bool(night_mode),
        "stageNodes": stage_nodes,
        "actionNodes": action_nodes,
    }
    if metadata.get("age") is not None:
        story_json["age"] = metadata["age"]
    if metadata.get("category"):
        story_json["category"] = metadata["category"]

    return story_json, assets


def write_studio_zip(story_dir: Path, zip_path: Path | None = None, night_mode: bool = False) -> Path:
    """Write the STUdio archive of the Telmi story folder at `story_dir`."""
    story_dir = Path(story_dir)
    try:
        metadata = json.loads((story_dir / "metadata.json").read_text(encoding="utf-8"))
        nodes = json.loads((story_dir / "nodes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LuniiError(f"{story_dir} is not a converted story: {exc}") from exc

    story_json, assets = build_story_json(metadata, nodes, story_dir, night_mode)
    zip_path = Path(zip_path) if zip_path else story_dir.parent / f"{story_dir.name}-lunii.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    thumbnail = _media(story_dir, ".", metadata.get("image") or "cover.png", IMAGE_EXTS)
    # Stored, not deflated: the media is already MP3 and PNG, and Lunii.QT reads the
    # archive straight off the card.
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("story.json", json.dumps(story_json, ensure_ascii=False))
        if thumbnail is not None:
            archive.write(thumbnail, "thumbnail.png")
        for name, source in sorted(assets.items()):
            archive.write(source, f"assets/{name}")
    return zip_path
