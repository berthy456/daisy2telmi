"""Checks the validator against a real published Telmi story, when one is on disk.

The sample is not committed; point TELMI_SAMPLE at a local copy to run these.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from daisy2telmi.telmi_builder import story_dir_name
from nodes_validator import validate_nodes, validate_story_dir

SAMPLE = Path(os.environ.get("TELMI_SAMPLE", "~/daisy/_00_La reine des pirates_fffffd-19d14f92f57")).expanduser()
requires_sample = pytest.mark.skipif(not SAMPLE.is_dir(), reason=f"published sample missing: {SAMPLE}")


@requires_sample
def test_the_published_pack_passes_the_validator() -> None:
    assert validate_story_dir(SAMPLE) == []


@requires_sample
def test_the_published_pack_folder_name_is_reproducible() -> None:
    metadata = json.loads((SAMPLE / "metadata.json").read_text(encoding="utf-8"))
    assert story_dir_name(
        metadata["title"], metadata["uuid"], metadata.get("age", 0), metadata.get("category", "")
    ) == SAMPLE.name


@requires_sample
def test_the_published_pack_uses_the_same_graph_shape() -> None:
    nodes = json.loads((SAMPLE / "nodes.json").read_text(encoding="utf-8"))
    assert validate_nodes(nodes) == []
    assert "m" in nodes["actions"] or "a0" in nodes["actions"]
