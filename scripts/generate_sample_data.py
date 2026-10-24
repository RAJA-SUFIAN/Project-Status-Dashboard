"""Generate a mock task list for the "Riyadh Smart Parking App" project.

Usage:
    python scripts/generate_sample_data.py [--as-of 2026-10-24] [--seed 42]

The output is deterministic for a given seed and as-of date, so the sample
dashboard looks the same on every machine.
"""

from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "riyadh_smart_parking_tasks.csv"

PROJECT_START = date(2026, 5, 3)

OWNERS = [
    "Ahmed Al-Qahtani",
    "Sara Al-Otaibi",
    "Faisal Al-Harbi",
    "Noura Al-Shehri",
    "Omar Al-Ghamdi",
    "Lina Al-Zahrani",
    "Khalid Al-Mutairi",
    "Reem Al-Dosari",
]

# (phase, [(task name, duration in days, planned budget SAR)]); the last task of
# every phase is the phase milestone.
PHASES = [
    ("1. Discovery & Planning", [
        ("Stakeholder workshops with Riyadh municipality", 10, 45_000),
        ("Parking demand study (Olaya & King Fahd Rd)", 14, 80_000),
        ("Requirements specification", 12, 40_000),
        ("Vendor selection for IoT sensors", 10, 25_000),
        ("Milestone: Project charter signed off", 3, 10_000),
    ]),
    ("2. UX / UI Design", [
        ("User personas & journey maps", 8, 30_000),
        ("Arabic / English bilingual UI kit", 12, 55_000),
        ("High-fidelity mobile mockups", 14, 60_000),
        ("Usability testing round 1", 7, 35_000),
        ("Milestone: Design freeze", 2, 8_000),
    ]),
    ("3. Backend & APIs", [
        ("Cloud architecture & landing zone", 10, 90_000),
        ("Parking availability API", 18, 120_000),
        ("Booking & reservation service", 20, 140_000),
        ("Admin portal for operators", 16, 95_000),
        ("Absher / Nafath SSO integration", 12, 70_000),
        ("Milestone: Backend MVP ready", 2, 10_000),
    ]),
    ("4. IoT Sensor Integration", [
        ("Pilot sensor install (500 bays)", 21, 260_000),
        ("Sensor gateway & MQTT pipeline", 14, 85_000),
        ("Real-time occupancy engine", 16, 110_000),
        ("Sensor calibration in summer heat", 10, 45_000),
        ("Milestone: Live occupancy feed", 2, 10_000),
    ]),
    ("5. Mobile App", [
        ("iOS app build", 30, 180_000),
        ("Android app build", 30, 175_000),
        ("Map & navigation to free bay", 18, 90_000),
        ("Push notifications & reminders", 10, 40_000),
        ("Milestone: Beta app on TestFlight / Play", 3, 12_000),
    ]),
    ("6. Payments", [
        ("mada & Apple Pay integration", 14, 85_000),
        ("SADAD bill payment for fines", 12, 60_000),
        ("ZATCA e-invoicing compliance", 10, 55_000),
        ("Milestone: Payments certified", 2, 10_000),
    ]),
    ("7. Testing & QA", [
        ("Automated regression suite", 14, 70_000),
        ("Load testing (100k concurrent users)", 8, 50_000),
        ("Security & penetration testing", 10, 95_000),
        ("User acceptance testing with operators", 12, 45_000),
        ("Milestone: Go-live readiness review", 2, 10_000),
    ]),
    ("8. Launch", [
        ("Marketing campaign (Riyadh Season)", 21, 150_000),
        ("App store submission", 5, 8_000),
        ("Operator training", 7, 30_000),
        ("Hypercare support", 21, 60_000),
        ("Milestone: Public launch", 1, 15_000),
    ]),
]

PRIORITIES = ["High", "Medium", "Low"]


def build_tasks(as_of: date, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    phase_start = PROJECT_START
    task_no = 1

    for phase, tasks in PHASES:
        cursor = phase_start
        phase_end = phase_start
        for name, duration, budget in tasks:
            is_milestone = name.startswith("Milestone:")
            # Tasks inside a phase overlap a little; milestones close the phase.
            start = phase_end if is_milestone else cursor
            end = start + timedelta(days=duration - 1)
            if not is_milestone:
                cursor = start + timedelta(days=max(2, duration // 2 + rng.randint(-2, 3)))
            phase_end = max(phase_end, end + timedelta(days=1))

            pct = _percent_complete(start, end, as_of, rng)
            actual = _actual_cost(budget, pct, rng)

            rows.append({
                "task_id": f"RSP-{task_no:03d}",
                "task_name": name.replace("Milestone: ", ""),
                "phase": phase,
                "milestone": is_milestone,
                "owner": rng.choice(OWNERS),
                "priority": "High" if is_milestone else rng.choices(PRIORITIES, [3, 5, 2])[0],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "percent_complete": pct,
                "budget_planned_sar": budget,
                "budget_actual_sar": actual,
            })
            task_no += 1

        # Phases overlap by about a week to mimic a real delivery plan.
        phase_start = phase_end - timedelta(days=rng.randint(5, 10))

    return pd.DataFrame(rows)


def _percent_complete(start: date, end: date, as_of: date, rng: random.Random) -> int:
    if as_of < start:
        return 0
    if as_of > end:
        # Most finished-on-paper tasks are done, a few are slipping.
        return 100 if rng.random() < 0.75 else rng.choice([60, 70, 80, 85, 90, 95])
    elapsed = (as_of - start).days + 1
    expected = elapsed / ((end - start).days + 1) * 100
    return int(max(0, min(99, round(expected + rng.uniform(-30, 15), -1))))


def _actual_cost(budget: int, pct: int, rng: random.Random) -> int:
    if pct == 0:
        return 0
    # Cost efficiency varies: some tasks run lean, a few overrun badly.
    factor = rng.choices([rng.uniform(0.8, 1.0), rng.uniform(1.0, 1.15), rng.uniform(1.2, 1.5)],
                         [4, 4, 2])[0]
    return int(round(budget * pct / 100 * factor, -2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--as-of", default="2026-10-24", help="Status date (YYYY-MM-DD)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    df = build_tasks(date.fromisoformat(args.as_of), args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Wrote {len(df)} tasks to {args.output}")


if __name__ == "__main__":
    main()
