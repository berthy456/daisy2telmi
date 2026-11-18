"""Checks a generated story against the rules Telmi-Sync and the story teller enforce.

The rules here are read off DantSu/Telmi-Sync (`readStoryMetadata`, `storyFormatDetector`)
and DantSu/Telmi-story-teller (`stories_reader.h`), not guessed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Telmi-Sync's readStoryMetadata deletes the folder if any of these is absent.
REQUIRED_ENTRIES = (
    "audios",
    "images",
    "metadata.json",
    "nodes.json",
    "title.mp3",
    "title.png",
)

_METADATA_KEYS = ("title", "uuid", "image", "version")


def validate_nodes(nodes: dict[str, Any]) -> list[str]:
    """Return human-readable problems with a `nodes.json`; empty means it looks valid."""
    problems: list[str] = []
    stages = nodes.get("stages")
    actions = nodes.get("actions")
    start = nodes.get("startAction")

    if not isinstance(stages, dict) or not stages:
        return ["nodes.json has no stages"]
    if not isinstance(actions, dict) or not actions:
        return ["nodes.json has no actions"]
    if not isinstance(start, dict) or "action" not in start:
        return ["nodes.json has no startAction"]
    if start["action"] not in actions:
        problems.append(f"startAction references unknown action {start['action']!r}")

    def check_transition(where: str, transition: Any) -> None:
        if transition is None:
            return
        if not isinstance(transition, dict):
            problems.append(f"{where} is not an object or null")
            return
        action, index = transition.get("action"), transition.get("index")
        if action not in actions:
            problems.append(f"{where} references unknown action {action!r}")
            return
        targets = actions[action]
        if not isinstance(targets, list) or not targets:
            problems.append(f"action {action!r} is not a non-empty list")
        elif not isinstance(index, int) or not 0 <= index < len(targets):
            problems.append(f"{where} index {index!r} is outside action {action!r}")

    for name, stage in stages.items():
        for key in ("image", "audio", "ok", "home", "control"):
            if key not in stage:
                problems.append(f"{name} is missing {key!r}")

        for key in ("image", "audio"):
            value = stage.get(key)
            if value is not None and not isinstance(value, str):
                problems.append(f"{name}.{key} must be a string or null")

        check_transition(f"{name}.ok", stage.get("ok"))
        check_transition(f"{name}.home", stage.get("home"))

        control = stage.get("control") or {}
        for key in ("ok", "home", "autoplay"):
            if not isinstance(control.get(key), bool):
                problems.append(f"{name}.control.{key} is missing or not a boolean")
    for action, targets in actions.items():
        if not isinstance(targets, list) or not targets:
            problems.append(f"action {action!r} must be a non-empty list")
            continue
        for target in targets:
            if target.get("stage") not in stages:
                problems.append(f"action {action!r} references unknown stage {target.get('stage')!r}")

    reachable: set[str] = set()
    seen_actions: set[str] = set()
    pending = [start["action"]]
    while pending:
        action = pending.pop()
        if action in seen_actions:
            continue
        seen_actions.add(action)
        for target in actions.get(action, []):
            stage_name = target.get("stage")
            if stage_name in stages and stage_name not in reachable:
                reachable.add(stage_name)
                for key in ("ok", "home"):
                    following = (stages[stage_name].get(key) or {}).get("action")
                    if following:
                        pending.append(following)
    if unreachable := set(stages) - reachable:
        problems.append(f"stages unreachable from startAction: {sorted(unreachable)}")

    return problems


def validate_story_zip(zip_path: Path) -> list[str]:
    """Check a zip against ConvertZip.js `findDirectory`, which picks the format
    by counting marker files per zip directory."""
    import zipfile

    problems: list[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        names = [n for n in archive.namelist() if not n.endswith("/")]
        markers: dict[str, int] = {}
        for name in names:
            parent = name.rsplit("/", 1)[0] if "/" in name else ""
            base = name.rsplit("/", 1)[-1]
            if base in ("metadata.json", "nodes.json", "title.mp3", "title.png"):
                markers[parent] = markers.get(parent, 0) + 1
        if not any(count == 4 for count in markers.values()):
            problems.append(
                f"no zip directory holds exactly the four Telmi markers; found {markers}"
            )
        if not any(name.startswith("audios/") or "/audios/" in name for name in names):
            problems.append("the zip has no audios/ entries")
    return problems


def validate_story_dir(story_dir: Path) -> list[str]:
    """Check a whole story folder against what Telmi-Sync requires on import."""
    problems: list[str] = []
    for entry in REQUIRED_ENTRIES:
        if not (story_dir / entry).exists():
            problems.append(f"missing {entry} (Telmi-Sync rejects or deletes the story without it)")

    nodes_path, metadata_path = story_dir / "nodes.json", story_dir / "metadata.json"
    if not nodes_path.is_file() or not metadata_path.is_file():
        return problems

    import json

    nodes = json.loads(nodes_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    problems += validate_nodes(nodes)

    for key in _METADATA_KEYS:
        if key not in metadata:
            problems.append(f"metadata.json is missing {key!r}")

    cover = metadata.get("image")
    if cover and not (story_dir / cover).is_file():
        problems.append(f"metadata.image points at a missing file: {cover}")

    for name, stage in (nodes.get("stages") or {}).items():
        audio, image = stage.get("audio"), stage.get("image")
        if audio and not (story_dir / "audios" / audio).is_file():
            problems.append(f"{name}.audio is missing: audios/{audio}")
        if image and not (story_dir / "images" / image).is_file():
            problems.append(f"{name}.image is missing: images/{image}")

    return problems
