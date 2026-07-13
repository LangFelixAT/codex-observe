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
    compare_reports,
    comparison_json,
    comparison_markdown,
    report_json,
    report_markdown,
    report_success_target,
    report_triage,
    session_summaries,
)


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

@media (max-width: 760px) {
  .co-briefing {
    grid-template-columns: 1fr;
  }
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
    if not order_by_session:
        return conversations
    ordered = conversations.copy()
    fallback_start = len(order_by_session)
    ordered["triage_risk"] = [
        risk_by_session.get(str(session_id), "unknown")
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


def risk_marker(risk: str) -> str:
    normalized = risk.strip().lower()
    if normalized == "high":
        return "!!"
    if normalized == "moderate":
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
        st.dataframe(
            tt[
                [
                    "timestamp",
                    "tool_name",
                    "command",
                    "workdir",
                    "output_chars",
                    "success",
                ]
            ],
            width="stretch",
            hide_index=True,
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

    conversations = order_conversations_for_review(conversations, session_summaries(db))

    with st.sidebar:
        st.header("Database")
        render_wrapped_path(db)
        st.metric("Conversations", len(conversations))
        st.markdown("### Conversations")
        if "selected_session_id" not in st.session_state:
            st.session_state["selected_session_id"] = conversations.iloc[0][
                "session_id"
            ]
        last_date = None
        for _, row in conversations.iterrows():
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
        st.markdown(triage_card_html(triage), unsafe_allow_html=True)
        report = build_report(str(db), session_id)
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
        comparison_options = [
            str(row["session_id"])
            for _, row in conversations.iterrows()
            if str(row["session_id"]) != str(session_id)
        ]
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
            st.dataframe(
                tools[
                    [
                        "timestamp",
                        "thread_id",
                        "tool_name",
                        "command",
                        "workdir",
                        "output_chars",
                        "success",
                    ]
                ],
                width="stretch",
                hide_index=True,
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
        st.dataframe(conversations, width="stretch", hide_index=True)
        st.subheader("Threads")
        st.dataframe(threads, width="stretch", hide_index=True)
        st.subheader("Usage snapshots")
        st.dataframe(usage, width="stretch", hide_index=True)
        st.subheader("Events")
        st.dataframe(events, width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
