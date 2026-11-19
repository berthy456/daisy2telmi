"""Checks a STUdio archive the way a Lunii's tools read it.

Port of `StudioStory` in Lunii.QT's `pkg/api/stories.py`, including the `ni`,
`ri`, `si` and `li` index it builds from `story.json` and what the device then
expects to find. Used by the tests, never shipped.
"""

from __future__ import annotations

import json
import re
import zipfile

NODE_SIZE = 0x2C
NI_HEADER_SIZE = 0x200
ASSET_NAME = re.compile(r"^[0-9A-F]{8}\.(png|mp3|jpg|jpeg|bmp|gif|webp|ogg)$")


def index_story(story: dict) -> dict:
    """The tables Lunii.QT builds while loading `story.json`."""
    snodes = story.get("stageNodes") or []
    anodes = story.get("actionNodes") or []

    ri: dict[str, int] = {}
    si: dict[str, int] = {}
    for node in snodes:
        for table, key in ((ri, "image"), (si, "audio")):
            name = node.get(key)
            if name and name not in table:
                table[name] = len(table)

    li: list[int] = []
    absolute = 0
    for anode in anodes:
        anode["global_index"] = absolute
        absolute += len(anode.get("options") or [])
        for option in anode.get("options") or []:
            li.append(next((i for i, n in enumerate(snodes) if n.get("uuid") == option), -1))

    return {"snodes": snodes, "anodes": anodes, "ri": ri, "si": si, "li": li}


def ni_bytes(story: dict) -> bytes:
    """The `ni` file the device reads: a 0x200 header then one 0x2C node each."""
    tables = index_story(story)
    snodes, ri, si = tables["snodes"], tables["ri"], tables["si"]

    header = b""
    header += int(str(story.get("format", "v1"))[1:]).to_bytes(2, "little")
    header += int(story.get("version") or 0).to_bytes(2, "little")
    header += NI_HEADER_SIZE.to_bytes(4, "little")
    header += NODE_SIZE.to_bytes(4, "little")
    header += len(snodes).to_bytes(4, "little")
    header += len(ri).to_bytes(4, "little")
    header += len(si).to_bytes(4, "little")
    header += b"\x01"
    header += b"\x00" * (NI_HEADER_SIZE - len(header))

    def signed(value: int) -> bytes:
        return int(value).to_bytes(4, "little", signed=True)

    def move(node: dict, field: str) -> bytes:
        transition = node.get(field)
        if not transition:
            return b"\xff\xff\xff\xff" * 3
        anode = next((a for a in tables["anodes"] if a.get("id") == transition["actionNode"]), None)
        return signed(anode["global_index"]) + signed(len(anode["options"])) + signed(transition["optionIndex"])

    body = b""
    for node in snodes:
        controls = node["controlSettings"]
        current = signed(ri.get(node.get("image"), -1))
        current += signed(si.get(node.get("audio"), -1))
        current += move(node, "okTransition")
        current += move(node, "homeTransition")
        for key in ("wheel", "ok", "home", "pause", "autoplay"):
            current += int(bool(controls.get(key))).to_bytes(2, "little")
        current += b"\x00\x00"
        if len(current) > NODE_SIZE:
            raise ValueError(f"a node is {len(current)} bytes, over the {NODE_SIZE} the device allows")
        body += current + b"\xaa" * (NODE_SIZE - len(current))
    return header + body


def validate_studio_zip(path) -> list[str]:
    """Every way a STUdio archive can fail to be a story a Lunii will take."""
    problems: list[str] = []
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"not a zip archive: {exc}"]

    with archive:
        names = archive.namelist()
        if "story.json" not in names:
            return ["story.json missing from the archive"]
        try:
            story = json.loads(archive.read("story.json").decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            return [f"story.json does not parse: {exc}"]

        inside = set(names)
        tables = index_story(story)
        snodes = tables["snodes"]
        if not snodes:
            problems.append("story.json has no stageNodes")
        elif snodes[0].get("type") != "cover":
            problems.append("the first stageNode is not the cover")

        for table, folder, key in ((tables["ri"], "assets", "image"), (tables["si"], "assets", "audio")):
            for name in table:
                asset = f"{folder}/{name}"
                if asset not in inside:
                    problems.append(f"{key} is missing from the archive: {asset}")
                elif not ASSET_NAME.match(name):
                    problems.append(f"{key} is not named like a STUdio asset: {name}")

        known_actions = {a.get("id") for a in tables["anodes"]}
        for node in snodes:
            label = node.get("name") or node.get("uuid")
            for field in ("okTransition", "homeTransition"):
                transition = node.get(field)
                if transition and transition.get("actionNode") not in known_actions:
                    problems.append(f"{label}.{field} points at an unknown action {transition.get('actionNode')}")
                if transition and not isinstance(transition.get("optionIndex"), int):
                    problems.append(f"{label}.{field} has no optionIndex")
            controls = node.get("controlSettings") or {}
            missing = {"wheel", "ok", "home", "pause", "autoplay"} - set(controls)
            if missing:
                problems.append(f"{label} has no controlSettings for {sorted(missing)}")
            # A lit OK with nothing behind it stops the device with an SD card error.
            if controls.get("ok") and not node.get("okTransition"):
                problems.append(f"{label} lights OK with no transition behind it")

        for anode in tables["anodes"]:
            if not anode.get("options"):
                problems.append(f"action {anode.get('id')} has no option")
            if any(index < 0 for index in _option_indexes(anode, snodes)):
                problems.append(f"action {anode.get('id')} points at a stage that is not in the story")

        start = snodes[0].get("okTransition") if snodes else None
        if not start:
            problems.append("the cover has no okTransition, so the story cannot be started")
        elif start.get("actionNode") not in known_actions:
            problems.append(f"the cover starts an unknown action {start.get('actionNode')}")

        ni = ni_bytes(story)
        if len(ni) != NI_HEADER_SIZE + NODE_SIZE * len(snodes):
            problems.append(f"ni is {len(ni)} bytes, not header plus {len(snodes)} node(s)")
        if len(tables["li"]) < 8 // 4:
            problems.append("li is shorter than the device pads it to")

    return problems


def _option_indexes(anode: dict, snodes: list[dict]) -> list[int]:
    return [next((i for i, n in enumerate(snodes) if n.get("uuid") == option), -1) for option in anode.get("options") or []]
