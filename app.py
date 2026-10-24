"""Project Status Dashboard - Streamlit entry point.

Run with:  streamlit run app.py
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import streamlit as st

from src import charts
from src.config import load_settings
from src.metrics import (
    RAG_ORDER, DataError, enrich, load_tasks, phase_summary, report_date_label, summarise,
)

st.set_page_config(page_title="Project Status Dashboard", page_icon="📊", layout="wide")

RAG_BADGE = {"Green": "🟢", "Amber": "🟠", "Red": "🔴"}


@st.cache_data(show_spinner=False)
def read_csv(source) -> pd.DataFrame:
    return load_tasks(source)


def money(value: float, currency: str) -> str:
    if abs(value) >= 1_000_000:
        return f"{currency} {value / 1_000_000:,.2f}M"
    return f"{currency} {value / 1_000:,.0f}K"


def rag_style(value: str) -> str:
    color = charts.RAG_COLORS.get(value)
    return f"background-color: {color}; color: white; font-weight: 600" if color else ""


def overdue_style(days: int) -> str:
    # Fade from light to strong red as a task slips further past its due date.
    alpha = min(1.0, 0.25 + days / 30)
    return f"background-color: rgba(214, 69, 69, {alpha:.2f}); color: white; font-weight: 600"


settings = load_settings()

# ---------------------------------------------------------------- sidebar ---
with st.sidebar:
    st.header("⚙️ Settings")
    uploaded = st.file_uploader("Upload your own task CSV", type="csv",
                                help="Same columns as the sample file in data/.")
    report_date = st.date_input("Status date", value=settings.report_date,
                                help="Default comes from REPORT_DATE in .env")
    settings = replace(settings, report_date=report_date)

try:
    raw = read_csv(uploaded if uploaded is not None else str(settings.data_path))
except FileNotFoundError:
    st.error(f"Data file not found: `{settings.data_path}`. "
             "Run `python scripts/generate_sample_data.py` first.")
    st.stop()
except DataError as exc:
    st.error(str(exc))
    st.stop()

tasks = enrich(raw, settings)

with st.sidebar:
    st.subheader("Filters")
    phases = st.multiselect("Phase", sorted(tasks["phase"].unique()))
    owners = st.multiselect("Owner", sorted(tasks["owner"].unique()))
    statuses = st.multiselect("Status", list(charts.STATUS_COLORS))
    rags = st.multiselect("RAG", RAG_ORDER)

filtered = tasks
for column, chosen in (("phase", phases), ("owner", owners), ("status", statuses),
                       ("rag", rags)):
    if chosen:
        filtered = filtered[filtered[column].isin(chosen)]

if filtered.empty:
    st.warning("No tasks match the selected filters.")
    st.stop()

summary = summarise(filtered, settings)
phase_df = phase_summary(filtered, settings)

with st.sidebar:
    st.divider()
    st.download_button("⬇️ Download filtered tasks (CSV)",
                       filtered.to_csv(index=False).encode("utf-8"),
                       file_name="project_tasks_filtered.csv", mime="text/csv",
                       width="stretch")

# ----------------------------------------------------------------- header ---
title_col, rag_col = st.columns([3, 1])
with title_col:
    st.title(f"📊 {settings.project_name}")
    st.caption(f"Status as of **{report_date_label(settings.report_date)}** · "
               f"{summary.tasks} tasks · {filtered['owner'].nunique()} owners")
with rag_col:
    color = charts.RAG_COLORS[summary.rag]
    st.markdown(
        f"""<div style="background:{color};color:white;border-radius:12px;
        padding:14px 18px;text-align:center;margin-top:12px">
        <div style="font-size:13px;opacity:.9">OVERALL STATUS</div>
        <div style="font-size:30px;font-weight:700">{summary.rag.upper()}</div>
        <div style="font-size:12px">{summary.rag_reason}</div></div>""",
        unsafe_allow_html=True,
    )

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Progress", f"{summary.pct_complete:.0f}%",
          f"{summary.pct_complete - summary.expected_pct:+.0f} pts vs plan")
k2.metric("Tasks done", f"{summary.done} / {summary.tasks}")
k3.metric("Overdue", summary.overdue, delta_color="inverse",
          delta=f"{summary.overdue / summary.tasks:.0%} of tasks" if summary.overdue else None)
k4.metric(f"Spent ({settings.currency})", money(summary.budget_actual, "").strip(),
          help=f"Total budget {money(summary.budget_planned, settings.currency)} · "
               f"{summary.budget_actual / summary.budget_planned:.0%} used")
k5.metric("CPI (cost)", f"{summary.cpi:.2f}", f"{summary.cpi - 1:+.2f}")
k6.metric("SPI (schedule)", f"{summary.spi:.2f}", f"{summary.spi - 1:+.2f}")

overrun = summary.eac - summary.budget_planned
if overrun > 0:
    st.info(f"📈 At the current cost efficiency the project is forecast to finish at "
            f"**{money(summary.eac, settings.currency)}**, "
            f"**{money(overrun, settings.currency)}** over budget.")

# ------------------------------------------------------------------- tabs ---
# ?tab=budget etc. opens a tab directly, so links to a specific view can be shared.
TABS = {"overview": "🏠 Overview", "timeline": "🗓️ Milestone timeline", "budget": "💰 Budget",
        "overdue": "⏰ Overdue tasks", "team": "👥 Team", "tasks": "📋 All tasks"}
overview, timeline, budget, overdue_tab, team, all_tasks = st.tabs(
    list(TABS.values()), default=TABS.get(st.query_params.get("tab", ""), TABS["overview"]))

with overview:
    left, right = st.columns([2, 1])
    with left:
        st.subheader("RAG status by phase")
        st.dataframe(
            phase_df.style.map(rag_style, subset=["RAG"]),
            hide_index=True, width="stretch",
            column_config={
                "% Complete": st.column_config.ProgressColumn(
                    "% Complete", min_value=0, max_value=100, format="%.0f%%"),
                "Planned": st.column_config.NumberColumn(format="localized"),
                "Earned": st.column_config.NumberColumn(format="localized"),
                "Actual": st.column_config.NumberColumn(format="localized"),
                "Cost variance": st.column_config.NumberColumn(
                    format="localized", help="Earned value minus actual cost. "
                                             "Negative = over budget for the work done."),
            },
        )
    with right:
        st.subheader("Task status")
        st.plotly_chart(charts.status_donut(filtered), width="stretch")

    st.subheader("Cost vs schedule performance")
    st.caption("Each bubble is a started phase, labelled by phase number (size = budget). "
               "Below 1.0 on CPI means over budget, below 1.0 on SPI means behind schedule.")
    st.plotly_chart(charts.cost_performance(phase_df), width="stretch")

with timeline:
    st.subheader("Phase timeline & milestones")
    st.caption("Bars are shaded by % complete. Diamonds are milestones coloured by RAG.")
    st.plotly_chart(charts.milestone_timeline(filtered, settings.report_date),
                    width="stretch")

    st.subheader("Milestones")
    ms = filtered[filtered["milestone"]][
        ["task_id", "task_name", "phase", "owner", "end_date", "percent_complete", "status",
         "rag"]].rename(columns={"end_date": "due_date"})
    st.dataframe(ms.style.map(rag_style, subset=["rag"]), hide_index=True,
                 width="stretch",
                 column_config={"due_date": st.column_config.DateColumn(format="DD MMM YYYY"),
                                "percent_complete": st.column_config.ProgressColumn(
                                    "% done", min_value=0, max_value=100, format="%d%%")})

    with st.expander("Task-level Gantt chart"):
        st.plotly_chart(charts.task_gantt(filtered, settings.report_date),
                        width="stretch")

with budget:
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Planned budget", money(summary.budget_planned, settings.currency))
    b2.metric("Actual spend", money(summary.budget_actual, settings.currency))
    b3.metric("Earned value", money(summary.earned_value, settings.currency),
              help="Budgeted cost of the work actually completed.")
    b4.metric("Forecast at completion", money(summary.eac, settings.currency),
              f"{money(summary.eac - summary.budget_planned, settings.currency)}",
              delta_color="inverse")

    st.subheader("Budget variance by phase")
    st.caption("Cost variance compares what the completed work *should* have cost (earned "
               "value) with what was actually spent, so in-progress phases are judged fairly.")
    st.plotly_chart(charts.budget_variance(phase_df, settings.currency),
                    width="stretch")

    st.subheader("Spend curve")
    st.plotly_chart(charts.cumulative_spend(filtered, settings.report_date, settings.currency),
                    width="stretch")

    st.subheader("Biggest cost overruns")
    worst = (filtered[filtered["cost_variance"] < 0]
             .sort_values("cost_variance")
             .head(10)[["task_id", "task_name", "owner", "percent_complete",
                        "budget_planned_sar", "budget_actual_sar", "earned_value",
                        "cost_variance", "cost_overrun_pct"]])
    st.dataframe(worst, hide_index=True, width="stretch", column_config={
        "budget_planned_sar": st.column_config.NumberColumn("Planned", format="localized"),
        "budget_actual_sar": st.column_config.NumberColumn("Actual", format="localized"),
        "earned_value": st.column_config.NumberColumn("Earned", format="localized"),
        "cost_variance": st.column_config.NumberColumn("Cost variance", format="localized"),
        "cost_overrun_pct": st.column_config.NumberColumn("Overrun", format="%.0f%%"),
        "percent_complete": st.column_config.NumberColumn("% done", format="%d%%"),
    })

with overdue_tab:
    overdue = (filtered[filtered["overdue"]]
               .sort_values("days_overdue", ascending=False)
               [["task_id", "task_name", "phase", "owner", "priority", "end_date",
                 "days_overdue", "percent_complete", "budget_actual_sar"]])
    if overdue.empty:
        st.success("🎉 No overdue tasks.")
    else:
        st.subheader(f"{len(overdue)} overdue task(s)")
        st.dataframe(
            overdue.style.map(overdue_style, subset=["days_overdue"]),
            hide_index=True, width="stretch",
            column_config={
                "end_date": st.column_config.DateColumn("Due date", format="DD MMM YYYY"),
                "days_overdue": st.column_config.NumberColumn("Days overdue"),
                "percent_complete": st.column_config.ProgressColumn(
                    "% done", min_value=0, max_value=100, format="%d%%"),
                "budget_actual_sar": st.column_config.NumberColumn("Spent", format="localized"),
            },
        )
        st.download_button("⬇️ Download overdue list", overdue.to_csv(index=False).encode(),
                           file_name="overdue_tasks.csv", mime="text/csv")

with team:
    st.subheader("Workload by owner")
    st.plotly_chart(charts.owner_workload(filtered), width="stretch")
    owner_df = (filtered.groupby("owner")
                .agg(tasks=("task_id", "count"), overdue=("overdue", "sum"),
                     avg_progress=("percent_complete", "mean"),
                     budget=("budget_planned_sar", "sum"),
                     spent=("budget_actual_sar", "sum"))
                .sort_values("overdue", ascending=False).reset_index())
    st.dataframe(owner_df, hide_index=True, width="stretch", column_config={
        "avg_progress": st.column_config.ProgressColumn(
            "Avg progress", min_value=0, max_value=100, format="%.0f%%"),
        "budget": st.column_config.NumberColumn(format="localized"),
        "spent": st.column_config.NumberColumn(format="localized"),
    })

with all_tasks:
    search = st.text_input("🔎 Search tasks", placeholder="e.g. payment, sensor, iOS")
    view = filtered
    if search:
        view = view[view["task_name"].str.contains(search, case=False)
                    | view["task_id"].str.contains(search, case=False)]
    cols = ["task_id", "task_name", "phase", "owner", "priority", "start_date", "end_date",
            "percent_complete", "status", "rag", "budget_planned_sar", "budget_actual_sar"]
    st.dataframe(view[cols].style.map(rag_style, subset=["rag"]), hide_index=True,
                 width="stretch", height=560, column_config={
                     "start_date": st.column_config.DateColumn(format="DD MMM YYYY"),
                     "end_date": st.column_config.DateColumn(format="DD MMM YYYY"),
                     "percent_complete": st.column_config.ProgressColumn(
                         "% done", min_value=0, max_value=100, format="%d%%"),
                     "budget_planned_sar": st.column_config.NumberColumn(
                         "Planned", format="localized"),
                     "budget_actual_sar": st.column_config.NumberColumn(
                         "Actual", format="localized"),
                 })

st.caption(f"RAG rules: a task is Red when overdue, >{settings.red_overrun:.0%} over its earned "
           f"value or >30 pts behind plan; Amber at >{settings.amber_overrun:.0%} over or "
           f">15 pts behind. Overall RAG is Green when both CPI and SPI are ≥ "
           f"{settings.green_threshold} with nothing overdue, Red below "
           f"{settings.red_threshold}. Thresholds are configurable in `.env`.")
