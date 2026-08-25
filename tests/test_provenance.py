from app.provenance import build_provenance


def test_provenance_from_mapped_metric_rows():
    sql = """
    SELECT c.company_name, f.period_end, ff.value_numeric, f.rounding_level,
           t.qname, m.metric_name
    FROM companies c
    JOIN filings f ON f.company_id = c.company_id AND f.processing_status = 'Processed'
    JOIN financial_facts ff ON ff.filing_id = f.filing_id
    JOIN tag_catalog t ON t.tag_id = ff.tag_id
    JOIN metric_tag_mappings m ON m.tag_id = t.tag_id AND m.status = 'APPROVED'
    WHERE m.metric_name = 'revenue'
    """
    rows = [
        {
            "company_name": "State Bank of India",
            "period_end": "2020-09-30",
            "value_numeric": "1",
            "rounding_level": "Crores",
            "qname": "in-bse-fin:RevenueFromOperations",
            "metric_name": "revenue",
        }
    ]
    columns = list(rows[0].keys())
    prov = build_provenance(sql, columns, rows)
    assert "value_numeric" in prov["source"].lower()
    assert "in-bse-fin:RevenueFromOperations" in prov["tags"]
    assert prov["metric"] == "revenue"
    assert "2020-09-30" in prov["period"]
    assert "Crores" in prov["rounding"]
    assert "SELECT" in prov["sql"].upper()
    assert prov["formula"] == "(none)"


def test_provenance_sql_arithmetic_and_derived_formula():
    sql = """
    SELECT c.company_name, (a.value_numeric - b.value_numeric) / b.value_numeric * 100
           AS value_numeric, m.metric_name, t.qname
    FROM companies c
    """
    rows = [
        {
            "company_name": "A",
            "value_numeric": 10,
            "metric_name": "revenue_growth",
            "qname": "in-bse-fin:RevenueFromOperations",
        }
    ]
    prov = build_provenance(
        sql,
        list(rows[0].keys()),
        rows,
        derived_formulas={"revenue_growth": "(current - previous) / previous * 100"},
    )
    assert "computed in SQL" in prov["source"]
    assert "(current - previous) / previous * 100" in (prov["formula"] or "")
    assert "in-bse-fin:RevenueFromOperations" in prov["tags"]


def test_provenance_component_serializes_custom_type():
    from app.provenance import ProvenanceComponent

    payload = ProvenanceComponent(provenance={"source": "x"}).serialize_for_frontend()
    assert payload["type"] == "provenance"
    assert payload["data"]["source"] == "x"
