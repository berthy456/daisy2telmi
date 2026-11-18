"""Structural checks for a Telmi `nodes.json`, shared by the unit and integration tests."""

from __future__ import annotations

from typing import Any

RESERVED_ACTIONS = {"backAction"}


def validate_nodes(nodes: dict[str, Any]) -> list[str]:
    """Return a list of human-readable problems; empty means the file looks valid."""
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

    ok_actions: list[str] = []
    for name, stage in stages.items():
        for key in ("ok", "home", "control"):
            if key not in stage:
                problems.append(f"{name} is missing {key!r}")
        if stage.get("audio") != f"{name}.mp3":
            problems.append(f"{name} has audio {stage.get('audio')!r}, expected {name + '.mp3'!r}")

        home = stage.get("home") or {}
        if home.get("action") != "backAction":
            problems.append(f"{name}.home must point at backAction, got {home.get('action')!r}")

        ok = stage.get("ok") or {}
        ok_actions.append(ok.get("action"))

        control = stage.get("control") or {}
        for key in ("ok", "home", "autoplay"):
            if not isinstance(control.get(key), bool):
                problems.append(f"{name}.control.{key} is missing or not a boolean")

    duplicates = {a for a in ok_actions if ok_actions.count(a) > 1 and a not in RESERVED_ACTIONS}
    if duplicates:
        problems.append(f"ok actions are not unique: {sorted(duplicates)}")

    referenced = set(ok_actions) | {home.get("action") for home in (s.get("home") or {} for s in stages.values())}
    for action in referenced - RESERVED_ACTIONS:
        if action not in actions:
            problems.append(f"stage references unknown action {action!r}")

    for action, targets in actions.items():
        for target in targets:
            if target.get("stage") not in stages:
                problems.append(f"action {action!r} references unknown stage {target.get('stage')!r}")

    reachable: set[str] = set()
    pending = [start["action"]]
    seen_actions: set[str] = set()
    while pending:
        action = pending.pop()
        if action in seen_actions or action in RESERVED_ACTIONS:
            continue
        seen_actions.add(action)
        for target in actions.get(action, []):
            stage_name = target.get("stage")
            if stage_name in stages and stage_name not in reachable:
                reachable.add(stage_name)
                following = (stages[stage_name].get("ok") or {}).get("action")
                if following:
                    pending.append(following)
    unreachable = set(stages) - reachable
    if unreachable:
        problems.append(f"stages unreachable from startAction: {sorted(unreachable)}")

    return problems
