"""Every example pipeline still builds against the current component registry.

`cod3s-data validate` checks a configuration against the schema. It does not
check that the `type:` names still exist, or that the parameters underneath
them are still accepted — a renamed component or a dropped parameter passes
validation and fails when someone actually runs the example.

Building each one through the real `ComponentFactory` catches that, which is
why these tests instantiate rather than merely load. Construction is cheap:
no source reads its file before `produce()`, and no destination opens its own
before the first write.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cod3s_data.config.loaders import load_yaml
from cod3s_data.framework import Framework

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"
EXAMPLE_PIPELINES = sorted(EXAMPLES_DIR.glob("*.yaml"))


def test_examples_are_discovered() -> None:
    """Guard the glob itself: matching nothing would make every test below vacuous."""
    assert EXAMPLE_PIPELINES, f"no pipeline found in {EXAMPLES_DIR}"


@pytest.mark.parametrize("path", EXAMPLE_PIPELINES, ids=lambda p: p.stem)
def test_example_builds_through_the_factory(path: Path) -> None:
    config = load_yaml(path)
    framework = Framework(config, observatory=False)

    framework._create_components()

    assert framework.sources, f"{path.name} declares no source"
    assert framework.destinations, f"{path.name} declares no destination"


@pytest.mark.parametrize("path", EXAMPLE_PIPELINES, ids=lambda p: p.stem)
def test_example_input_files_exist(path: Path) -> None:
    """A dataset renamed or removed breaks an example only when it is run.

    Sources only: a destination's `file_path` is an output, and one example
    points at a mount that is deliberately absent in order to demonstrate the
    dead-letter channel.
    """
    config = load_yaml(path)

    for source in config.sources:
        declared = source.params.get("file_path")
        if declared is None:
            continue
        resolved = Path(declared)
        if not resolved.is_absolute():
            resolved = REPO_ROOT / resolved
        assert resolved.is_file(), f"{path.name} reads {declared}, which does not exist"
