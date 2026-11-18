"""Keep the suite off the developer's real config file."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_config(tmp_path_factory):
    home = tmp_path_factory.mktemp("xdg-config")
    patch = pytest.MonkeyPatch()
    patch.setenv("XDG_CONFIG_HOME", str(home))
    patch.setenv("APPDATA", str(home))
    yield home
    patch.undo()
