"""Plotly charts with LLM encoding and interactive config."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional, Tuple, Type

import pandas as pd
import plotly.express as px
import plotly.io as pio
from pydantic import BaseModel, Field

from vanna.components import (
    ChartComponent,
    ComponentType,
    NotificationComponent,
    SimpleTextComponent,
    UiComponent,
)
from vanna.core.tool import Tool, ToolContext, ToolResult
from vanna.integrations.local import LocalFileSystem
from vanna.integrations.plotly import PlotlyChartGenerator

from app.cache import remember_chart

_THEME = PlotlyChartGenerator.THEME_COLORS
_PALETTE = PlotlyChartGenerator.COLOR_PALETTE

PLOTLY_CONFIG = {
    "responsive": True,
    "displayModeBar": True,
    "scrollZoom": True,
    "displaylogo": False,
}

logger = logging.getLogger("stockjarvis")


class FilingsVisualizeArgs(BaseModel):
    filename: str = Field(description="CSV filename written by run_sql")
    title: Optional[str] = Field(default=None, description="Chart title")
    chart_type: Optional[str] = Field(
        default=None,
        description=(
            "bar (ranked comparison), hbar (horizontal bar), line (time series), "
            "scatter, or histogram (distribution). For top-N companies use hbar."
        ),
    )
    x: Optional[str] = Field(default=None, description="Column for the x axis")
    y: Optional[str] = Field(default=None, description="Column for the y axis")


def _numeric_col(df: pd.DataFrame) -> str:
    if "value_numeric" in df.columns:
        return "value_numeric"
    numeric = df.select_dtypes(include="number").columns.tolist()
    return numeric[0] if numeric else df.columns[-1]


def _nunique(df: pd.DataFrame, col: str) -> int:
    if col not in df.columns:
        return 0
    return int(df[col].nunique(dropna=True))


def infer_encoding(
    df: pd.DataFrame,
    chart_type: Optional[str],
    x: Optional[str],
    y: Optional[str],
) -> Tuple[str, str, str, pd.DataFrame]:
    """Return (kind, x_col, y_col, frame). Ranking uses one row per company."""
    kind = (chart_type or "").strip().lower()
    if kind in {"horizontal_bar", "barh"}:
        kind = "hbar"
    companies = _nunique(df, "company_name")
    periods = _nunique(df, "period_end")
    ranking = companies >= 2 and companies >= max(periods, 1)

    if ranking and kind in {"", "bar", "hbar"}:
        frame = df.copy()
        if "period_end" in frame.columns:
            frame = frame.sort_values("period_end").groupby(
                "company_name", as_index=False
            ).last()
        elif "value_numeric" in frame.columns:
            frame = frame.groupby("company_name", as_index=False)["value_numeric"].max()
        value = x if x in frame.columns else _numeric_col(frame)
        category = y if y in frame.columns else "company_name"
        frame = frame.sort_values(value, ascending=True)
        return "hbar", value, category, frame

    if kind == "histogram":
        value = x or _numeric_col(df)
        return "histogram", value, value, df

    x_col = x if x and x in df.columns else None
    y_col = y if y and y in df.columns else None
    if x_col is None:
        if "period_end" in df.columns and periods >= 2:
            x_col = "period_end"
        elif "company_name" in df.columns:
            x_col = "company_name"
        else:
            x_col = df.columns[0]
    if y_col is None:
        y_col = _numeric_col(df)
    if kind not in {"bar", "hbar", "line", "scatter", "histogram"}:
        kind = "line" if x_col in {"period_end", "period_start"} else "bar"
    return kind, x_col, y_col, df


def generate_chart(
    df: pd.DataFrame,
    title: str,
    chart_type: Optional[str] = None,
    x: Optional[str] = None,
    y: Optional[str] = None,
) -> Dict[str, Any]:
    if df.empty:
        raise ValueError("Cannot visualize empty DataFrame")
    kind, x_col, y_col, frame = infer_encoding(df, chart_type, x, y)
    if kind == "histogram":
        fig = px.histogram(
            frame,
            x=x_col,
            title=title,
            color_discrete_sequence=[_THEME["teal"]],
        )
    elif kind == "line":
        fig = px.line(
            frame,
            x=x_col,
            y=y_col,
            title=title,
            color_discrete_sequence=[_THEME["teal"]],
        )
    elif kind == "scatter":
        fig = px.scatter(
            frame,
            x=x_col,
            y=y_col,
            title=title,
            color_discrete_sequence=[_THEME["magenta"]],
        )
    elif kind == "hbar":
        fig = px.bar(
            frame,
            x=x_col,
            y=y_col,
            orientation="h",
            title=title,
            color_discrete_sequence=[_THEME["orange"]],
        )
    else:
        fig = px.bar(
            frame,
            x=x_col,
            y=y_col,
            title=title,
            color_discrete_sequence=[_THEME["orange"]],
        )
    fig.update_layout(
        font={"color": _THEME["navy"]},
        autosize=True,
        colorway=_PALETTE,
        hovermode="closest",
        dragmode="zoom",
        xaxis_title=x_col,
        yaxis_title=y_col if kind != "histogram" else "count",
    )
    fig.update_traces(
        hovertemplate="%{x}<br>%{y}<extra></extra>"
        if kind != "histogram"
        else "%{x}<br>%{y}<extra></extra>"
    )
    return json.loads(pio.to_json(fig))


def _chart_component(chart_dict: Dict[str, Any], title: str, filename: str) -> ChartComponent:
    return ChartComponent(
        chart_type="plotly",
        data=chart_dict,
        title=title,
        interactive=True,
        config={"source_file": filename, **PLOTLY_CONFIG},
    )


class FilingsVisualizeDataTool(Tool[FilingsVisualizeArgs]):
    """visualize_data that honors chart_type plus x/y encoding."""

    def __init__(self, file_system: Optional[LocalFileSystem] = None):
        self.file_system = file_system or LocalFileSystem()

    @property
    def name(self) -> str:
        return "visualize_data"

    @property
    def description(self) -> str:
        return (
            "Chart a run_sql CSV. For top-N / ranking use chart_type=hbar, "
            "x=value_numeric, y=company_name. For one company over time use line "
            "with x=period_end. For a distribution use histogram. "
            "Pass x and y column names when you know them."
        )

    def get_args_schema(self) -> Type[FilingsVisualizeArgs]:
        return FilingsVisualizeArgs

    async def execute(
        self, context: ToolContext, args: FilingsVisualizeArgs
    ) -> ToolResult:
        try:
            csv_content = await self.file_system.read_file(args.filename, context)
            import io

            df = pd.read_csv(io.StringIO(csv_content))
            title = args.title or f"Visualization of {args.filename}"
            t0 = time.perf_counter()
            chart_dict = generate_chart(
                df, title, chart_type=args.chart_type, x=args.x, y=args.y
            )
            logger.info(
                "event=chart_done elapsed_s=%.3f rows=%s type=%s",
                time.perf_counter() - t0,
                len(df),
                args.chart_type,
            )
            remember_chart(context.conversation_id, chart_dict)
            result = (
                f"Created interactive {args.chart_type or 'auto'} chart from "
                f"'{args.filename}' ({len(df)} rows)."
            )
            return ToolResult(
                success=True,
                result_for_llm=result,
                ui_component=UiComponent(
                    rich_component=_chart_component(chart_dict, title, args.filename),
                    simple_component=SimpleTextComponent(text=result),
                ),
                metadata={"filename": args.filename, "chart": chart_dict},
            )
        except Exception as exc:
            error_message = f"Error creating visualization: {exc}"
            return ToolResult(
                success=False,
                result_for_llm=error_message,
                ui_component=UiComponent(
                    rich_component=NotificationComponent(
                        type=ComponentType.NOTIFICATION,
                        level="error",
                        message=error_message,
                    ),
                    simple_component=SimpleTextComponent(text=error_message),
                ),
                error=str(exc),
            )
