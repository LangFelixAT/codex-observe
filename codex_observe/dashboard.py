from __future__ import annotations

import argparse
import html
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from codex_observe.analysis import (
    build_tree,
    compactions_df,
    diagnostics_cards_html,
    diagnostics_df,
    findings_df,
    fmt_int,
    fmt_short,
    guardian_overhead_df,
    next_run_playbook_df,
    numericize,
    opportunity_df,
    opportunity_html,
    playbook_html,
    prepare_threads,
    sidebar_time_label,
    token_jumps_df,
    useful_text_preview,
    worker_goal,
)

from codex_observe.report import (
    build_report,
    command_arg,
    compare_reports,
    comparison_json,
    comparison_markdown,
    latest_ingest_scope,
    report_json,
    report_markdown,
    report_next_run_brief,
    report_next_run_checklist,
    report_success_target,
    session_risk_distribution,
    report_triage,
    session_summaries,
)


RAW_TABLE_PREVIEW_ROWS = 500


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--db", default=str(Path.home() / ".codex-observe" / "codex_observe.sqlite")
    )
    args, _ = p.parse_known_args()
    return args


@st.cache_data(show_spinner=False)
def read_sql(db: str, query: str, params: tuple = ()) -> pd.DataFrame:
    with sqlite3.connect(db) as conn:
        return pd.read_sql_query(query, conn, params=params)


def dataframe_preview(
    df: pd.DataFrame, limit: int = RAW_TABLE_PREVIEW_ROWS
) -> tuple[pd.DataFrame, str | None]:
    if limit <= 0 or len(df) <= limit:
        return df.copy(), None
    caption = (
        f"Showing first {fmt_int(limit)} of {fmt_int(len(df))} rows "
        "to keep large real-history dashboards responsive."
    )
    return df.head(limit).copy(), caption


def render_capped_dataframe(
    df: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    limit: int = RAW_TABLE_PREVIEW_ROWS,
) -> None:
    display = df
    if columns is not None:
        existing = [column for column in columns if column in df.columns]
        display = df[existing] if existing else df
    preview, caption = dataframe_preview(display, limit)
    if caption:
        st.caption(caption)
    st.dataframe(preview, width="stretch", hide_index=True)


def dashboard_css() -> str:
    return """
<style>
:root {
  --co-ink: #172026;
  --co-muted: #5d6b73;
  --co-border: #d7dee2;
  --co-surface: #f8faf9;
  --co-panel: #ffffff;
  --co-accent: #216869;
  --co-accent-2: #8f5f2a;
  --co-danger: #a34743;
}

.stApp {
  background: var(--co-surface);
  color: var(--co-ink);
}

[data-testid="stSidebar"] {
  background: #eef3f1;
  border-right: 1px solid var(--co-border);
}

[data-testid="stMetric"] {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  padding: 0.7rem 0.8rem;
}

[data-testid="stMetric"] label,
[data-testid="stCaptionContainer"] {
  color: var(--co-muted);
}

[data-testid="stTabs"] [role="tablist"] {
  flex-wrap: wrap;
  gap: 0.25rem 0.5rem;
}

[data-testid="stTabs"] [role="tab"] {
  max-width: 100%;
  white-space: normal;
}

[data-testid="stSidebar"] button {
  border-radius: 8px;
  min-height: 2.7rem;
  text-align: left;
  white-space: normal;
}

[data-testid="stSidebar"] button p {
  line-height: 1.25;
  text-align: left;
  white-space: normal;
}

.co-metric-grid {
  display: grid;
  gap: 0.7rem;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  margin: 0 0 1rem 0;
}

.co-metric-card {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  min-width: 0;
  padding: 0.78rem 0.85rem;
}

.co-metric-label {
  color: var(--co-muted);
  font-size: 0.78rem;
  font-weight: 650;
  letter-spacing: 0;
  line-height: 1.2;
  margin-bottom: 0.28rem;
}

.co-metric-value {
  color: var(--co-ink);
  font-size: 1.05rem;
  font-weight: 750;
  letter-spacing: 0;
  line-height: 1.18;
  overflow-wrap: anywhere;
}

.co-hero {
  border-bottom: 1px solid var(--co-border);
  margin: -1rem -1rem 1.2rem -1rem;
  padding: 1.25rem 1rem 1rem 1rem;
}

.co-kicker {
  color: var(--co-accent);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0;
  margin: 0 0 0.2rem 0;
  text-transform: uppercase;
}

.co-title {
  color: var(--co-ink);
  font-size: 2rem;
  font-weight: 750;
  letter-spacing: 0;
  line-height: 1.12;
  margin: 0;
}

.co-subtitle {
  color: var(--co-muted);
  font-size: 1rem;
  margin: 0.35rem 0 0 0;
  max-width: 58rem;
}

.co-empty {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-left: 5px solid var(--co-accent);
  border-radius: 8px;
  padding: 1rem 1.1rem;
}

.co-empty h2 {
  font-size: 1.15rem;
  letter-spacing: 0;
  margin: 0 0 0.35rem 0;
}

.co-empty p {
  color: var(--co-muted);
  margin: 0;
}

.co-empty-actions {
  display: grid;
  gap: 0.65rem;
  margin-top: 0.9rem;
}

.co-empty-action {
  background: #f8faf9;
  border: 1px solid var(--co-border);
  border-radius: 8px;
  padding: 0.75rem 0.85rem;
}

.co-empty-action strong {
  display: block;
  font-size: 0.88rem;
  letter-spacing: 0;
  margin-bottom: 0.35rem;
}

.co-empty-action code {
  color: var(--co-ink);
  overflow-wrap: anywhere;
  white-space: normal;
}

.co-briefing {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-left: 5px solid var(--co-accent);
  border-radius: 8px;
  display: grid;
  gap: 0.85rem;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  margin: 0.2rem 0 1rem 0;
  padding: 1rem;
}

.co-briefing h3 {
  font-size: 1.06rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.38rem 0;
}

.co-briefing p {
  color: var(--co-muted);
  font-size: 0.9rem;
  margin: 0.22rem 0;
}

.co-briefing-label {
  color: var(--co-accent);
  font-size: 0.76rem;
  font-weight: 750;
  letter-spacing: 0;
  margin-bottom: 0.3rem;
  text-transform: uppercase;
}

.co-briefing-grid {
  display: grid;
  gap: 0.55rem;
}

.co-briefing-fact {
  background: var(--co-surface);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  padding: 0.65rem 0.75rem;
}

.co-briefing-fact strong {
  color: var(--co-ink);
  display: block;
  font-size: 0.92rem;
  line-height: 1.22;
  margin-bottom: 0.16rem;
}

.co-review-path {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  margin: 0 0 1rem 0;
  padding: 0.95rem 1rem;
}

.co-review-path h3 {
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-review-path p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.2rem 0 0.65rem 0;
}

.co-review-steps {
  display: grid;
  gap: 0.55rem;
  grid-template-columns: repeat(auto-fit, minmax(185px, 1fr));
}

.co-review-step {
  background: var(--co-surface);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  min-width: 0;
  padding: 0.65rem 0.75rem;
}

.co-review-step strong {
  color: var(--co-ink);
  display: block;
  font-size: 0.84rem;
  line-height: 1.22;
  margin-bottom: 0.2rem;
}

.co-review-step span,
.co-review-step code {
  color: var(--co-muted);
  display: block;
  font-size: 0.8rem;
  line-height: 1.25;
  overflow-wrap: anywhere;
  white-space: normal;
}

@media (max-width: 760px) {
  .co-briefing {
    grid-template-columns: 1fr;
  }
}
.co-risk-distribution {
  background: color-mix(in srgb, var(--co-accent) 6%, var(--co-panel));
  border: 1px solid var(--co-border);
  border-radius: 8px;
  margin: 0 0 1rem 0;
  padding: 0.9rem 1rem;
}

.co-risk-distribution h3 {
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-risk-distribution p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.2rem 0 0.65rem 0;
}

.co-risk-distribution-grid {
  display: grid;
  gap: 0.5rem;
  grid-template-columns: repeat(auto-fit, minmax(115px, 1fr));
}

.co-risk-distribution-item {
  background: var(--co-surface);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  min-width: 0;
  padding: 0.6rem 0.7rem;
}

.co-risk-distribution-item strong {
  color: var(--co-ink);
  display: block;
  font-size: 1.15rem;
  line-height: 1.1;
}

.co-risk-distribution-item span {
  color: var(--co-muted);
  display: block;
  font-size: 0.78rem;
  line-height: 1.2;
  margin-top: 0.15rem;
}

.co-next-run-checklist {
  background: color-mix(in srgb, var(--co-accent-2) 6%, var(--co-panel));
  border: 1px solid var(--co-border);
  border-radius: 8px;
  margin: 0 0 1rem 0;
  padding: 0.9rem 1rem;
}

.co-next-run-checklist h3 {
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-next-run-checklist p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.2rem 0 0.65rem 0;
}

.co-next-run-items {
  display: grid;
  gap: 0.55rem;
  grid-template-columns: repeat(auto-fit, minmax(215px, 1fr));
}

.co-next-run-item {
  background: var(--co-surface);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  min-width: 0;
  padding: 0.65rem 0.75rem;
}

.co-next-run-item strong {
  color: var(--co-ink);
  display: block;
  font-size: 0.82rem;
  line-height: 1.22;
  margin-bottom: 0.24rem;
}

.co-next-run-item span {
  color: var(--co-muted);
  display: block;
  font-size: 0.8rem;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.co-next-run-item .co-next-run-success {
  color: var(--co-accent-2);
  font-weight: 700;
  margin-top: 0.28rem;
}

.co-next-run-brief {
  background: color-mix(in srgb, var(--co-accent) 7%, var(--co-panel));
  border: 1px solid var(--co-border);
  border-radius: 8px;
  margin: 0 0 1rem 0;
  padding: 0.9rem 1rem;
}

.co-next-run-brief h3 {
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-next-run-brief p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.2rem 0 0.65rem 0;
}

.co-next-run-brief-grid {
  display: grid;
  gap: 0.55rem;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
}

.co-next-run-brief-item {
  background: var(--co-surface);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  min-width: 0;
  padding: 0.65rem 0.75rem;
}

.co-next-run-brief-item strong {
  color: var(--co-ink);
  display: block;
  font-size: 0.82rem;
  line-height: 1.22;
  margin-bottom: 0.24rem;
}

.co-next-run-brief-item span,
.co-next-run-brief-item code {
  color: var(--co-muted);
  display: block;
  font-size: 0.8rem;
  line-height: 1.25;
  overflow-wrap: anywhere;
  white-space: normal;
}

.co-next-run-brief-prompt {
  margin-top: 0.65rem;
}

.co-feedback-handoff {
  background: color-mix(in srgb, var(--co-accent) 5%, var(--co-panel));
  border: 1px solid var(--co-border);
  border-radius: 8px;
  margin: 0 0 1rem 0;
  padding: 0.9rem 1rem;
}

.co-feedback-handoff h3 {
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-feedback-handoff p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.2rem 0 0.65rem 0;
}

.co-feedback-grid {
  display: grid;
  gap: 0.55rem;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
}

.co-feedback-item {
  background: var(--co-surface);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  min-width: 0;
  padding: 0.65rem 0.75rem;
}

.co-feedback-item strong {
  color: var(--co-ink);
  display: block;
  font-size: 0.82rem;
  line-height: 1.22;
  margin-bottom: 0.2rem;
}

.co-feedback-item span,
.co-feedback-item code {
  color: var(--co-muted);
  display: block;
  font-size: 0.8rem;
  line-height: 1.25;
  overflow-wrap: anywhere;
  white-space: normal;
}

.co-diagnostics {
  display: grid;
  gap: 0.8rem;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  margin: 0.2rem 0 1rem 0;
}

.co-diagnostic {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  padding: 0.9rem 1rem;
}

.co-diagnostic-priority {
  color: var(--co-accent);
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0;
  margin-bottom: 0.25rem;
  text-transform: uppercase;
}

.co-diagnostic h3 {
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.4rem 0;
}

.co-diagnostic-action {
  color: var(--co-ink);
  margin: 0 0 0.5rem 0;
}

.co-diagnostic-evidence {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0;
}

.co-playbook {
  display: grid;
  gap: 0.65rem;
  margin: 0.4rem 0 1.1rem 0;
}

.co-playbook-step {
  align-items: flex-start;
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  display: grid;
  gap: 0.75rem;
  grid-template-columns: 2rem minmax(0, 1fr);
  padding: 0.85rem 1rem;
}

.co-playbook-number {
  align-items: center;
  background: color-mix(in srgb, var(--co-accent) 12%, white);
  border-radius: 999px;
  color: var(--co-accent);
  display: flex;
  font-weight: 800;
  height: 2rem;
  justify-content: center;
  line-height: 1;
  width: 2rem;
}

.co-playbook h3 {
  font-size: 0.98rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.28rem 0;
}

.co-playbook p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0;
}

.co-playbook-impact {
  color: var(--co-accent-2) !important;
  font-weight: 700;
}

.co-opportunities {
  display: grid;
  gap: 0.65rem;
  margin: 0.4rem 0 1.1rem 0;
}

.co-opportunity {
  align-items: flex-start;
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  display: grid;
  gap: 0.75rem;
  grid-template-columns: 2rem minmax(0, 1fr);
  padding: 0.85rem 1rem;
}

.co-opportunity-rank {
  align-items: center;
  background: color-mix(in srgb, var(--co-accent-2) 14%, white);
  border-radius: 999px;
  color: var(--co-accent-2);
  display: flex;
  font-weight: 800;
  height: 2rem;
  justify-content: center;
  line-height: 1;
  width: 2rem;
}

.co-opportunity h3 {
  font-size: 0.98rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.28rem 0;
}

.co-opportunity p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0;
}


.co-success-target {
  background: color-mix(in srgb, var(--co-accent-2) 7%, white);
  border: 1px solid var(--co-border);
  border-left: 4px solid var(--co-accent-2);
  border-radius: 8px;
  margin: 0.35rem 0 1.1rem 0;
  padding: 0.9rem 1rem;
}

.co-success-target-kicker {
  color: var(--co-muted);
  font-size: 0.76rem;
  font-weight: 750;
  letter-spacing: 0;
  margin-bottom: 0.35rem;
  text-transform: uppercase;
}

.co-success-target h3 {
  color: var(--co-ink);
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-success-target p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.15rem 0;
}

.co-success-target strong {
  color: var(--co-accent);
}
.co-opportunity-scale {
  color: var(--co-accent) !important;
  font-weight: 700;
}
.co-triage {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-left: 5px solid var(--co-accent-2);
  border-radius: 8px;
  margin: 0.2rem 0 1rem 0;
  padding: 0.95rem 1rem;
}

.co-triage-header {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.co-triage h3 {
  font-size: 1.02rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0;
}

.co-triage-risk {
  background: color-mix(in srgb, var(--co-accent-2) 14%, white);
  border-radius: 999px;
  color: var(--co-accent-2);
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0;
  padding: 0.25rem 0.55rem;
  text-transform: uppercase;
}

.co-triage p {
  color: var(--co-muted);
  font-size: 0.9rem;
  margin: 0.3rem 0;
}

.co-triage ul {
  margin: 0.55rem 0 0 1.1rem;
  padding: 0;
}

.co-triage li {
  color: var(--co-muted);
  margin: 0.18rem 0;
}

.co-comparison-preview {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-left: 5px solid var(--co-accent);
  border-radius: 8px;
  margin: 0.45rem 0 0.9rem 0;
  padding: 0.9rem 1rem;
}

.co-comparison-preview h3 {
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-comparison-preview p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.24rem 0;
}

.co-comparison-preview strong {
  color: var(--co-ink);
}

.co-report-scope {
  background: color-mix(in srgb, var(--co-warning) 10%, var(--co-surface));
  border: 1px solid color-mix(in srgb, var(--co-warning) 32%, var(--co-border));
  border-radius: 8px;
  color: var(--co-ink);
  font-size: 0.84rem;
  line-height: 1.35;
  margin: 0.65rem 0 0.85rem 0;
  overflow-wrap: anywhere;
  padding: 0.55rem 0.65rem;
}
.co-sample-coverage {
  background: var(--co-panel);
  border: 1px solid color-mix(in srgb, var(--co-warning) 38%, var(--co-border));
  border-left: 5px solid var(--co-warning);
  border-radius: 8px;
  margin: 0.75rem 0 0.95rem 0;
  padding: 0.85rem 0.95rem;
}

.co-sample-coverage h3 {
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-sample-coverage p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.22rem 0;
}

.co-sample-coverage-grid {
  display: grid;
  gap: 0.5rem;
  grid-template-columns: repeat(auto-fit, minmax(125px, 1fr));
  margin-top: 0.65rem;
}

.co-sample-coverage-fact {
  background: var(--co-surface);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  min-width: 0;
  padding: 0.55rem 0.65rem;
}

.co-sample-coverage-fact strong {
  color: var(--co-ink);
  display: block;
  font-size: 0.86rem;
}

.co-sample-coverage-fact span {
  color: var(--co-muted);
  display: block;
  font-size: 0.78rem;
  margin-top: 0.16rem;
}

.co-sample-coverage code {
  background: color-mix(in srgb, var(--co-warning) 12%, var(--co-surface));
  border: 1px solid color-mix(in srgb, var(--co-warning) 28%, var(--co-border));
  border-radius: 6px;
  display: block;
  font-size: 0.78rem;
  margin-top: 0.55rem;
  overflow-wrap: anywhere;
  padding: 0.45rem 0.55rem;
  white-space: normal;
}
.co-comparison-scope {
  background: color-mix(in srgb, var(--co-warning) 10%, var(--co-surface));
  border: 1px solid color-mix(in srgb, var(--co-warning) 32%, var(--co-border));
  border-radius: 8px;
  color: var(--co-ink);
  font-size: 0.84rem;
  line-height: 1.35;
  margin-top: 0.65rem;
  overflow-wrap: anywhere;
  padding: 0.55rem 0.65rem;
}
.co-comparison-deltas {
  display: grid;
  gap: 0.55rem;
  grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  margin-top: 0.75rem;
}

.co-comparison-delta {
  background: var(--co-surface);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  min-width: 0;
  padding: 0.62rem 0.7rem;
}

.co-comparison-delta strong {
  display: block;
  font-size: 0.82rem;
  line-height: 1.2;
  margin-bottom: 0.18rem;
}

.co-comparison-delta span {
  color: var(--co-muted);
  display: block;
  font-size: 0.82rem;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.co-comparison-followup {
  background: var(--co-surface);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  margin-top: 0.75rem;
  padding: 0.65rem 0.75rem;
}

.co-comparison-followup strong {
  display: block;
  font-size: 0.82rem;
  line-height: 1.2;
  margin-bottom: 0.22rem;
}

.co-comparison-followup code {
  color: var(--co-ink);
  font-size: 0.82rem;
  overflow-wrap: anywhere;
  white-space: normal;
}

.co-comparison-review-path {
  background: color-mix(in srgb, var(--co-accent) 6%, var(--co-surface));
  border: 1px solid var(--co-border);
  border-radius: 8px;
  margin-top: 0.75rem;
  padding: 0.65rem 0.75rem;
}

.co-comparison-review-path > strong {
  display: block;
  font-size: 0.82rem;
  line-height: 1.2;
  margin-bottom: 0.3rem;
}

.co-comparison-review-path ol {
  margin: 0.35rem 0 0 1.05rem;
  padding: 0;
}

.co-comparison-review-path li {
  color: var(--co-muted);
  font-size: 0.82rem;
  line-height: 1.3;
  margin: 0.24rem 0;
}

.co-comparison-review-path li strong {
  display: block;
  font-size: 0.82rem;
}

.co-comparison-review-path code {
  color: var(--co-ink);
  display: block;
  font-size: 0.78rem;
  margin-top: 0.12rem;
  overflow-wrap: anywhere;
  white-space: normal;
}

.co-comparison-review-path span {
  display: block;
  margin-top: 0.12rem;
}

.co-thread-brief {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-left: 5px solid var(--co-accent-2);
  border-radius: 8px;
  margin: 0.25rem 0 1rem 0;
  padding: 0.9rem 1rem;
}

.co-thread-brief h3 {
  font-size: 1.02rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-thread-brief p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.22rem 0;
}

.co-thread-brief-grid {
  display: grid;
  gap: 0.5rem;
  grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
  margin-top: 0.65rem;
}

.co-thread-brief-fact {
  background: var(--co-surface);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  padding: 0.55rem 0.65rem;
}

.co-thread-brief-fact strong {
  color: var(--co-ink);
  display: block;
  font-size: 0.82rem;
  margin-bottom: 0.18rem;
}

.co-tool-brief {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-left: 5px solid var(--co-accent);
  border-radius: 8px;
  margin: 0.25rem 0 1rem 0;
  padding: 0.9rem 1rem;
}

.co-tool-brief h3 {
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-tool-brief p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.22rem 0;
}

.co-tool-brief strong {
  color: var(--co-ink);
}

.co-duplication-brief {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-left: 5px solid var(--co-accent-2);
  border-radius: 8px;
  margin: 0.25rem 0 1rem 0;
  padding: 0.9rem 1rem;
}

.co-duplication-brief h3 {
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-duplication-brief p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.22rem 0;
}

.co-duplication-brief strong {
  color: var(--co-ink);
}

.co-timeline-brief {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-left: 5px solid var(--co-accent);
  border-radius: 8px;
  margin: 0.25rem 0 1rem 0;
  padding: 0.9rem 1rem;
}

.co-timeline-brief h3 {
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-timeline-brief p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.22rem 0;
}

.co-timeline-brief strong {
  color: var(--co-ink);
}

.co-inventory-brief {
  background: var(--co-panel);
  border: 1px solid var(--co-border);
  border-left: 5px solid var(--co-accent-2);
  border-radius: 8px;
  margin: 0.25rem 0 1rem 0;
  padding: 0.9rem 1rem;
}

.co-inventory-brief h3 {
  font-size: 1rem;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0 0 0.35rem 0;
}

.co-inventory-brief p {
  color: var(--co-muted);
  font-size: 0.88rem;
  margin: 0.22rem 0;
}

.co-inventory-brief-grid {
  display: grid;
  gap: 0.5rem;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  margin-top: 0.65rem;
}

.co-inventory-brief-fact {
  background: var(--co-surface);
  border: 1px solid var(--co-border);
  border-radius: 8px;
  padding: 0.55rem 0.65rem;
}

.co-inventory-brief-fact strong {
  color: var(--co-ink);
  display: block;
  font-size: 0.82rem;
  margin-bottom: 0.18rem;
}
</style>
"""


def render_metric_grid(items: list[tuple[str, object]]) -> None:
    cards = []
    for label, value in items:
        cards.append(
            '<div class="co-metric-card">'
            f'<div class="co-metric-label">{html.escape(str(label))}</div>'
            f'<div class="co-metric-value">{html.escape(str(value))}</div>'
            "</div>"
        )
    st.markdown(
        '<div class="co-metric-grid">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


def triage_card_html(triage: dict[str, object]) -> str:
    risk = html.escape(str(triage.get("risk_level") or "unknown"))
    driver = html.escape(
        str(triage.get("primary_driver") or "No high-signal diagnostic")
    )
    action = html.escape(
        str(triage.get("next_action") or "Inspect the largest thread.")
    )
    reasons = [html.escape(str(reason)) for reason in triage.get("reasons", [])]
    reason_items = "".join(f"<li>{reason}</li>" for reason in reasons[:5])
    return (
        '<section class="co-triage">'
        '<div class="co-triage-header">'
        "<h3>Run triage</h3>"
        f'<span class="co-triage-risk">{risk}</span>'
        "</div>"
        f"<p><strong>Primary driver:</strong> {driver}</p>"
        f"<p><strong>Next action:</strong> {action}</p>"
        f"<ul>{reason_items}</ul>"
        "</section>"
    )


def review_path_html(success_target: dict[str, object], has_comparison: bool) -> str:
    metric = html.escape(str(success_target.get("metric") or "target metric"))
    current = html.escape(str(success_target.get("current") or "current value"))
    target = html.escape(str(success_target.get("target") or "target value"))
    comparison_action = (
        "Pick the baseline run in Compare selected run and download the comparison JSON."
        if has_comparison
        else "Collect another run, then compare it against this report JSON."
    )
    steps = [
        (
            "1. Save report JSON",
            "Use Download report JSON for the aggregate baseline.",
        ),
        ("2. Compare workflow change", comparison_action),
        (
            "3. Validate next run",
            f"{metric}: {current} -> {target}",
        ),
        (
            "4. File safe feedback",
            "Use PUBLIC_TOUR_FEEDBACK.md; avoid prompts, tool output, and local paths.",
        ),
    ]
    rendered_steps = []
    for label, body in steps:
        rendered_steps.append(
            '<div class="co-review-step">'
            f"<strong>{html.escape(label)}</strong>"
            f"<span>{html.escape(body)}</span>"
            "</div>"
        )
    return "\n".join(
        [
            '<section class="co-review-path">',
            "  <h3>Next review path</h3>",
            "  <p>Turn this run into a validated workflow change without exposing private content.</p>",
            '  <div class="co-review-steps">',
            *[f"    {step}" for step in rendered_steps],
            "  </div>",
            "</section>",
        ]
    )


def risk_distribution_html(distribution: object) -> str:
    if not isinstance(distribution, dict):
        return ""
    labels = [
        ("high", "High risk"),
        ("medium", "Medium risk"),
        ("low", "Low risk"),
        ("unknown", "Unknown"),
    ]
    items = []
    for key, label in labels:
        value = int(distribution.get(key, 0) or 0)
        items.append(
            '<div class="co-risk-distribution-item">'
            f"<strong>{html.escape(fmt_int(value))}</strong>"
            f"<span>{html.escape(label)}</span>"
            "</div>"
        )
    total = sum(int(distribution.get(key, 0) or 0) for key, _ in labels)
    return "\n".join(
        [
            '<section class="co-risk-distribution">',
            "  <h3>Risk distribution</h3>",
            f"  <p>{html.escape(fmt_int(total))} imported conversations grouped by aggregate triage risk.</p>",
            '  <div class="co-risk-distribution-grid">',
            *[f"    {item}" for item in items],
            "  </div>",
            "</section>",
        ]
    )


def next_run_checklist_html(checklist: object) -> str:
    if not isinstance(checklist, list) or not checklist:
        return ""
    items = []
    for step in checklist[:4]:
        if not isinstance(step, dict):
            continue
        phase = str(step.get("phase") or "Next run step").strip()
        action = str(step.get("action") or "Review the report.").strip()
        success = str(step.get("success_check") or "Confirm the result.").strip()
        if not phase and not action and not success:
            continue
        items.append(
            '<div class="co-next-run-item">'
            f"<strong>{html.escape(phase or 'Next run step')}</strong>"
            f"<span>{html.escape(action)}</span>"
            f'<span class="co-next-run-success">{html.escape(success)}</span>'
            "</div>"
        )
    if not items:
        return ""
    return "\n".join(
        [
            '<section class="co-next-run-checklist">',
            "  <h3>Next run checklist</h3>",
            "  <p>Use this before, during, and after the next run to prove the workflow change.</p>",
            '  <div class="co-next-run-items">',
            *[f"    {item}" for item in items],
            "  </div>",
            "</section>",
        ]
    )


def next_run_brief_html(brief: object) -> str:
    if not isinstance(brief, dict):
        return ""
    habit = str(brief.get("habit") or "Apply the top recommended workflow habit.")
    watch = str(brief.get("watch") or "top aggregate driver")
    metric = str(brief.get("target_metric") or "target metric")
    current = str(brief.get("current") or "current value")
    target = str(brief.get("target") or "target value")
    guardrail = str(
        brief.get("guardrail")
        or "Pause, split, or summarize before the same driver dominates the run."
    )
    prompt = str(brief.get("copy_prompt") or "").strip()
    if not prompt:
        prompt = "\n".join(
            [
                "Next Codex run plan:",
                f"- Try: {habit}",
                f"- Watch: {watch}",
                f"- Target: move {metric} from {current} toward {target}",
                f"- Guardrail: {guardrail}",
            ]
        )
    items = [
        ("Try", habit),
        ("Watch", watch),
        ("Target", f"{metric}: {current} -> {target}"),
        ("Guardrail", guardrail),
    ]
    item_html = []
    for label, value in items:
        item_html.append(
            '<div class="co-next-run-brief-item">'
            f"<strong>{html.escape(label)}</strong>"
            f"<span>{html.escape(value)}</span>"
            "</div>"
        )
    return "\n".join(
        [
            '<section class="co-next-run-brief">',
            "  <h3>Next run brief</h3>",
            "  <p>Copy this aggregate-only plan into the next Codex run before exporting comparison evidence.</p>",
            '  <div class="co-next-run-brief-grid">',
            *[f"    {item}" for item in item_html],
            "  </div>",
            '  <div class="co-next-run-brief-item co-next-run-brief-prompt">',
            "    <strong>Copy prompt</strong>",
            f"    <code>{html.escape(prompt)}</code>",
            "  </div>",
            "</section>",
        ]
    )


def feedback_handoff_html(handoff: object) -> str:
    if not isinstance(handoff, dict):
        return ""
    runbook = str(handoff.get("runbook") or "docs/PUBLIC_TOUR_FEEDBACK.md")
    issue_template = str(
        handoff.get("issue_template")
        or ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
    )
    evidence_rule = str(
        handoff.get("evidence_rule")
        or "Use synthetic or reviewed-redacted aggregate evidence only."
    )
    safe_sources = handoff.get("safe_sources")
    do_not_collect = handoff.get("do_not_collect")
    safe_source_text = (
        "; ".join(str(item) for item in safe_sources if isinstance(item, str) and item)
        if isinstance(safe_sources, list)
        else "Report and comparison downloads"
    )
    do_not_collect_text = (
        "; ".join(
            str(item) for item in do_not_collect if isinstance(item, str) and item
        )
        if isinstance(do_not_collect, list)
        else "Private prompts; tool output; local paths"
    )
    return "\n".join(
        [
            '<section class="co-feedback-handoff">',
            "  <h3>Safe feedback handoff</h3>",
            "  <p>Use these boundaries before sharing dashboard observations or downloaded artifacts.</p>",
            '  <div class="co-feedback-grid">',
            '    <div class="co-feedback-item"><strong>Runbook</strong>',
            f"    <code>{html.escape(runbook)}</code></div>",
            '    <div class="co-feedback-item"><strong>Issue template</strong>',
            f"    <code>{html.escape(issue_template)}</code></div>",
            '    <div class="co-feedback-item"><strong>Evidence rule</strong>',
            f"    <span>{html.escape(evidence_rule)}</span></div>",
            '    <div class="co-feedback-item"><strong>Safe sources</strong>',
            f"    <span>{html.escape(safe_source_text)}</span></div>",
            '    <div class="co-feedback-item"><strong>Do not collect</strong>',
            f"    <span>{html.escape(do_not_collect_text)}</span></div>",
            "  </div>",
            "</section>",
        ]
    )


def report_ingest_scope_warning_html(report: dict[str, object]) -> str:
    scope = report.get("ingest_scope")
    if not isinstance(scope, dict):
        return ""
    warning = scope.get("warning")
    if not isinstance(warning, str) or not warning:
        return ""
    return (
        '<div class="co-report-scope">'
        f"<strong>Ingest scope:</strong> {html.escape(warning)}"
        "</div>"
    )


def sampled_ingest_coverage_html(scope: object, db_path: str) -> str:
    if not isinstance(scope, dict) or scope.get("sampled") is not True:
        return ""
    counts = scope.get("counts")
    scan_limit = scope.get("scan_limit")
    if not isinstance(counts, dict) or not isinstance(scan_limit, dict):
        return ""
    matched = int(counts.get("files_matched") or 0)
    seen = int(counts.get("files_seen") or 0)
    deferred = int(counts.get("files_skipped_by_limit") or 0)
    threads = int(counts.get("threads") or 0)
    events = int(counts.get("events") or 0)
    newest_files = int(scan_limit.get("newest_files") or seen or 1)
    coverage = round(seen / matched * 100, 1) if matched > 0 else 0.0
    next_limit = min(matched, max(newest_files + 1, newest_files * 2))
    if matched and next_limit > newest_files:
        command = (
            "codex-observe ingest ~/.codex/sessions "
            f"--newest-files {next_limit} --db {command_arg(db_path)}"
        )
        command_label = f"Expand to {fmt_int(next_limit)} newest files"
    else:
        command = f"codex-observe ingest ~/.codex/sessions --db {command_arg(db_path)}"
        command_label = "Run full ingest when you need complete coverage"
    facts = [
        (
            "Coverage",
            f"{coverage:.1f}%",
            f"{fmt_int(seen)} of {fmt_int(matched)} matched files",
        ),
        ("Deferred", fmt_int(deferred), "files outside this sample"),
        ("Threads", fmt_short(threads), "imported from sampled files"),
        ("Events", fmt_short(events), "parsed into this database"),
    ]
    fact_html = []
    for label, value, detail in facts:
        fact_html.append(
            '<div class="co-sample-coverage-fact">'
            f"<strong>{html.escape(label)}: {html.escape(value)}</strong>"
            f"<span>{html.escape(detail)}</span>"
            "</div>"
        )
    warning = scope.get("warning")
    warning_text = (
        str(warning)
        if isinstance(warning, str)
        else "This dashboard is based on a bounded ingest sample."
    )
    return "\n".join(
        [
            '<section class="co-sample-coverage">',
            "  <h3>Sample coverage</h3>",
            f"  <p>{html.escape(warning_text)}</p>",
            '  <div class="co-sample-coverage-grid">',
            *[f"    {item}" for item in fact_html],
            "  </div>",
            f"  <p><strong>{html.escape(command_label)}</strong></p>",
            f"  <code>{html.escape(command)}</code>",
            "</section>",
        ]
    )


def operator_briefing_html(
    triage: dict[str, object],
    success_target: dict[str, object],
    opportunities: pd.DataFrame,
) -> str:
    risk = html.escape(str(triage.get("risk_level") or "unknown").capitalize())
    driver = html.escape(
        str(triage.get("primary_driver") or "No high-signal diagnostic")
    )
    action = html.escape(
        str(triage.get("next_action") or "Inspect the largest thread.")
    )
    metric = html.escape(str(success_target.get("metric") or "total_tokens"))
    current = html.escape(str(success_target.get("current") or "unknown"))
    target = html.escape(str(success_target.get("target") or "unknown"))
    if opportunities.empty:
        opportunity = "No aggregate opportunity crossed review thresholds."
        scale = "Keep collecting evidence until a cost driver emerges."
    else:
        first = opportunities.iloc[0]
        opportunity = html.escape(str(first.get("Habit") or "Inspect the top driver."))
        scale = html.escape(str(first.get("Scale") or "No scale available."))

    return "\n".join(
        [
            '<section class="co-briefing">',
            "  <div>",
            '    <div class="co-briefing-label">Operator briefing</div>',
            f"    <h3>{risk} risk: {driver}</h3>",
            f"    <p>{action}</p>",
            "  </div>",
            '  <div class="co-briefing-grid">',
            '    <div class="co-briefing-fact">',
            "      <strong>Best next habit</strong>",
            f"      <p>{opportunity}</p>",
            f"      <p>{scale}</p>",
            "    </div>",
            '    <div class="co-briefing-fact">',
            "      <strong>Proof target</strong>",
            f"      <p>{metric}: {current} -> {target}</p>",
            "    </div>",
            "  </div>",
            "</section>",
        ]
    )


def pct_of_total(value: object, total: object) -> float:
    try:
        numerator = float(value or 0)
        denominator = float(total or 0)
    except (TypeError, ValueError):
        return 0.0
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def safe_download_stem(value: object, fallback: str) -> str:
    raw_value = str(value or fallback)
    safe_value = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-" for char in raw_value
    ).strip("-")
    return safe_value or fallback


def report_download_payloads(report: dict[str, object]) -> dict[str, dict[str, str]]:
    session = report.get("session", {})
    safe_session_id = safe_download_stem(
        session.get("session_id") if isinstance(session, dict) else None,
        "selected-session",
    )
    base = f"codex-observe-{safe_session_id}-report"
    return {
        "markdown": {
            "filename": f"{base}.md",
            "data": report_markdown(report),
            "mime": "text/markdown",
        },
        "json": {
            "filename": f"{base}.json",
            "data": report_json(report),
            "mime": "application/json",
        },
    }


def comparison_download_payloads(
    comparison: dict[str, object],
) -> dict[str, dict[str, str]]:
    before = comparison.get("before", {})
    after = comparison.get("after", {})
    before_id = safe_download_stem(
        before.get("session_id") if isinstance(before, dict) else None,
        "before",
    )
    after_id = safe_download_stem(
        after.get("session_id") if isinstance(after, dict) else None,
        "after",
    )
    base = f"codex-observe-{before_id}-to-{after_id}-comparison"
    return {
        "markdown": {
            "filename": f"{base}.md",
            "data": comparison_markdown(comparison),
            "mime": "text/markdown",
        },
        "json": {
            "filename": f"{base}.json",
            "data": comparison_json(comparison),
            "mime": "application/json",
        },
    }


def comparison_delta_cards_html(comparison: dict[str, object], limit: int = 4) -> str:
    cards = []
    metrics = comparison.get("metrics")
    if not isinstance(metrics, list):
        return ""
    changed_metrics = [
        metric
        for metric in metrics
        if isinstance(metric, dict)
        and str(metric.get("direction") or "unchanged") != "unchanged"
    ]
    ranked = sorted(
        changed_metrics or [metric for metric in metrics if isinstance(metric, dict)],
        key=lambda metric: abs(int(metric.get("delta") or 0)),
        reverse=True,
    )
    selected_metrics = ranked[:limit]
    snapshot_metric = next(
        (
            metric
            for metric in ranked
            if str(metric.get("metric") or "") == "usage_snapshots"
            or str(metric.get("label") or "") == "Usage snapshots"
        ),
        None,
    )
    if snapshot_metric and snapshot_metric not in selected_metrics:
        if len(selected_metrics) >= limit and selected_metrics:
            selected_metrics[-1] = snapshot_metric
        else:
            selected_metrics.append(snapshot_metric)
    for metric in selected_metrics:
        label = html.escape(
            str(metric.get("label") or metric.get("metric") or "Metric")
        )
        before = html.escape(fmt_short(metric.get("before", 0)))
        after = html.escape(fmt_short(metric.get("after", 0)))
        delta = html.escape(fmt_short(metric.get("delta", 0)))
        direction = html.escape(str(metric.get("direction") or "unchanged"))
        delta_pct = metric.get("delta_pct")
        pct = ""
        if delta_pct is not None:
            pct = f" ({html.escape(str(delta_pct))}%)"
        cards.append(
            '<div class="co-comparison-delta">'
            f"<strong>{label}</strong>"
            f"<span>{before} -> {after}</span>"
            f"<span>{direction}: {delta}{pct}</span>"
            "</div>"
        )
    if not cards:
        return ""
    return '<div class="co-comparison-deltas">' + "".join(cards) + "</div>"


def comparison_followup_html(comparison: dict[str, object]) -> str:
    templates = comparison.get("next_command_templates")
    if not isinstance(templates, list):
        return ""
    command = next(
        (str(item) for item in templates if isinstance(item, str) and item), ""
    )
    if not command:
        return ""
    return (
        '<div class="co-comparison-followup">'
        "<strong>Next validation command</strong>"
        f"<code>{html.escape(command)}</code>"
        "</div>"
    )


def comparison_review_path_html(comparison: dict[str, object], limit: int = 5) -> str:
    review_path = comparison.get("review_path")
    if not isinstance(review_path, list):
        return ""
    items = []
    for step in review_path[:limit]:
        if not isinstance(step, dict):
            continue
        label = str(step.get("label") or "").strip()
        command = str(step.get("command") or "").strip()
        success = str(step.get("success_check") or "").strip()
        if not label and not command and not success:
            continue
        body = command or success
        success_part = (
            f"<span>{html.escape(success)}</span>"
            if success and success != body
            else ""
        )
        items.append(
            "<li>"
            f"<strong>{html.escape(label or 'Review step')}</strong>"
            f"<code>{html.escape(body)}</code>"
            f"{success_part}"
            "</li>"
        )
    if not items:
        return ""
    return (
        '<div class="co-comparison-review-path">'
        "<strong>Comparison review path</strong>"
        "<ol>" + "".join(items) + "</ol>"
        "</div>"
    )


def comparison_ingest_scope_warning_html(comparison: dict[str, object]) -> str:
    scope = comparison.get("ingest_scope")
    if not isinstance(scope, dict):
        return ""
    warning = scope.get("warning")
    if not isinstance(warning, str) or not warning:
        return ""
    return (
        '<div class="co-comparison-scope">'
        f"<strong>Ingest scope:</strong> {html.escape(warning)}"
        "</div>"
    )


def comparison_preview_html(comparison: dict[str, object]) -> str:
    triage = comparison.get("triage_risk", {})
    opportunity = comparison.get("opportunity_change", {})
    verdict = html.escape(str(comparison.get("verdict") or "unknown"))
    headline = html.escape(
        str(
            comparison.get("headline", {}).get("headline")
            if isinstance(comparison.get("headline"), dict)
            else "No comparison headline available."
        )
    )
    recommendation = html.escape(
        str(comparison.get("recommendation") or "Inspect the reports manually.")
    )
    triage_direction = html.escape(
        str(triage.get("direction") if isinstance(triage, dict) else "unknown")
    )
    opportunity_summary = html.escape(
        str(
            opportunity.get("summary")
            if isinstance(opportunity, dict)
            else "No opportunity change summary available."
        )
    )
    return "\n".join(
        [
            '<section class="co-comparison-preview">',
            f"  <h3>Comparison quick read: <strong>{verdict}</strong></h3>",
            f"  <p>{headline}</p>",
            f"  <p><strong>Triage movement:</strong> {triage_direction}</p>",
            f"  <p><strong>Opportunity movement:</strong> {opportunity_summary}</p>",
            f"  <p><strong>Next step:</strong> {recommendation}</p>",
            comparison_ingest_scope_warning_html(comparison),
            comparison_delta_cards_html(comparison),
            comparison_review_path_html(comparison),
            comparison_followup_html(comparison),
            "</section>",
        ]
    )


def success_target_html(success_target: dict[str, object]) -> str:
    metric = html.escape(str(success_target.get("metric") or "total_tokens"))
    current = html.escape(str(success_target.get("current") or "unknown"))
    target = html.escape(str(success_target.get("target") or "unknown"))
    rationale = html.escape(
        str(
            success_target.get("rationale")
            or "Use the next run to validate the recommended habit."
        )
    )
    verification = html.escape(
        str(
            success_target.get("verification")
            or "Export the next run as report JSON and compare the target metric."
        )
    )
    return "\n".join(
        [
            '<section class="co-success-target">',
            '  <div class="co-success-target-kicker">Next run success target</div>',
            f"  <h3>{metric}: <strong>{current}</strong> -> <strong>{target}</strong></h3>",
            f"  <p>{rationale}</p>",
            f"  <p>{verification}</p>",
            "</section>",
        ]
    )


def metric_with_share(value: object, total: object, *, unit: str = "tokens") -> str:
    return f"{fmt_short(value)} {unit} ({pct_of_total(value, total):.1f}%)"


def render_wrapped_path(path: str) -> None:
    st.markdown(
        f'<div class="co-path">{html.escape(path)}</div>', unsafe_allow_html=True
    )


def render_app_header() -> None:
    st.markdown(
        """
<section class="co-hero">
  <p class="co-kicker">Offline Codex observability</p>
  <h1 class="co-title">Codex Observe</h1>
  <p class="co-subtitle">Understand where sessions spend context, which workers dominate cost, and which prompts are replayed across a run.</p>
</section>
""",
        unsafe_allow_html=True,
    )


def empty_state_commands_html(commands: list[tuple[str, str]]) -> str:
    items = []
    for label, command in commands:
        items.append(
            "\n".join(
                [
                    '<div class="co-empty-action">',
                    f"  <strong>{html.escape(label)}</strong>",
                    f"  <code>{html.escape(command)}</code>",
                    "</div>",
                ]
            )
        )
    return "\n".join(['<div class="co-empty-actions">', *items, "</div>"])


def render_empty_state(title: str, body: str) -> None:
    st.markdown(
        f"""
<section class="co-empty">
  <h2>{title}</h2>
  <p>{body}</p>
</section>
""",
        unsafe_allow_html=True,
    )


def order_conversations_for_review(
    conversations: pd.DataFrame, summaries: list[dict]
) -> pd.DataFrame:
    if conversations.empty or not summaries:
        return conversations
    order_by_session = {
        str(summary.get("session_id")): index for index, summary in enumerate(summaries)
    }
    risk_by_session = {
        str(summary.get("session_id")): str(summary.get("triage_risk") or "unknown")
        for summary in summaries
    }
    usage_snapshots_by_session = {
        str(summary.get("session_id")): int(summary.get("usage_snapshots") or 0)
        for summary in summaries
    }
    if not order_by_session:
        return conversations
    ordered = conversations.copy()
    fallback_start = len(order_by_session)
    ordered["triage_risk"] = [
        risk_by_session.get(str(session_id), "unknown")
        for session_id in ordered["session_id"]
    ]
    ordered["usage_snapshots"] = [
        usage_snapshots_by_session.get(str(session_id), 0)
        for session_id in ordered["session_id"]
    ]
    ordered["_review_order"] = [
        order_by_session.get(str(session_id), fallback_start + index)
        for index, session_id in enumerate(ordered["session_id"])
    ]
    ordered = ordered.sort_values("_review_order", kind="stable").drop(
        columns=["_review_order"]
    )
    return ordered.reset_index(drop=True)


def sidebar_risk_filter_options(conversations: pd.DataFrame) -> list[tuple[str, str]]:
    counts = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    if "triage_risk" in conversations.columns:
        for value in conversations["triage_risk"].fillna("unknown"):
            risk = str(value or "unknown").strip().lower()
            if risk == "moderate":
                risk = "medium"
            if risk not in counts:
                risk = "unknown"
            counts[risk] += 1
    options = [("All risks", "all")]
    options.extend(
        (f"{risk.capitalize()} risk ({counts[risk]})", risk)
        for risk in ["high", "medium", "low", "unknown"]
    )
    return options


def filter_conversations_by_risk(
    conversations: pd.DataFrame, risk_filter: str | None
) -> pd.DataFrame:
    if (
        not risk_filter
        or risk_filter == "all"
        or "triage_risk" not in conversations.columns
    ):
        return conversations
    normalized = risk_filter.strip().lower()
    risk_values = conversations["triage_risk"].fillna("unknown").astype(str).str.lower()
    risk_values = risk_values.replace({"moderate": "medium"})
    return conversations[risk_values == normalized].reset_index(drop=True)


def filter_conversations_by_search(
    conversations: pd.DataFrame, query: str | None
) -> pd.DataFrame:
    terms = [term for term in str(query or "").strip().lower().split() if term]
    if not terms or conversations.empty:
        return conversations
    searchable_columns = [
        column
        for column in ["session_id", "preview", "last_seen", "triage_risk"]
        if column in conversations.columns
    ]
    if not searchable_columns:
        return conversations
    haystack = (
        conversations[searchable_columns]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .str.lower()
    )
    mask = pd.Series(True, index=conversations.index)
    for term in terms:
        mask &= haystack.str.contains(term, regex=False)
    return conversations[mask].reset_index(drop=True)


def risk_marker(risk: str) -> str:
    normalized = risk.strip().lower()
    if normalized == "high":
        return "!!"
    if normalized in {"medium", "moderate"}:
        return "!"
    if normalized == "low":
        return "OK"
    return "??"


def conversation_button_label(row: pd.Series, selected: bool) -> str:
    preview = useful_text_preview(row.get("preview") or row["session_id"], 72)
    risk = str(row.get("triage_risk") or "unknown").strip().lower()
    risk_label = f"{risk.capitalize()} risk"
    prefix = "> " if selected else ""
    return f"{prefix}{risk_marker(risk)} {risk_label} | {preview}"


def data_inventory_html(
    conversations: pd.DataFrame,
    threads: pd.DataFrame,
    usage: pd.DataFrame,
    tools: pd.DataFrame,
    messages: pd.DataFrame,
    events: pd.DataFrame,
) -> str:
    counts = [
        ("Conversations", len(conversations)),
        ("Threads", len(threads)),
        ("Usage", len(usage)),
        ("Tools", len(tools)),
        ("Messages", len(messages)),
        ("Events", len(events)),
    ]
    if threads.empty:
        action = "Re-run ingestion against a Codex session directory; no thread rows are available to analyze."
    elif usage.empty:
        action = "Check parser coverage for token usage payloads; cost charts need usage snapshots."
    elif messages.empty:
        action = "Inspect events first; transcript snippets are missing for this selected run."
    else:
        action = "Use these raw tables only to verify a specific aggregate finding from the guided tabs."
    fact_html = "".join(
        '<div class="co-inventory-brief-fact">'
        f"<strong>{html.escape(label)}</strong>"
        f"<span>{fmt_int(value)}</span>"
        "</div>"
        for label, value in counts
    )
    return "\n".join(
        [
            '<section class="co-inventory-brief">',
            "  <h3>Data inventory</h3>",
            f"  <p><strong>Inspect first:</strong> {html.escape(action)}</p>",
            f'  <div class="co-inventory-brief-grid">{fact_html}</div>',
            "</section>",
        ]
    )


def timeline_quick_read_html(
    jumps: pd.DataFrame, compactions: pd.DataFrame, total_tokens: object
) -> str:
    if jumps.empty and compactions.empty:
        return ""
    jump_tokens = 0
    jump_label = "No token jump captured"
    jump_timestamp = "unknown time"
    if not jumps.empty:
        jump = jumps.sort_values("delta_input_tokens", ascending=False).iloc[0]
        jump_tokens = int(jump.get("delta_input_tokens") or 0)
        jump_label = html.escape(str(jump.get("label") or "unknown thread"))
        jump_timestamp = html.escape(str(jump.get("timestamp") or "unknown time"))
    compaction_count = int(len(compactions)) if not compactions.empty else 0
    share = pct_of_total(jump_tokens, total_tokens)
    if jump_tokens >= 10_000:
        action = "Open the rows around the largest jump and look for pasted context, broad file reads, or bulky tool output."
    elif compaction_count:
        action = "Inspect the compaction boundary first; it marks where the run outgrew its working context."
    else:
        action = "Use this tab to find the first meaningful context-growth step before changing workflow."
    return "\n".join(
        [
            '<section class="co-timeline-brief">',
            "  <h3>Timeline quick read</h3>",
            f"  <p><strong>Inspect first:</strong> {html.escape(action)}</p>",
            f"  <p><strong>Largest jump:</strong> {jump_label} at {jump_timestamp} added {fmt_short(jump_tokens)} input tokens ({share:.1f}% of run) | <strong>Compactions:</strong> {fmt_int(compaction_count)}</p>",
            "</section>",
        ]
    )


def duplication_quick_read_html(
    duplicated_blocks: pd.DataFrame, total_tokens: object
) -> str:
    if duplicated_blocks.empty:
        return ""
    dup = duplicated_blocks.copy()
    if "approx_tokens_replayed" not in dup.columns:
        dup["approx_tokens_replayed"] = 0
    dup["approx_tokens_replayed"] = pd.to_numeric(
        dup["approx_tokens_replayed"], errors="coerce"
    ).fillna(0)
    replayed = int(dup["approx_tokens_replayed"].sum())
    if replayed <= 0:
        return ""
    top = dup.sort_values("approx_tokens_replayed", ascending=False).iloc[0]
    label = html.escape(str(top.get("label") or "repeated block"))
    seen = int(top.get("seen") or 0)
    threads = int(top.get("threads") or 0)
    share = pct_of_total(replayed, total_tokens)
    if replayed >= 10_000:
        action = "Move the top repeated block into a stable file or summary and point workers to it once."
    elif threads >= 3:
        action = "Check why this block is crossing thread boundaries before launching more workers."
    else:
        action = "Review the top repeated block and decide whether it should be referenced instead of replayed."
    return "\n".join(
        [
            '<section class="co-duplication-brief">',
            "  <h3>Duplication quick read</h3>",
            f"  <p><strong>Inspect first:</strong> {html.escape(action)}</p>",
            f"  <p><strong>Replay estimate:</strong> {fmt_short(replayed)} tokens ({share:.1f}% of run) | <strong>Top block:</strong> {label} seen {fmt_int(seen)} times across {fmt_int(threads)} threads</p>",
            "</section>",
        ]
    )


def tool_quick_read_html(tools: pd.DataFrame) -> str:
    if tools.empty:
        return ""
    tool_rows = tools.copy()
    if "output_chars" not in tool_rows.columns:
        tool_rows["output_chars"] = 0
    tool_rows["output_chars"] = pd.to_numeric(
        tool_rows["output_chars"], errors="coerce"
    ).fillna(0)
    total_calls = int(len(tool_rows))
    total_output = int(tool_rows["output_chars"].sum())
    largest = tool_rows.sort_values("output_chars", ascending=False).iloc[0]
    largest_tool = html.escape(str(largest.get("tool_name") or "unknown tool"))
    largest_output = int(largest.get("output_chars") or 0)
    noisy_share = pct_of_total(largest_output, total_output)
    if largest_output >= 20_000:
        action = "Narrow this command or filter its output before feeding results back into the thread."
    elif total_calls >= 20:
        action = "Batch related tool calls and inspect repeated commands before replaying results."
    elif total_output:
        action = "Start with the largest output and decide whether the next run needs a tighter command."
    else:
        action = "Tool count is visible, but no captured output volume crossed a review threshold."
    return "\n".join(
        [
            '<section class="co-tool-brief">',
            "  <h3>Tool quick read</h3>",
            f"  <p><strong>Inspect first:</strong> {html.escape(action)}</p>",
            f"  <p><strong>Calls:</strong> {fmt_int(total_calls)} | <strong>Captured output:</strong> {fmt_short(total_output)} chars | <strong>Largest output:</strong> {largest_tool} at {fmt_short(largest_output)} chars ({noisy_share:.1f}% of captured output)</p>",
            "</section>",
        ]
    )


def thread_brief_html(selected_thread: pd.Series, total_tokens: object) -> str:
    label = html.escape(str(selected_thread.get("label") or "Selected thread"))
    kind = html.escape(str(selected_thread.get("kind") or "unknown"))
    tokens = int(selected_thread.get("final_total_tokens") or 0)
    uncached = int(selected_thread.get("final_uncached_input_tokens") or 0)
    tools = int(selected_thread.get("tool_call_count") or 0)
    share = pct_of_total(tokens, total_tokens)
    if share >= 50:
        action = (
            "Shorten or split this thread first; it dominates the run's context budget."
        )
    elif uncached >= 10_000:
        action = "Gate fresh context before this thread starts; uncached input is the main cost to reduce."
    elif tools:
        action = "Inspect this thread's tool outputs and narrow bulky commands before replaying results."
    else:
        action = (
            "Review this thread's timeline for context jumps before changing workflow."
        )
    facts = [
        ("Kind", kind),
        ("Total", f"{fmt_short(tokens)} tokens"),
        ("Run share", f"{share:.1f}%"),
        ("Uncached", f"{fmt_short(uncached)} tokens"),
        ("Tools", fmt_int(tools)),
    ]
    fact_html = "".join(
        '<div class="co-thread-brief-fact">'
        f"<strong>{html.escape(name)}</strong>"
        f"<span>{html.escape(str(value))}</span>"
        "</div>"
        for name, value in facts
    )
    return "\n".join(
        [
            '<section class="co-thread-brief">',
            f"  <h3>Thread brief: {label}</h3>",
            f"  <p><strong>Inspect first:</strong> {html.escape(action)}</p>",
            f'  <div class="co-thread-brief-grid">{fact_html}</div>',
            "</section>",
        ]
    )


def load_events_for_session(db: str, session_id: str) -> pd.DataFrame:
    return read_sql(
        db,
        """
        SELECT e.*
        FROM events e
        JOIN threads t ON t.thread_id = e.thread_id
        WHERE t.session_id=?
        ORDER BY e.timestamp, e.idx
    """,
        (session_id,),
    )


def load_messages_for_session(db: str, session_id: str) -> pd.DataFrame:
    return read_sql(
        db,
        """
        SELECT m.*
        FROM messages m
        JOIN threads t ON t.thread_id = m.thread_id
        WHERE t.session_id=?
        ORDER BY m.timestamp
    """,
        (session_id,),
    )


def render_agent_detail(
    selected_thread: pd.Series,
    threads: pd.DataFrame,
    usage: pd.DataFrame,
    tools: pd.DataFrame,
    messages: pd.DataFrame,
    events: pd.DataFrame,
) -> None:
    tid = selected_thread["thread_id"]
    st.subheader(selected_thread["label"])
    total_thread_tokens = (
        threads["final_total_tokens"].fillna(0).sum() if not threads.empty else 0
    )
    st.markdown(
        thread_brief_html(selected_thread, total_thread_tokens),
        unsafe_allow_html=True,
    )
    render_metric_grid(
        [
            ("Kind", selected_thread["kind"]),
            ("Input", fmt_short(selected_thread["final_input_tokens"])),
            ("Uncached", fmt_short(selected_thread["final_uncached_input_tokens"])),
            ("Tools", fmt_int(selected_thread["tool_call_count"])),
            ("Events", fmt_int(selected_thread["event_count"])),
            ("Cache", f"{selected_thread['cache_pct']:.1f}%"),
        ]
    )

    goal = worker_goal(messages, events, tid)
    if goal:
        st.markdown("**Likely goal / launch prompt**")
        st.info(goal)

    ut = usage[usage["thread_id"] == tid].copy()
    if not ut.empty:
        st.markdown("**Token timeline for this thread**")
        ut["timestamp"] = pd.to_datetime(ut["timestamp"], errors="coerce")
        st.line_chart(
            ut.set_index("timestamp")[
                [
                    "input_tokens",
                    "cached_input_tokens",
                    "uncached_input_tokens",
                    "output_tokens",
                    "reasoning_tokens",
                ]
            ]
        )
        jumps = token_jumps_df(ut, threads, limit=10)
        if not jumps.empty:
            st.markdown("**Largest jumps in this thread**")
            st.dataframe(jumps, width="stretch", hide_index=True)

    comps = compactions_df(events[events["thread_id"] == tid], usage, threads)
    if not comps.empty:
        st.markdown("**Context compactions in this thread**")
        st.dataframe(comps, width="stretch", hide_index=True)

    tt = tools[tools["thread_id"] == tid].copy()
    if not tt.empty:
        st.markdown("**Tools in this thread**")
        by_tool = (
            tt.groupby("tool_name", dropna=False)
            .agg(calls=("call_id", "count"), output_chars=("output_chars", "sum"))
            .reset_index()
            .sort_values("calls", ascending=False)
        )
        st.dataframe(by_tool, width="stretch", hide_index=True)
        render_capped_dataframe(
            tt,
            columns=[
                "timestamp",
                "tool_name",
                "command",
                "workdir",
                "output_chars",
                "success",
            ],
        )

    mm = messages[messages["thread_id"] == tid].copy()
    if not mm.empty:
        st.markdown("**Messages / transcript snippets**")
        show = mm.copy()
        show["preview"] = show["text"].map(lambda x: useful_text_preview(x, 500))
        st.dataframe(
            show[
                [
                    "timestamp",
                    "role",
                    "source",
                    "char_count",
                    "approx_tokens",
                    "preview",
                ]
            ].tail(50),
            width="stretch",
            hide_index=True,
        )


def main() -> None:
    args = parse_args()
    db = str(Path(args.db).expanduser())
    st.set_page_config(page_title="Codex Observe", layout="wide")
    st.markdown(dashboard_css(), unsafe_allow_html=True)
    render_app_header()

    if not Path(db).exists():
        render_empty_state(
            "No database found",
            "Ingest Codex session logs first, then refresh this dashboard.",
        )
        st.markdown(
            empty_state_commands_html(
                [
                    (
                        "Try synthetic data",
                        f"codex-observe demo --serve --db {db} --host 127.0.0.1 --port 8501",
                    ),
                    (
                        "Ingest private logs locally",
                        f"codex-observe ingest ~/.codex/sessions --db {db}",
                    ),
                    ("Check database health", f"codex-observe doctor --db {db}"),
                ]
            ),
            unsafe_allow_html=True,
        )
        return

    conversations = read_sql(
        db,
        """
        SELECT c.*, COALESCE(tc.sidebar_tool_calls, 0) AS sidebar_tool_calls,
        COALESCE((
            SELECT substr(m.text, 1, 140)
            FROM messages m
            JOIN threads t ON t.thread_id = m.thread_id
            WHERE t.session_id = c.session_id
              AND m.role = 'user'
              AND length(trim(m.text)) > 0
              AND m.text NOT LIKE '# AGENTS.md instructions%'
              AND m.text NOT LIKE '<environment_context>%'
              AND m.text NOT LIKE '<INSTRUCTIONS>%'
              AND m.text NOT LIKE 'We need modify%'
              AND m.text NOT LIKE 'We need inspect%'
              AND m.text NOT LIKE 'The following is the Codex agent history%'
            ORDER BY m.timestamp ASC
            LIMIT 1
        ), c.session_id) AS preview
        FROM conversations c
        LEFT JOIN (
            SELECT session_id, COALESCE(SUM(tool_call_count), 0) AS sidebar_tool_calls
            FROM threads
            GROUP BY session_id
        ) tc ON tc.session_id = c.session_id
        ORDER BY c.last_seen DESC
    """,
    )
    if conversations.empty:
        render_empty_state(
            "No conversations imported yet",
            "The database exists, but it does not contain any parsed conversations. Re-run ingestion against a directory that contains Codex JSONL session files.",
        )
        st.markdown(
            empty_state_commands_html(
                [
                    (
                        "Try synthetic data",
                        f"codex-observe demo --serve --db {db} --host 127.0.0.1 --port 8501",
                    ),
                    (
                        "Ingest private logs locally",
                        f"codex-observe ingest ~/.codex/sessions --db {db}",
                    ),
                    ("Check database health", f"codex-observe doctor --db {db}"),
                ]
            ),
            unsafe_allow_html=True,
        )
        return

    summaries = session_summaries(db)
    risk_distribution = session_risk_distribution(summaries)
    ingest_scope = latest_ingest_scope(db)
    conversations = order_conversations_for_review(conversations, summaries)

    with st.sidebar:
        st.header("Database")
        render_wrapped_path(db)
        st.metric("Conversations", len(conversations))
        search_query = st.text_input(
            "Find session",
            placeholder="Search label, date, risk, or session fragment",
            key="sidebar_session_search",
        )
        risk_filter_options = sidebar_risk_filter_options(conversations)
        risk_filter_labels = [label for label, _value in risk_filter_options]
        selected_risk_label = st.selectbox(
            "Risk filter", risk_filter_labels, index=0, key="sidebar_risk_filter"
        )
        risk_filter = dict(risk_filter_options)[selected_risk_label]
        filtered_conversations = filter_conversations_by_risk(
            conversations, risk_filter
        )
        filtered_conversations = filter_conversations_by_search(
            filtered_conversations, search_query
        )
        active_filters = []
        if str(search_query or "").strip():
            active_filters.append("search")
        if risk_filter != "all":
            active_filters.append("risk")
        if active_filters:
            st.caption(
                f"Showing {len(filtered_conversations)} of {len(conversations)} conversations after "
                f"{', '.join(active_filters)} filter"
            )
        if filtered_conversations.empty:
            st.info("No conversations match the current sidebar filters.")
            st.stop()
        elif st.session_state.get("selected_session_id") not in set(
            filtered_conversations["session_id"]
        ):
            st.session_state["selected_session_id"] = filtered_conversations.iloc[0][
                "session_id"
            ]
        st.markdown("### Conversations")
        if (
            "selected_session_id" not in st.session_state
            and not filtered_conversations.empty
        ):
            st.session_state["selected_session_id"] = filtered_conversations.iloc[0][
                "session_id"
            ]
        last_date = None
        for _, row in filtered_conversations.iterrows():
            day = str(row.get("last_seen") or "")[:10]
            if day != last_date:
                st.markdown(f"#### {day or 'Unknown date'}")
                last_date = day
            selected = row["session_id"] == st.session_state["selected_session_id"]
            label = conversation_button_label(row, selected)
            if st.button(label, key=f"conv_{row['session_id']}", width="stretch"):
                st.session_state["selected_session_id"] = row["session_id"]
                st.rerun()
            if selected:
                bits = []
                t = sidebar_time_label(row.get("last_seen"))
                bits.append(
                    f"{str(row.get('triage_risk') or 'unknown').capitalize()} risk"
                )
                if t:
                    bits.append(t)
                bits.append(f"{int(row.get('thread_count') or 0)} threads")
                bits.append(f"{fmt_int(row.get('sidebar_tool_calls') or 0)} tools")
                bits.append(f"{fmt_int(row.get('usage_snapshots') or 0)} snapshots")
                bits.append(f"{fmt_short(row.get('total_tokens') or 0)} tokens")
                st.caption(" | ".join(bits))
        session_id = st.session_state["selected_session_id"]

    conv = conversations[conversations.session_id == session_id].iloc[0]
    threads = read_sql(
        db,
        "SELECT * FROM threads WHERE session_id=? ORDER BY created_at, first_seen",
        (session_id,),
    )
    usage = read_sql(
        db,
        "SELECT * FROM usage_snapshots WHERE thread_id IN (SELECT thread_id FROM threads WHERE session_id=?) ORDER BY timestamp, idx",
        (session_id,),
    )
    tools = read_sql(
        db,
        "SELECT * FROM tool_calls WHERE thread_id IN (SELECT thread_id FROM threads WHERE session_id=?) ORDER BY timestamp",
        (session_id,),
    )
    events = load_events_for_session(db, session_id)
    messages = load_messages_for_session(db, session_id)

    threads = prepare_threads(threads)
    usage = numericize(
        usage,
        [
            "idx",
            "input_tokens",
            "cached_input_tokens",
            "uncached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
            "last_input_tokens",
            "last_total_tokens",
        ],
    )
    tools = numericize(tools, ["timeout_ms", "success", "duration_ms", "output_chars"])

    cache_pct = (
        int(conv.total_cached_input_tokens or 0) / int(conv.total_input_tokens or 1)
    ) * 100
    workers = int((threads["kind"] == "worker").sum())
    guardians = int((threads["kind"] == "guardian").sum())
    explorers = int((threads["kind"] == "explorer").sum())
    tool_total = int(threads["tool_call_count"].fillna(0).sum())
    largest_thread = (
        threads.sort_values("final_total_tokens", ascending=False).iloc[0]
        if not threads.empty
        else None
    )
    compactions = compactions_df(events, usage, threads)

    total_tokens = int(conv.total_tokens or 0)
    largest_thread_tokens = (
        largest_thread["final_total_tokens"] if largest_thread is not None else 0
    )

    render_metric_grid(
        [
            ("Threads", fmt_int(conv.thread_count)),
            ("Workers", fmt_int(workers)),
            ("Explorers", fmt_int(explorers)),
            ("Guardians", fmt_int(guardians)),
            ("Tools", fmt_int(tool_total)),
            ("Cache hit", f"{cache_pct:.1f}%"),
            ("Compactions", fmt_int(len(compactions))),
            (
                "Largest thread",
                metric_with_share(largest_thread_tokens, total_tokens),
            ),
            (
                "Uncached input",
                metric_with_share(conv.total_uncached_input_tokens, total_tokens),
            ),
        ]
    )

    duplicated_blocks = read_sql(
        db,
        """
        SELECT label, block_hash, COUNT(*) AS seen, COUNT(DISTINCT thread_id) AS threads,
               MAX(approx_tokens) AS approx_tokens_each,
               SUM(approx_tokens) AS approx_tokens_replayed,
               MIN(preview) AS preview
        FROM prompt_blocks
        WHERE thread_id IN (SELECT thread_id FROM threads WHERE session_id=?)
        GROUP BY label, block_hash
        HAVING COUNT(*) > 1
        ORDER BY approx_tokens_replayed DESC
        LIMIT 300
    """,
        (session_id,),
    )

    diagnostics = diagnostics_df(threads, usage, events, tools, duplicated_blocks)
    playbook = next_run_playbook_df(diagnostics)
    repeated_prompt_tokens = 0
    if (
        not duplicated_blocks.empty
        and "approx_tokens_replayed" in duplicated_blocks.columns
    ):
        repeated_prompt_tokens = int(
            pd.to_numeric(duplicated_blocks["approx_tokens_replayed"], errors="coerce")
            .fillna(0)
            .sum()
        )
    largest_tool_output_chars = 0
    if not tools.empty and "output_chars" in tools.columns:
        largest_tool_output_chars = int(tools["output_chars"].fillna(0).max())
    triage = report_triage(
        {
            "summary": {
                "total_tokens": total_tokens,
                "largest_thread_share_pct": pct_of_total(
                    largest_thread_tokens, total_tokens
                ),
                "repeated_prompt_share_pct": pct_of_total(
                    repeated_prompt_tokens, total_tokens
                ),
                "uncached_input_share_pct": pct_of_total(
                    conv.total_uncached_input_tokens, total_tokens
                ),
                "largest_tool_output_chars": largest_tool_output_chars,
                "compactions": int(len(compactions)),
            },
            "headline": {
                "top_diagnostic": str(diagnostics.iloc[0]["Diagnostic"])
                if not diagnostics.empty
                else "No high-signal diagnostic",
                "recommendation": str(playbook.iloc[0]["Habit"])
                if not playbook.empty
                else "Inspect the largest thread before changing workflow.",
            },
        }
    )
    tab_overview, tab_agent, tab_timeline, tab_tools, tab_dup, tab_raw = st.tabs(
        [
            "Overview",
            "Agent detail",
            "Timeline & jumps",
            "Tools",
            "Duplication",
            "Raw tables",
        ]
    )

    success_summary = {
        "total_tokens": total_tokens,
        "largest_thread_tokens": largest_thread_tokens,
        "largest_thread_share_pct": pct_of_total(largest_thread_tokens, total_tokens),
        "repeated_prompt_tokens": repeated_prompt_tokens,
        "repeated_prompt_share_pct": pct_of_total(repeated_prompt_tokens, total_tokens),
        "uncached_input_tokens": int(conv.total_uncached_input_tokens or 0),
        "uncached_input_share_pct": pct_of_total(
            conv.total_uncached_input_tokens, total_tokens
        ),
        "largest_tool_output_chars": largest_tool_output_chars,
        "compactions": int(len(compactions)),
    }
    opportunities = opportunity_df(success_summary)
    success_target = report_success_target(
        {"summary": success_summary, "opportunities": opportunities.to_dict("records")}
    )

    with tab_overview:
        st.markdown(
            operator_briefing_html(triage, success_target, opportunities),
            unsafe_allow_html=True,
        )
        st.markdown(
            risk_distribution_html(risk_distribution),
            unsafe_allow_html=True,
        )
        st.markdown(
            sampled_ingest_coverage_html(ingest_scope, db),
            unsafe_allow_html=True,
        )
        comparison_options = [
            str(row["session_id"])
            for _, row in conversations.iterrows()
            if str(row["session_id"]) != str(session_id)
        ]
        st.markdown(
            review_path_html(success_target, has_comparison=bool(comparison_options)),
            unsafe_allow_html=True,
        )
        st.markdown(triage_card_html(triage), unsafe_allow_html=True)
        report = build_report(str(db), session_id)
        st.markdown(
            next_run_checklist_html(
                report.get("next_run_checklist") or report_next_run_checklist(report)
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            next_run_brief_html(
                report.get("next_run_brief") or report_next_run_brief(report)
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            feedback_handoff_html(report.get("feedback_handoff")),
            unsafe_allow_html=True,
        )
        st.markdown(
            report_ingest_scope_warning_html(report),
            unsafe_allow_html=True,
        )
        downloads = report_download_payloads(report)
        export_left, export_right = st.columns(2)
        with export_left:
            st.download_button(
                "Download report MD",
                downloads["markdown"]["data"],
                file_name=downloads["markdown"]["filename"],
                mime=downloads["markdown"]["mime"],
                width="stretch",
                key=f"download_report_md_{session_id}",
            )
        with export_right:
            st.download_button(
                "Download report JSON",
                downloads["json"]["data"],
                file_name=downloads["json"]["filename"],
                mime=downloads["json"]["mime"],
                width="stretch",
                key=f"download_report_json_{session_id}",
            )
        if comparison_options:
            st.subheader("Compare selected run")
            comparison_labels = {}
            for _, row in conversations.iterrows():
                candidate_id = str(row["session_id"])
                risk = str(row.get("triage_risk") or "unknown").capitalize()
                last_seen = sidebar_time_label(row.get("last_seen")) or "unknown time"
                tokens = fmt_short(row.get("total_tokens") or 0)
                comparison_labels[candidate_id] = (
                    f"{risk} risk | {last_seen} | {tokens} tokens | {candidate_id}"
                )
            baseline_session_id = st.selectbox(
                "Baseline run",
                comparison_options,
                format_func=lambda value: comparison_labels.get(value, value),
                key=f"comparison_baseline_{session_id}",
                width="stretch",
            )
            baseline_report = build_report(str(db), baseline_session_id)
            comparison = compare_reports(baseline_report, report)
            st.markdown(comparison_preview_html(comparison), unsafe_allow_html=True)
            comparison_downloads = comparison_download_payloads(comparison)
            compare_left, compare_right = st.columns(2)
            with compare_left:
                st.download_button(
                    "Download comparison MD",
                    comparison_downloads["markdown"]["data"],
                    file_name=comparison_downloads["markdown"]["filename"],
                    mime=comparison_downloads["markdown"]["mime"],
                    width="stretch",
                    key=f"download_comparison_md_{baseline_session_id}_{session_id}",
                )
            with compare_right:
                st.download_button(
                    "Download comparison JSON",
                    comparison_downloads["json"]["data"],
                    file_name=comparison_downloads["json"]["filename"],
                    mime=comparison_downloads["json"]["mime"],
                    width="stretch",
                    key=f"download_comparison_json_{baseline_session_id}_{session_id}",
                )
        st.subheader("Next run success target")
        st.markdown(success_target_html(success_target), unsafe_allow_html=True)
        st.subheader("Opportunity stack")
        if opportunities.empty:
            st.info("No aggregate opportunity crossed review thresholds yet.")
        else:
            st.markdown(opportunity_html(opportunities), unsafe_allow_html=True)
            with st.expander("Show opportunity table"):
                st.dataframe(opportunities, width="stretch", hide_index=True)

        st.subheader("What to inspect first")
        if diagnostics.empty:
            st.info(
                "No diagnostics available yet. This conversation may not have token snapshots, tools, or prompt blocks."
            )
        else:
            st.markdown(diagnostics_cards_html(diagnostics), unsafe_allow_html=True)
            with st.expander("Show diagnostic table"):
                st.dataframe(diagnostics, width="stretch", hide_index=True)

        st.subheader("Next run playbook")
        if playbook.empty:
            st.info(
                "No playbook yet. Run diagnostics against a conversation with token snapshots, tools, or repeated prompt blocks."
            )
        else:
            st.markdown(playbook_html(playbook), unsafe_allow_html=True)
            with st.expander("Show playbook table"):
                st.dataframe(playbook, width="stretch", hide_index=True)

        st.subheader("Why this run was expensive")
        st.dataframe(
            findings_df(threads, usage, events), width="stretch", hide_index=True
        )

        st.subheader("Conversation tree")
        st.code(build_tree(threads, session_id), language="text")

        st.subheader("Cost attribution by agent/thread")
        attrib = threads.sort_values("final_total_tokens", ascending=False).copy()
        total_tokens = float(attrib["final_total_tokens"].sum() or 1)
        attrib["share_pct"] = attrib["final_total_tokens"] / total_tokens * 100
        st.dataframe(
            attrib[
                [
                    "label",
                    "kind",
                    "final_total_tokens",
                    "final_uncached_input_tokens",
                    "tool_call_count",
                    "share_pct",
                    "cache_pct",
                ]
            ],
            width="stretch",
            hide_index=True,
        )
        st.bar_chart(
            attrib.set_index("label")[
                [
                    "final_uncached_input_tokens",
                    "final_cached_input_tokens",
                    "final_output_tokens",
                    "final_reasoning_tokens",
                ]
            ]
        )

        st.subheader("Cost attribution by role/source")
        role_summary = (
            threads.groupby("label", dropna=False)[
                [
                    "final_input_tokens",
                    "final_cached_input_tokens",
                    "final_uncached_input_tokens",
                    "final_output_tokens",
                    "final_reasoning_tokens",
                    "tool_call_count",
                ]
            ]
            .sum()
            .reset_index()
            .sort_values("final_input_tokens", ascending=False)
        )
        st.dataframe(role_summary, width="stretch", hide_index=True)

        st.subheader("Efficiency / overhead indicators")
        eff = threads.sort_values("input_per_output", ascending=False).copy()
        st.dataframe(
            eff[
                [
                    "label",
                    "kind",
                    "final_input_tokens",
                    "output_plus_reasoning",
                    "input_per_output",
                    "tokens_per_tool",
                    "tool_call_count",
                    "cache_pct",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

        st.subheader("Guardian overhead")
        gh = guardian_overhead_df(threads)
        if gh.empty:
            st.info("No guardian threads found in this conversation.")
        else:
            g_total_in = int(gh["final_input_tokens"].sum())
            g_total_out = int(
                (gh["final_output_tokens"] + gh["final_reasoning_tokens"]).sum()
            )
            gc1, gc2, gc3, gc4 = st.columns(4)
            gc1.metric("Guardian runs", fmt_int(len(gh)))
            gc2.metric("Guardian input", fmt_short(g_total_in))
            gc3.metric("Output + reasoning", fmt_short(g_total_out))
            gc4.metric(
                "Input/output ratio", fmt_short(g_total_in / max(g_total_out, 1))
            )
            st.dataframe(gh, width="stretch", hide_index=True)

    with tab_agent:
        st.subheader("Worker / thread detail")
        options = []
        for _, r in threads.sort_values(
            "final_total_tokens", ascending=False
        ).iterrows():
            options.append(
                (
                    f"{r['label']} | {fmt_short(r['final_total_tokens'])} | {r['thread_id'][-8:]}",
                    r["thread_id"],
                )
            )
        if options:
            selected_label = st.selectbox("Select a thread", [o[0] for o in options])
            selected_tid = dict(options)[selected_label]
            selected_thread = threads[threads["thread_id"] == selected_tid].iloc[0]
            render_agent_detail(
                selected_thread, threads, usage, tools, messages, events
            )

    with tab_timeline:
        jumps = token_jumps_df(usage, threads, limit=50)
        st.markdown(
            timeline_quick_read_html(jumps, compactions, total_tokens),
            unsafe_allow_html=True,
        )
        st.subheader("Spawn graph / thread lifecycle")
        lifecycle = threads[
            [
                "label",
                "kind",
                "thread_id",
                "parent_thread_id",
                "first_seen",
                "last_seen",
                "final_total_tokens",
                "tool_call_count",
            ]
        ].sort_values("first_seen")
        st.dataframe(lifecycle, width="stretch", hide_index=True)
        st.code(build_tree(threads, session_id), language="text")

        st.subheader("Largest token jumps")
        if jumps.empty:
            st.info("No token snapshots found.")
        else:
            st.dataframe(jumps, width="stretch", hide_index=True)

        st.subheader("Context growth snapshots")
        if usage.empty:
            st.info("No usage snapshots found.")
        else:
            timeline = usage.merge(
                threads[["thread_id", "label"]], on="thread_id", how="left"
            )
            timeline["timestamp"] = pd.to_datetime(
                timeline["timestamp"], errors="coerce"
            )
            st.line_chart(
                timeline.set_index("timestamp")[
                    [
                        "input_tokens",
                        "cached_input_tokens",
                        "uncached_input_tokens",
                        "output_tokens",
                        "reasoning_tokens",
                    ]
                ]
            )

        st.subheader("Context compactions")
        if compactions.empty:
            st.info("No context compaction events found.")
        else:
            st.dataframe(compactions, width="stretch", hide_index=True)

    with tab_tools:
        st.subheader("Tool calls")
        if tools.empty:
            st.info("No tool calls found in this conversation.")
        else:
            st.markdown(tool_quick_read_html(tools), unsafe_allow_html=True)
            by_tool = (
                tools.groupby("tool_name", dropna=False)
                .agg(calls=("call_id", "count"), output_chars=("output_chars", "sum"))
                .reset_index()
                .sort_values("calls", ascending=False)
            )
            st.subheader("Tool distribution")
            st.dataframe(by_tool, width="stretch", hide_index=True)
            st.bar_chart(by_tool.set_index("tool_name")["calls"])

            st.subheader("Tool calls by thread")
            tools_by_thread = (
                tools.groupby("thread_id")
                .agg(calls=("call_id", "count"), output_chars=("output_chars", "sum"))
                .reset_index()
            )
            tools_by_thread = tools_by_thread.merge(
                threads[["thread_id", "label", "kind", "final_total_tokens"]],
                on="thread_id",
                how="left",
            ).sort_values("calls", ascending=False)
            tools_by_thread["tokens_per_tool"] = tools_by_thread[
                "final_total_tokens"
            ] / tools_by_thread["calls"].replace(0, 1)
            st.dataframe(tools_by_thread, width="stretch", hide_index=True)

            st.subheader("Largest tool outputs")
            st.dataframe(
                tools.sort_values("output_chars", ascending=False)[
                    [
                        "timestamp",
                        "thread_id",
                        "tool_name",
                        "command",
                        "output_chars",
                        "success",
                    ]
                ].head(100),
                width="stretch",
                hide_index=True,
            )

            st.subheader("Raw tool calls")
            render_capped_dataframe(
                tools,
                columns=[
                    "timestamp",
                    "thread_id",
                    "tool_name",
                    "command",
                    "workdir",
                    "output_chars",
                    "success",
                ],
            )

    with tab_dup:
        st.subheader("Repeated prompt blocks")
        dup = duplicated_blocks
        if dup.empty:
            st.info(
                "No repeated large prompt blocks found with the current heuristics."
            )
        else:
            st.markdown(
                duplication_quick_read_html(dup, total_tokens),
                unsafe_allow_html=True,
            )
            d1, d2, d3 = st.columns(3)
            d1.metric(
                "Repeated approx tokens", fmt_short(dup["approx_tokens_replayed"].sum())
            )
            d2.metric("Repeated blocks", fmt_int(len(dup)))
            d3.metric("Threads involved", fmt_int(dup["threads"].max()))
            by_label = (
                dup.groupby("label")
                .agg(
                    blocks=("block_hash", "count"),
                    replayed_tokens=("approx_tokens_replayed", "sum"),
                    seen=("seen", "sum"),
                )
                .reset_index()
                .sort_values("replayed_tokens", ascending=False)
            )
            st.subheader("Duplication breakdown")
            st.dataframe(by_label, width="stretch", hide_index=True)
            st.bar_chart(by_label.set_index("label")["replayed_tokens"])
            st.subheader("Repeated blocks")
            st.dataframe(dup, width="stretch", hide_index=True)
        st.caption(
            "Duplication tokens are approximate text-fragment estimates. Authoritative usage totals still come from Codex token_count events."
        )

    with tab_raw:
        st.markdown(
            data_inventory_html(conversations, threads, usage, tools, messages, events),
            unsafe_allow_html=True,
        )
        st.subheader("Conversations")
        render_capped_dataframe(conversations)
        st.subheader("Threads")
        render_capped_dataframe(threads)
        st.subheader("Usage snapshots")
        render_capped_dataframe(usage)
        st.subheader("Events")
        render_capped_dataframe(events)


if __name__ == "__main__":
    main()
