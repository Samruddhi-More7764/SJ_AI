import pandas as pd

from app.charts import generate_chart, infer_encoding, _chart_component


def test_chart_type_bar_not_forced_to_table():
    df = pd.DataFrame(
        {
            "company_name": ["SBI", "SBI"],
            "symbol": ["SBIN", "SBIN"],
            "period_end": ["2018-06-30", "2018-03-31"],
            "value_numeric": [1.0, 2.0],
        }
    )
    chart = generate_chart(df, "Revenue", "bar")
    traces = chart.get("data") or []
    types = {t.get("type") for t in traces}
    assert "table" not in types
    assert "bar" in types


def test_top_n_uses_company_not_period_on_category_axis():
    df = pd.DataFrame(
        {
            "company_name": ["A", "B", "C", "A", "B", "C"],
            "period_end": ["2018-03-31"] * 3 + ["2018-06-30"] * 3,
            "value_numeric": [1, 2, 3, 10, 20, 30],
        }
    )
    kind, x_col, y_col, frame = infer_encoding(df, "bar", None, None)
    assert kind == "hbar"
    assert x_col == "value_numeric"
    assert y_col == "company_name"
    assert len(frame) == 3
    chart = generate_chart(df, "Top companies", "hbar")
    types = {t.get("type") for t in (chart.get("data") or [])}
    assert "bar" in types
    assert "table" not in types
    assert (chart.get("data") or [{}])[0].get("orientation") == "h"


def test_chart_component_is_interactive():
    payload = _chart_component(
        {"data": [], "layout": {}}, "Top companies", "out.csv"
    ).serialize_for_frontend()
    assert payload["interactive"] is True
    assert payload["data"]["config"]["displayModeBar"] is True
    assert payload["data"]["config"]["scrollZoom"] is True


def test_histogram_type():
    df = pd.DataFrame({"value_numeric": [1.0, 2.0, 2.0, 3.0]})
    chart = generate_chart(df, "Dist", "histogram")
    types = {t.get("type") for t in (chart.get("data") or [])}
    assert "histogram" in types
