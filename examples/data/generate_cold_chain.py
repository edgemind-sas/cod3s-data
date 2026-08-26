"""Generate the telemetry of one refrigerated delivery round.

Deterministic. A van with three compartments does a morning round; at one stop
the chilled compartment is left open too long. Regenerate with:

    uv run python examples/data/generate_cold_chain.py
"""

from __future__ import annotations

import csv
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

SEED = 20260826
DURATION_S = 3600  # a one-hour round, one reading per minute per compartment
STEP_S = 60
START = datetime(2026, 8, 26, 6, 0, 0, tzinfo=UTC)

# Compartment, target temperature, what it carries
COMPARTMENTS = [
    ("surgele_avant", -20.0, "glaces"),
    ("frais_arriere", 4.0, "produits_laitiers"),
    ("surgele_arriere", -20.0, "legumes_surgeles"),
]

# The delivery stop that goes wrong: the chilled compartment door stays open.
INCIDENT_START_S = 2400  # 06:40
INCIDENT_END_S = 2880  # 06:48


def temperature(compartment: str, target: float, t: int, jitter: random.Random) -> float:
    """Compartment temperature, with the compressor cycling around the target."""
    # A refrigeration unit does not hold a line, it cycles: roughly ±0.8 °C
    cycle = 0.8 * math.sin(2 * math.pi * t / 420.0)
    base = target + cycle

    if compartment == "frais_arriere" and INCIDENT_START_S <= t < INCIDENT_END_S:
        # Door open at a delivery stop: the compartment warms towards the
        # street, then the unit pulls it back down once the door is shut.
        elapsed = t - INCIDENT_START_S
        base = target + 14.0 * (1 - math.exp(-elapsed / 200.0))
    elif compartment == "frais_arriere" and t >= INCIDENT_END_S:
        recovery = t - INCIDENT_END_S
        excess = 11.0 * math.exp(-recovery / 240.0)
        base = target + cycle + excess

    return base + jitter.gauss(0, 0.15)


def main() -> None:
    jitter = random.Random(SEED)
    rows = []
    for t in range(0, DURATION_S, STEP_S):
        stamp = (START + timedelta(seconds=t)).isoformat()
        for compartment, target, cargo in COMPARTMENTS:
            value = temperature(compartment, target, t, jitter)
            rows.append((stamp, compartment, f"{value:.2f}", cargo))

    out = Path(__file__).parent / "cold_chain_round.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "compartment", "celsius", "cargo"])
        writer.writerows(rows)

    print(f"{out} — {len(rows)} readings over {DURATION_S // 60} minutes")


if __name__ == "__main__":
    main()
