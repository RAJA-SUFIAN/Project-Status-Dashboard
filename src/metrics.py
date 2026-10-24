"""Load the task CSV and derive schedule, cost and RAG metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import IO

import numpy as np
import pandas as pd

from src.config import Settings

REQUIRED_COLUMNS = {
    "task_id", "task_name", "phase", "milestone", "owner", "start_date", "end_date",
    "percent_complete", "budget_planned_sar", "budget_actual_sar",
}

RAG_ORDER = ["Red", "Amber", "Green"]


class DataError(ValueError):
    """Raised when an uploaded CSV does not match the expected schema."""


def load_tasks(source: str | IO) -> pd.DataFrame:
    df = pd.read_csv(source)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise DataError(f"CSV is missing columns: {', '.join(sorted(missing))}")

    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"])
    df["milestone"] = df["milestone"].astype(str).str.lower().isin(["true", "1", "yes"])
    df["percent_complete"] = df["percent_complete"].clip(0, 100)
    if "priority" not in df.columns:
        df["priority"] = "Medium"
    return df


def enrich(df: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Add earned-value columns, task status and a task-level RAG."""
    df = df.copy()
    today = pd.Timestamp(settings.report_date)

    duration = (df["end_date"] - df["start_date"]).dt.days + 1
    elapsed = ((today - df["start_date"]).dt.days + 1).clip(lower=0)
    df["expected_pct"] = (elapsed / duration * 100).clip(0, 100).round(0)

    df["planned_value"] = df["budget_planned_sar"] * df["expected_pct"] / 100
    df["earned_value"] = df["budget_planned_sar"] * df["percent_complete"] / 100
    df["cost_variance"] = df["earned_value"] - df["budget_actual_sar"]
    df["budget_variance"] = df["budget_actual_sar"] - df["budget_planned_sar"]

    done = df["percent_complete"] >= 100
    df["overdue"] = (df["end_date"] < today) & ~done
    df["days_overdue"] = np.where(df["overdue"], (today - df["end_date"]).dt.days, 0)

    df["status"] = np.select(
        [done, df["overdue"], df["start_date"] > today],
        ["Done", "Overdue", "Not started"],
        default="In progress",
    )

    overrun = np.where(
        df["earned_value"] > 0,
        df["budget_actual_sar"] / df["earned_value"].replace(0, np.nan) - 1,
        0,
    )
    df["cost_overrun_pct"] = np.nan_to_num(overrun) * 100
    behind = df["expected_pct"] - df["percent_complete"]

    df["rag"] = np.select(
        [
            df["overdue"] | (overrun > settings.red_overrun) | (behind > 30),
            (overrun > settings.amber_overrun) | (behind > 15),
        ],
        ["Red", "Amber"],
        default="Green",
    )
    return df


@dataclass(frozen=True)
class Summary:
    tasks: int
    done: int
    overdue: int
    pct_complete: float
    expected_pct: float
    budget_planned: float
    budget_actual: float
    earned_value: float
    planned_value: float
    cpi: float
    spi: float
    eac: float
    rag: str
    rag_reason: str


def summarise(df: pd.DataFrame, settings: Settings) -> Summary:
    planned = df["budget_planned_sar"].sum()
    actual = df["budget_actual_sar"].sum()
    ev = df["earned_value"].sum()
    pv = df["planned_value"].sum()

    cpi = ev / actual if actual else 1.0
    spi = ev / pv if pv else 1.0
    eac = planned / cpi if cpi else planned
    rag, reason = overall_rag(cpi, spi, int(df["overdue"].sum()), len(df), settings)

    return Summary(
        tasks=len(df),
        done=int((df["status"] == "Done").sum()),
        overdue=int(df["overdue"].sum()),
        pct_complete=ev / planned * 100 if planned else 0.0,
        expected_pct=pv / planned * 100 if planned else 0.0,
        budget_planned=planned,
        budget_actual=actual,
        earned_value=ev,
        planned_value=pv,
        cpi=cpi,
        spi=spi,
        eac=eac,
        rag=rag,
        rag_reason=reason,
    )


def overall_rag(cpi: float, spi: float, overdue: int, total: int,
                settings: Settings) -> tuple[str, str]:
    worst = min(cpi, spi)
    overdue_share = overdue / total if total else 0
    driver = "cost (CPI)" if cpi <= spi else "schedule (SPI)"

    if worst < settings.red_threshold or overdue_share > 0.2:
        why = f"{driver} at {worst:.2f}" if worst < settings.red_threshold \
            else f"{overdue} of {total} tasks overdue"
        return "Red", f"Critical: {why}"
    if worst < settings.green_threshold or overdue > 0:
        return "Amber", f"Watch: {driver} at {worst:.2f}, {overdue} task(s) overdue"
    return "Green", f"On track: CPI {cpi:.2f}, SPI {spi:.2f}"


def phase_summary(df: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    rows = []
    for phase, grp in df.groupby("phase", sort=True):
        s = summarise(grp, settings)
        rows.append({
            "Phase": phase,
            "Start": grp["start_date"].min().date(),
            "End": grp["end_date"].max().date(),
            "Tasks": s.tasks,
            "Done": s.done,
            "Overdue": s.overdue,
            "% Complete": round(s.pct_complete, 1),
            "Planned": s.budget_planned,
            "Earned": s.earned_value,
            "Actual": s.budget_actual,
            # Earned minus actual: negative means the work done so far cost more
            # than budgeted, which raw planned-vs-actual hides for unfinished phases.
            "Cost variance": s.earned_value - s.budget_actual,
            "CPI": round(s.cpi, 2),
            "SPI": round(s.spi, 2),
            "RAG": s.rag,
        })
    return pd.DataFrame(rows)


def report_date_label(d: date) -> str:
    return d.strftime("%d %b %Y")
