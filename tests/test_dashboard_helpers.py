from __future__ import annotations

import pandas as pd

from codex_observe.dashboard import build_tree, prepare_threads, role_label, thread_kind


def test_thread_kind_classifies_root_worker_explorer_guardian_and_unknown() -> None:
    assert thread_kind({"agent_role": "", "source_kind": "", "parent_thread_id": "", "agent_nickname": "", "thread_source": "root"}) == "root"
    assert thread_kind({"agent_role": "guardian", "source_kind": "", "parent_thread_id": "parent", "agent_nickname": "", "thread_source": "subagent"}) == "guardian"
    assert thread_kind({"agent_role": "", "source_kind": "guardian", "parent_thread_id": "parent", "agent_nickname": "", "thread_source": "subagent"}) == "guardian"
    assert thread_kind({"agent_role": "explorer", "source_kind": "", "parent_thread_id": "parent", "agent_nickname": "Scout", "thread_source": "subagent"}) == "explorer"
    assert thread_kind({"agent_role": "", "source_kind": "thread_spawn", "parent_thread_id": "parent", "agent_nickname": "Builder", "thread_source": "subagent"}) == "worker"
    assert thread_kind({"agent_role": "", "source_kind": "", "parent_thread_id": "parent", "agent_nickname": "", "thread_source": "manual"}) == "unknown"


def test_role_label_uses_deterministic_names_and_nicknames() -> None:
    assert role_label({"parent_thread_id": "", "agent_role": "", "source_kind": "", "agent_nickname": "", "thread_source": "root"}) == "Root"
    assert role_label({"parent_thread_id": "parent", "agent_role": "guardian", "source_kind": "", "agent_nickname": "", "thread_source": "subagent"}) == "Guardian"
    assert role_label({"parent_thread_id": "parent", "agent_role": "explorer", "source_kind": "", "agent_nickname": "Scout", "thread_source": "subagent"}) == "Explorer (Scout)"
    assert role_label({"parent_thread_id": "parent", "agent_role": "", "source_kind": "thread_spawn", "agent_nickname": "Builder", "thread_source": "subagent"}) == "Worker (Builder)"
    assert role_label({"parent_thread_id": "parent", "agent_role": "", "source_kind": "", "agent_nickname": "", "thread_source": "manual"}) == "Unknown"


def test_prepare_threads_coerces_numbers_and_calculates_metrics_with_zero_denominators() -> None:
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
        "\u2514\u2500\u2500 Root [abcdef01] input=100, uncached=80, tools=1\n"
        "    \u2514\u2500\u2500 Worker (Builder) [12345678] input=5.0k, uncached=4.0k, tools=2"
    )

