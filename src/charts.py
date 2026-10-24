"""Plotly figures used by the dashboard."""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

RAG_COLORS = {"Green": "#2E9E5B", "Amber": "#E8A33D", "Red": "#D64545"}
STATUS_COLORS = {
    "Done": "#2E9E5B",
    "In progress": "#3B7DD8",
    "Overdue": "#D64545",
    "Not started": "#9AA4B2",
}
OVER_BUDGET = "#D64545"
UNDER_BUDGET = "#2E9E5B"
PLANNED = "#9AA4B2"
EARNED = "#7FB89A"
ACTUAL = "#3B7DD8"


def _layout(fig: go.Figure, height: int = 420) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(size=13),
    )
    return fig


def _today_line(fig: go.Figure, report_date: date) -> None:
    # add_vline's annotation is unreliable with date axes, so draw both by hand.
    x = pd.Timestamp(report_date)
    fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, yref="paper",
                  line=dict(color="#D64545", width=2, dash="dash"))
    fig.add_annotation(x=x, y=0.99, yref="paper", text="Status date", showarrow=False,
                       xanchor="left", yanchor="top", xshift=4, font=dict(color="#D64545"))


def milestone_timeline(df: pd.DataFrame, report_date: date) -> go.Figure:
    """Gantt of phases with milestone diamonds and a status-date marker."""
    phases = (
        df.groupby("phase")
        .agg(start=("start_date", "min"), end=("end_date", "max"),
             planned=("budget_planned_sar", "sum"),
             earned=("earned_value", "sum"))
        .reset_index()
    )
    phases["progress"] = (phases["earned"] / phases["planned"] * 100).round(0)
    phases["label"] = phases["progress"].astype(int).astype(str) + "%"
    # Plotly timelines need the bar to end after the last day, not on it.
    phases["end_excl"] = phases["end"] + pd.Timedelta(days=1)

    fig = px.timeline(
        phases, x_start="start", x_end="end_excl", y="phase", text="label",
        color="progress", color_continuous_scale=["#E3EAF5", "#3B7DD8"],
        range_color=[0, 100],
        hover_data={"start": "|%d %b %Y", "end": "|%d %b %Y", "progress": True,
                    "end_excl": False, "label": False},
    )
    fig.update_traces(textposition="inside", insidetextanchor="middle")

    milestones = df[df["milestone"]]
    if not milestones.empty:
        fig.add_trace(go.Scatter(
            x=milestones["end_date"], y=milestones["phase"], mode="markers",
            marker=dict(symbol="diamond", size=15,
                        color=[STATUS_COLORS["Not started"] if s == "Not started"
                               else RAG_COLORS[r]
                               for r, s in zip(milestones["rag"], milestones["status"])],
                        line=dict(color="white", width=1.5)),
            name="Milestone",
            customdata=milestones[["task_name", "status"]],
            hovertemplate="<b>%{customdata[0]}</b><br>%{x|%d %b %Y}<br>%{customdata[1]}"
                          "<extra></extra>",
        ))

    _today_line(fig, report_date)
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_xaxes(title=None)
    fig.update_layout(coloraxis_colorbar=dict(title="% done"))
    return _layout(fig, height=460)


def task_gantt(df: pd.DataFrame, report_date: date) -> go.Figure:
    data = df.sort_values("start_date").assign(
        end_excl=lambda d: d["end_date"] + pd.Timedelta(days=1),
        label=lambda d: d["task_id"] + "  " + d["task_name"],
    )
    fig = px.timeline(
        data, x_start="start_date", x_end="end_excl", y="label", color="status",
        color_discrete_map=STATUS_COLORS,
        hover_data={"owner": True, "percent_complete": True, "end_excl": False,
                    "label": False},
    )
    _today_line(fig, report_date)
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_xaxes(title=None)
    return _layout(fig, height=max(420, 22 * len(data) + 80))


def budget_variance(phase_df: pd.DataFrame, currency: str) -> go.Figure:
    """Planned / earned / actual bars per phase with the cost variance alongside."""
    fig = make_subplots(rows=1, cols=2, column_widths=[0.6, 0.4], horizontal_spacing=0.08,
                        subplot_titles=(f"Planned vs actual ({currency})",
                                        f"Cost variance: earned − actual ({currency})"),
                        shared_yaxes=True)
    for column, color in (("Planned", PLANNED), ("Earned", EARNED), ("Actual", ACTUAL)):
        fig.add_trace(go.Bar(y=phase_df["Phase"], x=phase_df[column], name=column,
                             orientation="h", marker_color=color,
                             hovertemplate="%{y}<br>" + column + " %{x:,.0f}<extra></extra>"),
                      row=1, col=1)
    variance = phase_df["Cost variance"]
    fig.add_trace(go.Bar(
        y=phase_df["Phase"], x=variance, orientation="h", showlegend=False,
        marker_color=[OVER_BUDGET if v < 0 else UNDER_BUDGET for v in variance],
        text=[f"{v:+,.0f}" for v in variance], textposition="auto",
        hovertemplate="%{y}<br>Cost variance %{x:+,.0f}<extra></extra>",
    ), row=1, col=2)
    fig.update_layout(barmode="group")
    fig.update_yaxes(autorange="reversed")
    _layout(fig, height=480)
    # Lift the legend clear of the subplot titles.
    fig.update_layout(margin=dict(t=80), legend=dict(y=1.12, x=0, xanchor="left"))
    return fig


def cost_performance(phase_df: pd.DataFrame) -> go.Figure:
    """CPI vs SPI per phase: bottom-left quadrant is over budget and late."""
    # Phases with no work yet have no meaningful indices, so leave them out.
    started = phase_df[(phase_df["Earned"] > 0) | (phase_df["Actual"] > 0)].assign(
        # Finished phases cluster near (1, 1); short labels keep them readable.
        label=lambda d: d["Phase"].str.split(".").str[0])
    fig = px.scatter(
        started, x="SPI", y="CPI", text="label", color="RAG", size="Planned",
        color_discrete_map=RAG_COLORS, size_max=40, hover_name="Phase",
        hover_data={"Planned": ":,.0f", "Actual": ":,.0f", "label": False},
    )
    fig.add_hline(y=1, line_dash="dot", line_color="#9AA4B2")
    fig.add_vline(x=1, line_dash="dot", line_color="#9AA4B2")
    fig.update_traces(textposition="middle center", textfont=dict(color="white", size=12))
    return _layout(fig, height=420)


def cumulative_spend(df: pd.DataFrame, report_date: date, currency: str) -> go.Figure:
    """S-curve of planned spend over time vs. actual spend to date."""
    days = pd.date_range(df["start_date"].min(), df["end_date"].max(), freq="W")
    planned = []
    for d in days:
        dur = (df["end_date"] - df["start_date"]).dt.days + 1
        frac = (((d - df["start_date"]).dt.days + 1) / dur).clip(0, 1)
        planned.append((df["budget_planned_sar"] * frac).sum())

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=days, y=planned, name="Planned (baseline)", mode="lines",
                             line=dict(color=PLANNED, width=3)))
    fig.add_trace(go.Scatter(
        x=[pd.Timestamp(report_date)], y=[df["budget_actual_sar"].sum()],
        name="Actual to date", mode="markers", marker=dict(color=ACTUAL, size=14)))
    fig.add_trace(go.Scatter(
        x=[pd.Timestamp(report_date)], y=[df["earned_value"].sum()],
        name="Earned value", mode="markers",
        marker=dict(color=UNDER_BUDGET, size=14, symbol="diamond")))
    _today_line(fig, report_date)
    fig.update_yaxes(title=currency, tickformat=",.0f")
    return _layout(fig, height=380)


def status_donut(df: pd.DataFrame) -> go.Figure:
    counts = df["status"].value_counts().reindex(list(STATUS_COLORS)).dropna()
    fig = go.Figure(go.Pie(
        labels=counts.index, values=counts.values, hole=0.6, sort=False,
        marker=dict(colors=[STATUS_COLORS[s] for s in counts.index]),
        textinfo="value",
    ))
    return _layout(fig, height=320)


def owner_workload(df: pd.DataFrame) -> go.Figure:
    data = df.groupby(["owner", "status"]).size().reset_index(name="tasks")
    order = df["owner"].value_counts().index.tolist()
    fig = px.bar(data, y="owner", x="tasks", color="status", orientation="h",
                 color_discrete_map=STATUS_COLORS, category_orders={"owner": order})
    fig.update_yaxes(title=None)
    fig.update_xaxes(title="Tasks")
    return _layout(fig, height=360)
