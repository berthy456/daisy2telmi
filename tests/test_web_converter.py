"""The browser converter must produce packs the Python validator accepts.

Runs the same ES modules the page loads under Node, then checks the result with
the validator that mirrors Telmi-Sync's import rules.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from nodes_validator import validate_story_dir, validate_story_zip

ROOT = Path(__file__).resolve().parents[1]
node = shutil.which("node")
requires_node = pytest.mark.skipif(node is None, reason="node not installed")
requires_pack = pytest.mark.skipif(not (ROOT / "gon-ruby-mp3.zip").exists(), reason="test pack missing")

CONVERT_SCRIPT = """
import {readFile, writeFile} from 'node:fs/promises';
import {readZip} from './web/zip.js';
import {buildStoryZip} from './web/convert.js';
const silent = new Uint8Array(await readFile('web/silence.mp3'));
const entries = await readZip(new Uint8Array(await readFile(process.argv[1])));
const story = await buildStoryZip(entries, silent);
await writeFile(process.argv[2], story.zip);
"""


@requires_node
@requires_pack
def test_the_browser_converter_output_is_a_valid_story(tmp_path: Path) -> None:
    out_zip = tmp_path / "story.zip"
    subprocess.run(
        [node, "--input-type=module", "-e", CONVERT_SCRIPT, str(ROOT / "gon-ruby-mp3.zip"), str(out_zip)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )

    assert validate_story_zip(out_zip) == []
    with zipfile.ZipFile(out_zip) as archive:
        archive.extractall(tmp_path)
    story_dir = next(entry for entry in tmp_path.iterdir() if entry.is_dir())
    assert validate_story_dir(story_dir) == []

    nodes = __import__("json").loads((story_dir / "nodes.json").read_text(encoding="utf-8"))
    assert [name for name in nodes["stages"] if name.startswith("s")] == [f"s{k}" for k in range(6)]
