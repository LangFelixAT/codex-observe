from __future__ import annotations

import pandas as pd

from codex_observe.analysis import (
    build_tree,
    diagnostics_cards_html,
    diagnostics_df,
    next_run_playbook_df,
    opportunity_df,
    opportunity_html,
    playbook_html,
    prepare_threads,
    role_label,
    thread_kind,
)
from codex_observe.dashboard import (
    comparison_download_payloads,
    comparison_preview_html,
    conversation_button_label,
    dashboard_css,
    duplication_quick_read_html,
    empty_state_commands_html,
    risk_marker,
    order_conversations_for_review,
    metric_with_share,
    operator_briefing_html,
    pct_of_total,
    report_download_payloads,
    triage_card_html,
    success_target_html,
    timeline_quick_read_html,
    thread_brief_html,
    tool_quick_read_html,
)


def test_order_conversations_for_review_uses_risk_aware_session_summaries() -> None:
    conversations = pd.DataFrame(
        [
            {
                "session_id": "newer-low",
                "last_seen": "2026-01-01T12:35:00Z",
                "preview": "newer low-risk follow-up",
            },
            {
                "session_id": "older-high",
                "last_seen": "2026-01-01T12:23:00Z",
                "preview": "older high-risk run",
            },
        ]
    )
    summaries = [
        {"session_id": "older-high", "triage_risk": "high"},
        {"session_id": "newer-low", "triage_risk": "low"},
    ]

    ordered = order_conversations_for_review(conversations, summaries)

    assert ordered["session_id"].tolist() == ["older-high", "newer-low"]
    assert ordered["triage_risk"].tolist() == ["high", "low"]
    assert "_review_order" not in ordered.columns


def test_conversation_button_label_includes_risk_and_selection_marker() -> None:
    row = pd.Series(
        {
            "session_id": "session-high",
            "preview": "Investigate a costly run with repeated context",
            "triage_risk": "high",
        }
    )

    assert conversation_button_label(row, selected=True) == (
        "> !! High risk | Investigate a costly run with repeated context"
    )
    assert conversation_button_label(row, selected=False) == (
        "!! High risk | Investigate a costly run with repeated context"
    )


def test_conversation_button_label_falls_back_to_session_id_and_unknown_risk() -> None:
    row = pd.Series({"session_id": "session-unknown", "preview": ""})

    assert conversation_button_label(row, selected=False) == (
        "?? Unknown risk | session-unknown"
    )


def test_risk_marker_makes_sidebar_risk_scannable() -> None:
    assert risk_marker("high") == "!!"
    assert risk_marker("moderate") == "!"
    assert risk_marker("low") == "OK"
    assert risk_marker("unknown") == "??"
    assert risk_marker("") == "??"


def test_thread_brief_html_summarizes_selected_thread_and_escapes() -> None:
    rendered = thread_brief_html(
        pd.Series(
            {
                "label": "Worker <Parser>",
                "kind": "worker",
                "final_total_tokens": 33_200,
                "final_uncached_input_tokens": 12_000,
                "tool_call_count": 3,
            }
        ),
        57_510,
    )

    assert 'class="co-thread-brief"' in rendered
    assert "Thread brief" in rendered
    assert "Worker &lt;Parser&gt;" in rendered
    assert "Shorten or split this thread first" in rendered
    assert "33.2k tokens" in rendered
    assert "57.7%" in rendered
    assert "12.0k tokens" in rendered
    assert "Worker <Parser>" not in rendered


def test_tool_quick_read_html_summarizes_noisy_tool_output_and_escapes() -> None:
    rendered = tool_quick_read_html(
        pd.DataFrame(
            [
                {"tool_name": "shell <run>", "output_chars": 25_000},
                {"tool_name": "search", "output_chars": 5_000},
            ]
        )
    )

    assert 'class="co-tool-brief"' in rendered
    assert "Tool quick read" in rendered
    assert "Narrow this command" in rendered
    assert "shell &lt;run&gt;" in rendered
    assert "30.0k chars" in rendered
    assert "25.0k chars" in rendered
    assert "83.3%" in rendered
    assert "shell <run>" not in rendered


def test_timeline_quick_read_html_summarizes_jump_and_escapes() -> None:
    rendered = timeline_quick_read_html(
        pd.DataFrame(
            [
                {
                    "label": "Worker <Builder>",
                    "timestamp": "2026-07-13T10:00:00Z",
                    "delta_input_tokens": 18_000,
                }
            ]
        ),
        pd.DataFrame([{"thread_id": "t1"}, {"thread_id": "t2"}]),
        60_000,
    )

    assert 'class="co-timeline-brief"' in rendered
    assert "Timeline quick read" in rendered
    assert "Open the rows around the largest jump" in rendered
    assert "Worker &lt;Builder&gt;" in rendered
    assert "18.0k input tokens" in rendered
    assert "30.0%" in rendered
    assert "Compactions:</strong> 2" in rendered
    assert "Worker <Builder>" not in rendered


def test_timeline_quick_read_html_handles_compaction_without_jumps() -> None:
    rendered = timeline_quick_read_html(
        pd.DataFrame(), pd.DataFrame([{"thread_id": "t1"}]), 10_000
    )

    assert "Timeline quick read" in rendered
    assert "Inspect the compaction boundary first" in rendered
    assert "No token jump captured" in rendered


def test_timeline_quick_read_html_returns_empty_string_without_evidence() -> None:
    assert timeline_quick_read_html(pd.DataFrame(), pd.DataFrame(), 1000) == ""


def test_tool_quick_read_html_returns_empty_string_without_tools() -> None:
    assert tool_quick_read_html(pd.DataFrame()) == ""


def test_duplication_quick_read_html_summarizes_replay_and_escapes() -> None:
    rendered = duplication_quick_read_html(
        pd.DataFrame(
            [
                {
                    "label": "AGENTS <root>",
                    "seen": 4,
                    "threads": 3,
                    "approx_tokens_replayed": 12_000,
                },
                {
                    "label": "handoff",
                    "seen": 2,
                    "threads": 2,
                    "approx_tokens_replayed": 3_000,
                },
            ]
        ),
        60_000,
    )

    assert 'class="co-duplication-brief"' in rendered
    assert "Duplication quick read" in rendered
    assert "Move the top repeated block" in rendered
    assert "AGENTS &lt;root&gt;" in rendered
    assert "15.0k tokens" in rendered
    assert "25.0%" in rendered
    assert "seen 4 times across 3 threads" in rendered
    assert "AGENTS <root>" not in rendered


def test_duplication_quick_read_html_returns_empty_string_without_replay() -> None:
    assert duplication_quick_read_html(pd.DataFrame(), 1000) == ""
    assert (
        duplication_quick_read_html(
            pd.DataFrame([{"label": "x", "approx_tokens_replayed": 0}]), 1000
        )
        == ""
    )


def test_thread_kind_classifies_root_worker_explorer_guardian_and_unknown() -> None:
    assert (
        thread_kind(
            {
                "agent_role": "",
                "source_kind": "",
                "parent_thread_id": "",
                "agent_nickname": "",
                "thread_source": "root",
            }
        )
        == "root"
    )
    assert (
        thread_kind(
            {
                "agent_role": "guardian",
                "source_kind": "",
                "parent_thread_id": "parent",
                "agent_nickname": "",
                "thread_source": "subagent",
            }
        )
        == "guardian"
    )
    assert (
        thread_kind(
            {
                "agent_role": "",
                "source_kind": "guardian",
                "parent_thread_id": "parent",
                "agent_nickname": "",
                "thread_source": "subagent",
            }
        )
        == "guardian"
    )
    assert (
        thread_kind(
            {
                "agent_role": "explorer",
                "source_kind": "",
                "parent_thread_id": "parent",
                "agent_nickname": "Scout",
                "thread_source": "subagent",
            }
        )
        == "explorer"
    )
    assert (
        thread_kind(
            {
                "agent_role": "",
                "source_kind": "thread_spawn",
                "parent_thread_id": "parent",
                "agent_nickname": "Builder",
                "thread_source": "subagent",
            }
        )
        == "worker"
    )
    assert (
        thread_kind(
            {
                "agent_role": "",
                "source_kind": "",
                "parent_thread_id": "parent",
                "agent_nickname": "",
                "thread_source": "manual",
            }
        )
        == "unknown"
    )


def test_role_label_uses_deterministic_names_and_nicknames() -> None:
    assert (
        role_label(
            {
                "parent_thread_id": "",
                "agent_role": "",
                "source_kind": "",
                "agent_nickname": "",
                "thread_source": "root",
            }
        )
        == "Root"
    )
    assert (
        role_label(
            {
                "parent_thread_id": "parent",
                "agent_role": "guardian",
                "source_kind": "",
                "agent_nickname": "",
                "thread_source": "subagent",
            }
        )
        == "Guardian"
    )
    assert (
        role_label(
            {
                "parent_thread_id": "parent",
                "agent_role": "explorer",
                "source_kind": "",
                "agent_nickname": "Scout",
                "thread_source": "subagent",
            }
        )
        == "Explorer (Scout)"
    )
    assert (
        role_label(
            {
                "parent_thread_id": "parent",
                "agent_role": "",
                "source_kind": "thread_spawn",
                "agent_nickname": "Builder",
                "thread_source": "subagent",
            }
        )
        == "Worker (Builder)"
    )
    assert (
        role_label(
            {
                "parent_thread_id": "parent",
                "agent_role": "",
                "source_kind": "",
                "agent_nickname": "",
                "thread_source": "manual",
            }
        )
        == "Unknown"
    )


def test_prepare_threads_coerces_numbers_and_calculates_metrics_with_zero_denominators() -> (
    None
):
    threads = pd.DataFrame(
        [
            {
                "thread_id": "root-thread",
                "parent_thread_id": "",
                "agent_role": "",
                "source_kind": "",
                "agent_nickname": "",
                "thread_source": "root",
                "event_count": "3",
                "turn_count": None,
                "tool_call_count": 4,
                "final_input_tokens": "200",
                "final_cached_input_tokens": "50",
                "final_uncached_input_tokens": "150",
                "final_output_tokens": "20",
                "final_reasoning_tokens": "30",
                "final_total_tokens": "250",
                "base_instruction_chars": None,
            },
            {
                "thread_id": "worker-thread",
                "parent_thread_id": "root-thread",
                "agent_role": "",
                "source_kind": "thread_spawn",
                "agent_nickname": "Builder",
                "thread_source": "subagent",
                "event_count": None,
                "turn_count": None,
                "tool_call_count": 0,
                "final_input_tokens": 0,
                "final_cached_input_tokens": 0,
                "final_uncached_input_tokens": 0,
                "final_output_tokens": 0,
                "final_reasoning_tokens": 0,
                "final_total_tokens": 0,
                "base_instruction_chars": 0,
            },
        ]
    )

    prepared = prepare_threads(threads)

    root = prepared[prepared["thread_id"] == "root-thread"].iloc[0]
    worker = prepared[prepared["thread_id"] == "worker-thread"].iloc[0]
    assert root["kind"] == "root"
    assert root["label"] == "Root"
    assert root["event_count"] == 3
    assert root["turn_count"] == 0
    assert root["cache_pct"] == 25
    assert root["output_plus_reasoning"] == 50
    assert root["input_per_output"] == 4
    assert root["tokens_per_tool"] == 62.5
    assert worker["kind"] == "worker"
    assert worker["label"] == "Worker (Builder)"
    assert worker["cache_pct"] == 0
    assert worker["input_per_output"] == 0
    assert worker["tokens_per_tool"] == 0


def test_build_tree_renders_root_with_child_thread() -> None:
    threads = prepare_threads(
        pd.DataFrame(
            [
                {
                    "thread_id": "root-thread-abcdef01",
                    "parent_thread_id": "",
                    "agent_role": "",
                    "source_kind": "",
                    "agent_nickname": "",
                    "thread_source": "root",
                    "created_at": "2026-01-01T00:00:00Z",
                    "first_seen": "2026-01-01T00:00:00Z",
                    "event_count": 3,
                    "turn_count": 1,
                    "tool_call_count": 1,
                    "final_input_tokens": 100,
                    "final_cached_input_tokens": 20,
                    "final_uncached_input_tokens": 80,
                    "final_output_tokens": 10,
                    "final_reasoning_tokens": 5,
                    "final_total_tokens": 115,
                    "base_instruction_chars": 0,
                },
                {
                    "thread_id": "child-thread-12345678",
                    "parent_thread_id": "root-thread-abcdef01",
                    "agent_role": "",
                    "source_kind": "thread_spawn",
                    "agent_nickname": "Builder",
                    "thread_source": "subagent",
                    "created_at": "2026-01-01T00:01:00Z",
                    "first_seen": "2026-01-01T00:01:00Z",
                    "event_count": 2,
                    "turn_count": 1,
                    "tool_call_count": 2,
                    "final_input_tokens": 5000,
                    "final_cached_input_tokens": 1000,
                    "final_uncached_input_tokens": 4000,
                    "final_output_tokens": 100,
                    "final_reasoning_tokens": 50,
                    "final_total_tokens": 5150,
                    "base_instruction_chars": 0,
                },
            ]
        )
    )

    tree = build_tree(threads, "session-1")

    assert tree == (
        "Conversation session-1\n"
        "+-- Root [abcdef01] input=100, uncached=80, tools=1\n"
        "    +-- Worker (Builder) [12345678] input=5.0k, uncached=4.0k, tools=2"
    )


def test_dashboard_css_contains_polish_hooks_without_viewport_scaled_type() -> None:
    css = dashboard_css()

    assert ".co-hero" in css
    assert ".co-empty" in css
    assert ".co-empty-actions" in css
    assert ".co-empty-action" in css
    assert ".co-comparison-preview" in css
    assert ".co-thread-brief" in css
    assert ".co-tool-brief" in css
    assert ".co-duplication-brief" in css
    assert ".co-timeline-brief" in css
    assert ".co-metric-grid" in css
    assert ".co-metric-card" in css
    assert ".co-metric-label" in css
    assert ".co-metric-value" in css
    assert "repeat(auto-fit, minmax(150px, 1fr))" in css
    assert ".co-briefing" in css
    assert ".co-briefing-grid" in css
    assert ".co-briefing-fact" in css
    assert ".co-diagnostics" in css
    assert ".co-diagnostic-action" in css
    assert ".co-playbook" in css
    assert ".co-playbook-impact" in css
    assert ".co-opportunities" in css
    assert ".co-opportunity-scale" in css
    assert ".co-triage" in css
    assert ".co-triage-risk" in css
    assert '[data-testid="stMetric"]' in css
    assert '[data-testid="stSidebar"] button' in css
    assert "white-space: normal;" in css
    assert "letter-spacing: 0;" in css
    assert "vw" not in css


def test_empty_state_commands_html_renders_copy_pasteable_safe_actions() -> None:
    rendered = empty_state_commands_html(
        [
            ("Try <demo>", "codex-observe demo --serve --db demo<db>.sqlite"),
            ("Ingest logs", "codex-observe ingest ~/.codex/sessions --db demo.sqlite"),
            ("Check health", "codex-observe doctor --db demo.sqlite"),
        ]
    )

    assert 'class="co-empty-actions"' in rendered
    assert rendered.count('class="co-empty-action"') == 3
    assert "Try &lt;demo&gt;" in rendered
    assert "demo&lt;db&gt;.sqlite" in rendered
    assert "codex-observe ingest ~/.codex/sessions --db demo.sqlite" in rendered
    assert "codex-observe doctor --db demo.sqlite" in rendered
    assert "Try <demo>" not in rendered


def test_triage_card_html_escapes_content_and_renders_reasons() -> None:
    rendered = triage_card_html(
        {
            "risk_level": "high",
            "primary_driver": "Largest <thread>",
            "next_action": "Set stop & summarize",
            "reasons": ["Prompt replay > 15%", "Tool output <large>"],
        }
    )

    assert 'class="co-triage"' in rendered
    assert 'class="co-triage-risk"' in rendered
    assert "Run triage" in rendered
    assert "Largest &lt;thread&gt;" in rendered
    assert "Set stop &amp; summarize" in rendered
    assert "Tool output &lt;large&gt;" in rendered
    assert "Largest <thread>" not in rendered


def test_operator_briefing_html_summarizes_top_action_and_escapes_content() -> None:
    rendered = operator_briefing_html(
        {
            "risk_level": "high",
            "primary_driver": "Largest <thread>",
            "next_action": "Set stop & summarize",
        },
        {
            "metric": "largest_thread_share_pct",
            "current": "57.7%",
            "target": "below <50%",
        },
        pd.DataFrame(
            [
                {
                    "Habit": "Stop <dominant> worker",
                    "Scale": "33.2k tokens (57.7% of run)",
                }
            ]
        ),
    )

    assert 'class="co-briefing"' in rendered
    assert "Operator briefing" in rendered
    assert "High risk" in rendered
    assert "Largest &lt;thread&gt;" in rendered
    assert "Set stop &amp; summarize" in rendered
    assert "Stop &lt;dominant&gt; worker" in rendered
    assert "largest_thread_share_pct: 57.7% -> below &lt;50%" in rendered
    assert "Largest <thread>" not in rendered


def test_report_download_payloads_match_cli_report_contract() -> None:
    report = {
        "schema_version": "codex-observe.report.v1",
        "privacy": {"mode": "aggregate-only"},
        "session": {"session_id": "demo/session <cost>"},
        "headline": {
            "headline": "High risk run",
            "top_diagnostic": "Largest thread drives the run",
            "recommendation": "Set a stop condition",
        },
        "summary": {
            "threads": 3,
            "workers": 1,
            "explorers": 1,
            "guardians": 1,
            "tool_calls": 4,
            "compactions": 1,
            "total_tokens": 57510,
            "input_tokens": 34700,
            "uncached_input_tokens": 22700,
            "cached_input_tokens": 12000,
            "cache_pct": 34.6,
            "largest_thread_tokens": 33200,
            "largest_thread_kind": "worker",
            "largest_thread_share_pct": 57.7,
            "repeated_prompt_tokens": 10000,
            "repeated_prompt_share_pct": 17.4,
            "uncached_input_share_pct": 39.5,
            "largest_tool_output_chars": 4000,
        },
        "triage": {
            "risk_level": "high",
            "primary_driver": "Largest thread drives the run",
            "next_action": "Set a stop condition",
            "reasons": ["Largest thread used 57.7% of total tokens."],
        },
        "opportunities": [],
        "diagnostics": [],
        "playbook": [],
        "findings": [],
        "success_target": {
            "metric": "largest_thread_share_pct",
            "current": "57.7%",
            "target": "below 50.0%",
        },
        "next_action_detail": {"action": "Set a stop condition"},
    }

    payloads = report_download_payloads(report)

    assert (
        payloads["markdown"]["filename"] == "codex-observe-demo-session--cost-report.md"
    )
    assert payloads["markdown"]["mime"] == "text/markdown"
    assert "# Codex Observe Run Report" in payloads["markdown"]["data"]
    assert (
        payloads["json"]["filename"] == "codex-observe-demo-session--cost-report.json"
    )
    assert payloads["json"]["mime"] == "application/json"
    assert '"schema_version": "codex-observe.report.v1"' in payloads["json"]["data"]
    assert '"mode": "aggregate-only"' in payloads["json"]["data"]


def test_comparison_download_payloads_match_cli_comparison_contract() -> None:
    comparison = {
        "schema_version": "codex-observe.comparison.v1",
        "privacy": {"mode": "aggregate-only"},
        "before": {"session_id": "before/session"},
        "after": {"session_id": "after session"},
        "summary": "After run improved total tokens.",
        "verdict": "improved",
        "largest_change": "Total tokens improved by 10.0%.",
        "recommendation": "Keep the improved habit.",
        "triage_risk": {"before": "high", "after": "low", "direction": "improved"},
        "opportunity_change": {"summary": "Top opportunity improved."},
        "recommendation_detail": {"action": "keep_change"},
        "metrics": [
            {
                "label": "Total tokens",
                "before": 1000,
                "after": 900,
                "delta": -100,
                "delta_pct": -10.0,
                "direction": "improved",
            }
        ],
        "diagnostics": {"resolved": [], "new": [], "persisted": []},
    }

    payloads = comparison_download_payloads(comparison)

    assert (
        payloads["markdown"]["filename"]
        == "codex-observe-before-session-to-after-session-comparison.md"
    )
    assert payloads["markdown"]["mime"] == "text/markdown"
    assert "# Codex Observe Run Comparison" in payloads["markdown"]["data"]
    assert (
        payloads["json"]["filename"]
        == "codex-observe-before-session-to-after-session-comparison.json"
    )
    assert payloads["json"]["mime"] == "application/json"
    assert '"schema_version": "codex-observe.comparison.v1"' in payloads["json"]["data"]
    assert '"mode": "aggregate-only"' in payloads["json"]["data"]


def test_comparison_preview_html_summarizes_and_escapes_quick_read() -> None:
    rendered = comparison_preview_html(
        {
            "verdict": "improved <ok>",
            "headline": {"headline": "Verdict improved & stable."},
            "triage_risk": {"direction": "improved"},
            "opportunity_change": {"summary": "Top opportunity stayed <largest>."},
            "recommendation": "Keep change & compare again.",
        }
    )

    assert 'class="co-comparison-preview"' in rendered
    assert "Comparison quick read" in rendered
    assert "improved &lt;ok&gt;" in rendered
    assert "Verdict improved &amp; stable." in rendered
    assert "Triage movement" in rendered
    assert "Opportunity movement" in rendered
    assert "Top opportunity stayed &lt;largest&gt;." in rendered
    assert "Keep change &amp; compare again." in rendered
    assert "improved <ok>" not in rendered


def test_success_target_html_escapes_and_renders_target_card() -> None:
    rendered = success_target_html(
        {
            "metric": "largest_thread_share_pct",
            "current": "57.7%",
            "target": "below <50%",
            "rationale": "Split & stop earlier",
            "verification": "Compare <next> report JSON",
        }
    )

    assert 'class="co-success-target"' in rendered
    assert "Next run success target" in rendered
    assert "largest_thread_share_pct" in rendered
    assert "below &lt;50%" in rendered
    assert "Split &amp; stop earlier" in rendered
    assert "Compare &lt;next&gt; report JSON" in rendered
    assert "below <50%" not in rendered


def test_dashboard_metric_share_helpers_format_actionable_percentages() -> None:
    assert pct_of_total(33200, 57510) == 57.7
    assert pct_of_total(0, 0) == 0.0
    assert pct_of_total("not-a-number", 100) == 0.0
    assert metric_with_share(33200, 57510) == "33.2k tokens (57.7%)"
    assert metric_with_share(4000, 57510, unit="chars") == "4.0k chars (7.0%)"


def test_opportunity_df_ranks_aggregate_cost_drivers() -> None:
    opportunities = opportunity_df(
        {
            "total_tokens": 57_510,
            "largest_thread_tokens": 33_200,
            "repeated_prompt_tokens": 10_000,
            "uncached_input_tokens": 22_700,
            "largest_tool_output_chars": 4_000,
            "compactions": 1,
        }
    )

    assert opportunities["Driver"].tolist()[:3] == [
        "Largest thread",
        "Uncached input",
        "Repeated prompt blocks",
    ]
    assert opportunities.iloc[0].to_dict() == {
        "Rank": 1,
        "Habit": "Set a stop condition for the dominant thread",
        "Driver": "Largest thread",
        "Scale": "33.2k tokens (57.7% of run)",
        "Why": "This is the biggest aggregate token pool to shorten or split first.",
    }


def test_opportunity_html_escapes_card_content() -> None:
    rendered = opportunity_html(
        pd.DataFrame(
            [
                {
                    "Rank": 1,
                    "Habit": "Stop <thread>",
                    "Driver": "Largest & risky",
                    "Scale": "10k tokens",
                    "Why": "Use <shorter> checkpoints",
                }
            ]
        )
    )

    assert 'class="co-opportunities"' in rendered
    assert 'class="co-opportunity-scale"' in rendered
    assert "Stop &lt;thread&gt;" in rendered
    assert "Largest &amp; risky" in rendered
    assert "Use &lt;shorter&gt; checkpoints" in rendered
    assert "Stop <thread>" not in rendered


def test_diagnostics_df_prioritizes_actionable_cost_signals() -> None:
    threads = prepare_threads(
        pd.DataFrame(
            [
                {
                    "thread_id": "root-thread",
                    "parent_thread_id": "",
                    "agent_role": "",
                    "source_kind": "",
                    "agent_nickname": "",
                    "thread_source": "root",
                    "created_at": "2026-01-01T00:00:00Z",
                    "first_seen": "2026-01-01T00:00:00Z",
                    "last_seen": "2026-01-01T00:10:00Z",
                    "event_count": 8,
                    "turn_count": 2,
                    "tool_call_count": 1,
                    "final_input_tokens": 12000,
                    "final_cached_input_tokens": 2000,
                    "final_uncached_input_tokens": 10000,
                    "final_output_tokens": 500,
                    "final_reasoning_tokens": 250,
                    "final_total_tokens": 12750,
                    "base_instruction_chars": 0,
                },
                {
                    "thread_id": "guardian-thread",
                    "parent_thread_id": "root-thread",
                    "agent_role": "guardian",
                    "source_kind": "guardian",
                    "agent_nickname": "",
                    "thread_source": "subagent",
                    "created_at": "2026-01-01T00:03:00Z",
                    "first_seen": "2026-01-01T00:03:00Z",
                    "last_seen": "2026-01-01T00:04:00Z",
                    "event_count": 3,
                    "turn_count": 1,
                    "tool_call_count": 0,
                    "final_input_tokens": 2000,
                    "final_cached_input_tokens": 1000,
                    "final_uncached_input_tokens": 1000,
                    "final_output_tokens": 40,
                    "final_reasoning_tokens": 10,
                    "final_total_tokens": 2050,
                    "base_instruction_chars": 0,
                },
            ]
        )
    )
    usage = pd.DataFrame(
        [
            {
                "thread_id": "root-thread",
                "idx": 1,
                "timestamp": "2026-01-01T00:01:00Z",
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "uncached_input_tokens": 100,
                "output_tokens": 10,
                "reasoning_tokens": 0,
                "total_tokens": 110,
            },
            {
                "thread_id": "root-thread",
                "idx": 2,
                "timestamp": "2026-01-01T00:02:00Z",
                "input_tokens": 12100,
                "cached_input_tokens": 2000,
                "uncached_input_tokens": 10100,
                "output_tokens": 100,
                "reasoning_tokens": 20,
                "total_tokens": 12220,
            },
        ]
    )
    events = pd.DataFrame(
        [
            {
                "thread_id": "root-thread",
                "idx": 2,
                "timestamp": "2026-01-01T00:02:30Z",
                "type": "compacted",
                "payload_type": "",
            },
        ]
    )
    tools = pd.DataFrame(
        [
            {
                "thread_id": "root-thread",
                "tool_name": "shell_command",
                "command": "Get-ChildItem -Recurse",
                "output_chars": 25000,
            },
        ]
    )
    duplicated = pd.DataFrame(
        [
            {"label": "AGENTS.md", "seen": 3, "approx_tokens_replayed": 15000},
        ]
    )

    diagnostics = diagnostics_df(threads, usage, events, tools, duplicated)

    assert diagnostics["Diagnostic"].tolist() == [
        "Largest thread drives the run",
        "Largest context jump",
        "Largest tool output",
        "Repeated prompt blocks",
        "Context compaction occurred",
        "Guardian overhead",
    ]
    assert diagnostics.iloc[0]["Priority"] == "High"
    assert "Inspect this thread first" in diagnostics.iloc[0]["Action"]
    assert (
        "+12.0k input tokens"
        in diagnostics.loc[
            diagnostics["Diagnostic"] == "Largest context jump", "Evidence"
        ].iloc[0]
    )
    assert (
        "25.0k chars"
        in diagnostics.loc[
            diagnostics["Diagnostic"] == "Largest tool output", "Evidence"
        ].iloc[0]
    )
    assert (
        "15.0k approximate replayed tokens"
        in diagnostics.loc[
            diagnostics["Diagnostic"] == "Repeated prompt blocks", "Evidence"
        ].iloc[0]
    )


def test_diagnostics_df_returns_schema_for_empty_threads() -> None:
    diagnostics = diagnostics_df(
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    )

    assert diagnostics.empty
    assert diagnostics.columns.tolist() == [
        "Priority",
        "Diagnostic",
        "Action",
        "Evidence",
    ]


def test_diagnostics_cards_html_escapes_content_and_renders_cards() -> None:
    diagnostics = pd.DataFrame(
        [
            {
                "Priority": "High",
                "Diagnostic": "Largest <thread>",
                "Action": "Inspect & reduce context",
                "Evidence": "demo-root used > 50%",
            }
        ]
    )

    rendered = diagnostics_cards_html(diagnostics)

    assert 'class="co-diagnostics"' in rendered
    assert 'class="co-diagnostic"' in rendered
    assert "Largest &lt;thread&gt;" in rendered
    assert "Inspect &amp; reduce context" in rendered
    assert "demo-root used &gt; 50%" in rendered
    assert "Largest <thread>" not in rendered


def test_diagnostics_cards_html_returns_empty_string_for_no_rows() -> None:
    assert diagnostics_cards_html(pd.DataFrame()) == ""


def test_next_run_playbook_df_turns_diagnostics_into_habits() -> None:
    diagnostics = pd.DataFrame(
        [
            {
                "Priority": "High",
                "Diagnostic": "Largest context jump",
                "Action": "Inspect timeline",
                "Evidence": "Root +18.0k input tokens",
            },
            {
                "Priority": "High",
                "Diagnostic": "Largest tool output",
                "Action": "Narrow command",
                "Evidence": "shell_command produced 30.0k chars",
            },
            {
                "Priority": "Medium",
                "Diagnostic": "Largest context jump",
                "Action": "Duplicate should be ignored",
                "Evidence": "duplicate",
            },
        ]
    )

    playbook = next_run_playbook_df(diagnostics)

    assert playbook.columns.tolist() == ["Step", "Habit", "Impact", "Why", "Source"]
    assert playbook["Step"].tolist() == [1, 2]
    assert playbook["Habit"].tolist() == [
        "Gate large context before it enters the chat",
        "Narrow bulky commands before sharing output",
    ]
    assert playbook["Impact"].tolist() == [
        "Targets sudden input-token growth.",
        "Targets bulky tool-output feedback loops.",
    ]
    assert "Root +18.0k input tokens" in playbook.iloc[0]["Source"]


def test_next_run_playbook_df_returns_schema_for_empty_diagnostics() -> None:
    playbook = next_run_playbook_df(pd.DataFrame())

    assert playbook.empty
    assert playbook.columns.tolist() == ["Step", "Habit", "Impact", "Why", "Source"]


def test_playbook_html_escapes_content_and_renders_steps() -> None:
    playbook = pd.DataFrame(
        [
            {
                "Step": 1,
                "Habit": "Gate <context>",
                "Impact": "Targets <input> growth",
                "Why": "Use summaries & filters",
                "Source": "Largest jump > 10k",
            }
        ]
    )

    rendered = playbook_html(playbook)

    assert 'class="co-playbook"' in rendered
    assert 'class="co-playbook-step"' in rendered
    assert "Gate &lt;context&gt;" in rendered
    assert "Targets &lt;input&gt; growth" in rendered
    assert "Use summaries &amp; filters" in rendered
    assert "Largest jump &gt; 10k" in rendered
    assert "Gate <context>" not in rendered


def test_playbook_html_returns_empty_string_for_no_rows() -> None:
    assert playbook_html(pd.DataFrame()) == ""
