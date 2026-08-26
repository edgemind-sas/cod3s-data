"""Generate the telemetry of one 3D print job, as a scripted incident.

Deterministic: same numbers on every run. The point of the file is not the
values but the story they tell — a print that heats up, runs well, degrades,
gets caught, and recovers. Regenerate with:

    uv run python examples/data/generate_print_job.py
"""

from __future__ import annotations

import csv
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

SEED = 20260826
DURATION_S = 1200  # 20 minutes of print, one reading per second per sensor
START = datetime(2026, 8, 26, 9, 0, 0, tzinfo=UTC)

# Job setpoints (PLA), matching examples/jobs/PLA.yaml
EXTRUDER_TARGET = 210.0
BED_TARGET = 60.0


def extruder_temperature(t: int, jitter: random.Random) -> float:
    """Nozzle temperature over the job.

    0-90s     heating from room temperature to the setpoint
    90-600s   printing, stable
    600-780s  a partial clog: heat is drawn away faster than it is replaced
    780-870s  the operator purges the nozzle, temperature climbs back
    870-1200s stable again to the end of the job
    """
    if t < 90:
        # Exponential approach, the way a PID-controlled heater actually behaves
        base = 25.0 + (EXTRUDER_TARGET - 25.0) * (1 - math.exp(-t / 22.0))
    elif t < 600:
        base = EXTRUDER_TARGET
    elif t < 780:
        base = EXTRUDER_TARGET - 13.0 * (t - 600) / 180.0  # drifts down to 197
    elif t < 870:
        base = 197.0 + 13.0 * (t - 780) / 90.0  # purged, climbs back
    else:
        base = EXTRUDER_TARGET
    # A thermocouple on a moving hotend is genuinely this noisy. It matters:
    # the raw signal crosses the alarm threshold several times on the way down,
    # which is what makes the smoothed channel worth having.
    return base + jitter.gauss(0, 1.8)


def bed_temperature(t: int, jitter: random.Random) -> float:
    """Bed temperature over the job.

    Stable except between 700s and 760s, when the workshop door is opened and
    a draft cools the unenclosed bed below tolerance.
    """
    if t < 60:
        base = 22.0 + (BED_TARGET - 22.0) * (1 - math.exp(-t / 18.0))
    elif 700 <= t < 760:
        base = BED_TARGET - 4.5 * math.sin(math.pi * (t - 700) / 60.0)
    else:
        base = BED_TARGET
    return base + jitter.gauss(0, 0.5)


def main() -> None:
    jitter = random.Random(SEED)
    rows = []
    for t in range(DURATION_S):
        stamp = (START + timedelta(seconds=t)).isoformat()
        rows.append((stamp, "extruder", f"{extruder_temperature(t, jitter):.2f}", "nozzle"))
        rows.append((stamp, "bed", f"{bed_temperature(t, jitter):.2f}", "plate"))

    out = Path(__file__).parent / "print_job_pla.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "sensor", "celsius", "location"])
        writer.writerows(rows)

    print(f"{out} — {len(rows)} readings over {DURATION_S}s")


if __name__ == "__main__":
    main()
