"""Settings loaded from environment variables / the .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    project_name: str
    data_path: Path
    report_date: date
    currency: str
    # Overall RAG thresholds on the CPI / SPI performance indices.
    green_threshold: float
    red_threshold: float
    # Task-level cost overrun (actual vs earned value) that turns a task amber / red.
    amber_overrun: float
    red_overrun: float


def load_settings() -> Settings:
    raw_date = os.getenv("REPORT_DATE", "").strip()
    try:
        report_date = date.fromisoformat(raw_date) if raw_date else date.today()
    except ValueError:
        report_date = date.today()

    data_path = Path(os.getenv("DATA_PATH", "data/riyadh_smart_parking_tasks.csv"))
    if not data_path.is_absolute():
        data_path = ROOT / data_path

    return Settings(
        project_name=os.getenv("PROJECT_NAME", "Riyadh Smart Parking App"),
        data_path=data_path,
        report_date=report_date,
        currency=os.getenv("CURRENCY", "SAR"),
        green_threshold=_float("RAG_GREEN_THRESHOLD", 0.95),
        red_threshold=_float("RAG_RED_THRESHOLD", 0.85),
        amber_overrun=_float("TASK_AMBER_OVERRUN", 0.05),
        red_overrun=_float("TASK_RED_OVERRUN", 0.15),
    )
