"""The two scenario demos still produce the numbers their README advertises.

`examples/README.md` presents "seventy alarms against eight" as the lesson of
`print_job_incident.yaml`: the point of the demo *is* the gap between the raw
signal and the smoothed one. `tests/unit/test_examples.py` only checks that
every example still builds, so a change to how `moving_average` windows or how
`relative_alarm` transitions would leave both demos running and the README
quietly wrong.

Run through the CLI rather than assembling the pipelines in Python with a
`collect` destination. The Python route is faster and less brittle, but the
numbers being defended are counts of console lines produced by the command the
README tells a reader to type; only running that command tests it. What is
asserted here is therefore the reader's path end to end — configuration,
factory, replay, transformations and console formatting.

The data is deterministic — seeded generators, versioned CSVs — so the counts
are too. The cost is real: about twenty seconds for the print job and thirty
for the cold chain, the two replays being accelerated 60x and 120x.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Generous next to the ~20 s and ~30 s the replays take locally: a shared runner
# is slower, and a timeout here has to read as "the pipeline hung", not "the CI
# machine was busy".
RUN_TIMEOUT_S = 300


def run_example(name: str) -> str:
    """Replay one example pipeline to completion and return its stdout."""
    completed = subprocess.run(
        [sys.executable, "-m", "cod3s_data.cli", "run", f"examples/{name}.yaml"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_S,
    )
    assert completed.returncode == 0, (
        f"examples/{name}.yaml exited {completed.returncode}\n{completed.stderr}"
    )
    return completed.stdout


@pytest.fixture(scope="module")
def print_job_output() -> str:
    return run_example("print_job_incident")


@pytest.fixture(scope="module")
def cold_chain_output() -> str:
    return run_example("cold_chain_round")


def test_print_job_incident_alarm_counts(print_job_output: str) -> None:
    """Seventy raw alarms against eight smoothed — the gap the demo exists for.

    These two counts are the ones `examples/README.md` prints as shell
    commands; the substrings are the ones it greps for.
    """
    raw = print_job_output.count("'alarm_type': 'brut'")
    smoothed = print_job_output.count("'alarm_type': 'lisse'")

    assert (raw, smoothed) == (70, 8), (
        f"examples/README.md advertises 70 raw alarms against 8 smoothed; "
        f"this run produced {raw} against {smoothed}. Either the demo changed "
        f"meaning or a transformation did — update both, or neither."
    )


def test_cold_chain_only_the_chilled_compartment_alarms(cold_chain_output: str) -> None:
    """One alarm transformation, three compartments, state tracked per key.

    The README's claim is that the two frozen compartments never leave their
    range: the per-key state is what makes a single `relative_alarm` able to
    cover all three, and a regression there would show up as one of them
    firing.
    """
    alarms = [line for line in cold_chain_output.splitlines() if "'alarm_type'" in line]

    assert len(alarms) == 2, f"expected an ACTIVE then a CLEARED, got {len(alarms)}"
    assert "'status': 'ACTIVE'" in alarms[0]
    assert "'status': 'CLEARED'" in alarms[1]
    assert all("frais_arriere" in line for line in alarms)
    assert not any("surgele" in line for line in alarms), (
        "a frozen compartment left its range; the demo says neither ever does"
    )


def test_cold_chain_alarms_are_dead_lettered_with_a_reason(cold_chain_output: str) -> None:
    """Both alarms reach the dead-letter channel carrying why they got there.

    The compliance log points at a mount that does not exist, which is the
    second thing the demo shows. The `dlq_*` tags are the payload of #14: a
    message arriving on the dead-letter channel without them is
    indistinguishable from ordinary traffic.
    """
    rejected = [line for line in cold_chain_output.splitlines() if '"dlq_destination"' in line]

    assert len(rejected) == 2, f"expected both alarms rejected, got {len(rejected)}"
    for line in rejected:
        assert '"dlq_destination":"FileDestination"' in line
        assert '"dlq_error_type":"FileNotFoundError"' in line
        assert '"dlq_attempts":"2"' in line
        # The tags are additive: what the message carried before the failure is
        # still readable by whatever consumes the dead-letter channel.
        assert '"cargo":' in line
