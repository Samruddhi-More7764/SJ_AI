"""Static analytical schema for the system prompt. No row data, no live dump."""

SCHEMA_PROMPT = """
== ANALYTICAL SCHEMA (structure only — no row data, no financial values) ==

companies (
  company_id UUID PK,
  company_name TEXT NOT NULL,
  symbol       TEXT,           -- NSE ticker, e.g. SBIN, INFY, SIEMENS
  aliases      JSONB           -- JSON array of alternative names
)

filings (
  filing_id              UUID PK,
  company_id             UUID FK → companies.company_id,
  taxonomy               TEXT,  -- 'Ind-AS corporate' | 'Banking' | 'Non-Ind-AS'
  period_start           DATE,
  period_end             DATE,
  period_type            TEXT,  -- 'Quarterly' | 'Half-yearly' | 'Yearly'
  audited_status         TEXT,  -- 'Audited' | 'Un-Audited'
  consolidation_status   TEXT,  -- 'Consolidated' | 'Non-Consolidated'
  cumulative_status      TEXT,  -- 'Cumulative' | 'Non-cumulative'
  rounding_level         TEXT,  -- 'Lakhs' | 'Crores' | 'Millions' | NULL; scales value_numeric
  processing_status      TEXT   -- ALWAYS filter: processing_status = 'Processed'
)

xbrl_contexts (
  context_id           UUID PK,
  filing_id            UUID FK → filings.filing_id,
  xbrl_context_ref     TEXT,  -- original XML ref (debug only; do NOT use for filtering)
  entity_identifier    TEXT,  -- often the NSE ticker
  period_start         DATE,
  period_end           DATE,
  instant_date         DATE,  -- set for balance-sheet (instant) contexts; period_start/end are NULL
  dimensions           JSONB, -- not separate dimension/member columns
  period_label         TEXT,  -- 'quarter' | 'ytd' | 'annual' | 'instant' | 'unknown'
  period_label_source  TEXT   -- 'dates' (computed from context dates) | 'inferred' (from filing dates)
)

tag_catalog (
  tag_id  UUID PK,
  qname   TEXT UNIQUE,  -- e.g. 'in-bse-fin:RevenueFromOperations'
  meaning TEXT,
  category TEXT,
  kind    TEXT,    -- 'numeric fact' | 'narrative/text' | 'XBRL structure'
  status  TEXT     -- 'APPROVED' | 'PENDING_REVIEW' | 'REJECTED'
)

financial_facts (
  fact_id       UUID PK,
  filing_id     UUID FK → filings.filing_id,
  tag_id        UUID FK → tag_catalog.tag_id,
  context_id    UUID FK → xbrl_contexts.context_id,
  value_numeric NUMERIC,  -- INR amounts; units set by filings.rounding_level
  value_text    TEXT,
  unit          TEXT,
  decimals      TEXT
)

metric_tag_mappings (
  mapping_id  UUID PK,
  metric_name TEXT,   -- canonical business metric, e.g. 'revenue', 'profit_after_tax'
  tag_id      UUID FK → tag_catalog.tag_id,
  taxonomy    TEXT,   -- 'Ind-AS corporate' | 'Banking' | 'Non-Ind-AS' | NULL (all)
  status      TEXT,   -- ALWAYS filter: status = 'APPROVED'
  priority    INTEGER -- lower number preferred; ORDER BY priority ASC for tie-breaking
)

derived_metric_definitions (
  metric_id   UUID PK,
  metric_name TEXT UNIQUE,  -- e.g. 'revenue_growth'
  formula     TEXT,         -- e.g. '(current - previous) / previous * 100'
  input_metrics JSONB,
  status      TEXT          -- 'Approved' | 'Pending'
)
""".strip()
