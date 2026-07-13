from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .parser import IngestResult, ingest


TS = "2026-01-01T12:{minute:02d}:00Z"
DEFAULT_DEMO_DB = ".artifacts/demo/codex_observe_demo.sqlite"
DEFAULT_DEMO_SESSIONS = ".artifacts/demo/sessions"
REPEATED_INSTRUCTIONS = (
    "# AGENTS.md instructions\n"
    + "Use small, reviewable changes. Prefer tests and visual checks. " * 120
)
TRANSCRIPT_BLOCK = (
    ">>> TRANSCRIPT START\n"
    + "User asked for an offline Codex observability dashboard. " * 100
    + "\n>>> TRANSCRIPT END"
)


def event(minute: int, payload: dict[str, Any], typ: str = "event") -> dict[str, Any]:
    return {"timestamp": TS.format(minute=minute), "type": typ, "payload": payload}


def session_meta(
    *,
    minute: int,
    thread_id: str,
    session_id: str,
    parent_thread_id: str | None = None,
    role: str | None = None,
    nickname: str = "",
) -> dict[str, Any]:
    source: dict[str, Any] | str = "root"
    if parent_thread_id:
        source = {
            "subagent": {
                "thread_spawn": {
                    "agent_role": role or "worker",
                    "agent_nickname": nickname,
                }
            }
        }
    return event(
        minute,
        {
            "id": thread_id,
            "session_id": session_id,
            "parent_thread_id": parent_thread_id,
            "source": source,
            "thread_source": "subagent" if parent_thread_id else "root",
            "cwd": "D:/demo/codex-observe",
            "cli_version": "demo",
            "model_provider": "openai",
            "timestamp": TS.format(minute=minute),
            "base_instructions": {"text": "Synthetic demo session for Codex Observe."},
        },
        typ="session_meta",
    )


def message(minute: int, role: str, content: str, turn: str) -> dict[str, Any]:
    return event(
        minute, {"type": "message", "role": role, "content": content, "turn_id": turn}
    )


def token_count(
    minute: int,
    turn: str,
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    last_input_tokens: int,
) -> dict[str, Any]:
    total_tokens = input_tokens + output_tokens + reasoning_tokens
    return event(
        minute,
        {
            "type": "token_count",
            "turn_id": turn,
            "info": {
                "total_token_usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached_input_tokens,
                    "output_tokens": output_tokens,
                    "reasoning_output_tokens": reasoning_tokens,
                    "total_tokens": total_tokens,
                },
                "last_token_usage": {
                    "input_tokens": last_input_tokens,
                    "cached_input_tokens": min(
                        cached_input_tokens, last_input_tokens // 2
                    ),
                    "output_tokens": max(1, output_tokens // 4),
                    "reasoning_output_tokens": max(1, reasoning_tokens // 4),
                    "total_tokens": last_input_tokens
                    + max(1, output_tokens // 4)
                    + max(1, reasoning_tokens // 4),
                },
                "model_context_window": 200000,
            },
        },
    )


def tool_call(
    minute: int, call_id: str, command: str, turn: str
) -> list[dict[str, Any]]:
    output = "synthetic output line\n" * (180 if "rg" in command else 40)
    return [
        event(
            minute,
            {
                "type": "function_call",
                "call_id": call_id,
                "name": "shell_command",
                "arguments": json.dumps(
                    {
                        "command": command,
                        "workdir": "D:/demo/codex-observe",
                        "timeout_ms": 10000,
                    }
                ),
                "turn_id": turn,
            },
        ),
        event(
            minute + 1,
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": output,
                "turn_id": turn,
            },
        ),
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )


def build_demo_sessions(root: Path) -> None:
    session_id = "demo-session-cost-review"
    root_rows = [
        session_meta(minute=0, thread_id="demo-root", session_id=session_id),
        message(
            1,
            "user",
            "Analyze why this Codex run became expensive and recommend what to inspect first.",
            "turn-root-1",
        ),
        message(
            2,
            "assistant",
            "I will inspect token growth, workers, tool outputs, and repeated prompt blocks.",
            "turn-root-1",
        ),
        token_count(
            3,
            "turn-root-1",
            input_tokens=1200,
            cached_input_tokens=300,
            output_tokens=160,
            reasoning_tokens=80,
            last_input_tokens=1200,
        ),
        *tool_call(4, "root-rg", "rg --files", "turn-root-1"),
        event(
            7,
            {
                "type": "thread_goal_updated",
                "goal": {"objective": "Find the largest sources of context growth."},
                "turn_id": "turn-root-2",
            },
        ),
        message(
            8,
            "assistant",
            REPEATED_INSTRUCTIONS + "\n\n" + TRANSCRIPT_BLOCK,
            "turn-root-2",
        ),
        token_count(
            9,
            "turn-root-2",
            input_tokens=18500,
            cached_input_tokens=8000,
            output_tokens=620,
            reasoning_tokens=240,
            last_input_tokens=17300,
        ),
        event(10, {"type": "context_compacted", "turn_id": "turn-root-2"}),
        token_count(
            11,
            "turn-root-2",
            input_tokens=9200,
            cached_input_tokens=4000,
            output_tokens=700,
            reasoning_tokens=260,
            last_input_tokens=900,
        ),
    ]
    write_jsonl(root / "root.jsonl", root_rows)

    worker_rows = [
        session_meta(
            minute=12,
            thread_id="demo-worker-parser",
            session_id=session_id,
            parent_thread_id="demo-root",
            role="worker",
            nickname="Parser",
        ),
        message(
            13,
            "user",
            REPEATED_INSTRUCTIONS
            + "\n"
            + TRANSCRIPT_BLOCK
            + "\n\nInspect parser behavior and duplicate handling.",
            "turn-worker-1",
        ),
        token_count(
            14,
            "turn-worker-1",
            input_tokens=24000,
            cached_input_tokens=15000,
            output_tokens=900,
            reasoning_tokens=350,
            last_input_tokens=24000,
        ),
        *tool_call(
            15, "worker-rg", "rg token_count codex_observe tests", "turn-worker-1"
        ),
        message(
            18,
            "assistant",
            "Parser looks deterministic; duplicate handling is covered by tests.",
            "turn-worker-1",
        ),
        token_count(
            19,
            "turn-worker-1",
            input_tokens=31500,
            cached_input_tokens=19000,
            output_tokens=1200,
            reasoning_tokens=500,
            last_input_tokens=7500,
        ),
    ]
    write_jsonl(root / "worker-parser.jsonl", worker_rows)

    guardian_rows = [
        session_meta(
            minute=20,
            thread_id="demo-guardian",
            session_id=session_id,
            parent_thread_id="demo-root",
            role="guardian",
            nickname="",
        ),
        message(
            21,
            "user",
            REPEATED_INSTRUCTIONS
            + "\n"
            + TRANSCRIPT_BLOCK
            + "\n\nApprove whether the dashboard may run visual QA locally.",
            "turn-guardian-1",
        ),
        token_count(
            22,
            "turn-guardian-1",
            input_tokens=14000,
            cached_input_tokens=9000,
            output_tokens=90,
            reasoning_tokens=60,
            last_input_tokens=14000,
        ),
        message(
            23,
            "assistant",
            "Approved: local screenshots do not send data externally.",
            "turn-guardian-1",
        ),
    ]
    write_jsonl(root / "guardian.jsonl", guardian_rows)
    followup_session_id = "demo-session-focused-followup"
    followup_root_rows = [
        session_meta(
            minute=24,
            thread_id="demo-followup-root",
            session_id=followup_session_id,
        ),
        message(
            25,
            "user",
            "Run a focused follow-up pass using the previous aggregate report.",
            "turn-followup-root-1",
        ),
        token_count(
            26,
            "turn-followup-root-1",
            input_tokens=2400,
            cached_input_tokens=2000,
            output_tokens=250,
            reasoning_tokens=50,
            last_input_tokens=900,
        ),
        *tool_call(
            27, "followup-root-list", "Get-ChildItem docs", "turn-followup-root-1"
        ),
        message(
            29,
            "assistant",
            "Focused pass stayed small and used existing context effectively.",
            "turn-followup-root-1",
        ),
    ]
    write_jsonl(root / "followup-root.jsonl", followup_root_rows)

    followup_worker_rows = [
        session_meta(
            minute=30,
            thread_id="demo-followup-worker",
            session_id=followup_session_id,
            parent_thread_id="demo-followup-root",
            role="worker",
            nickname="Docs",
        ),
        message(
            31,
            "user",
            "Check whether the report recommendation is reflected in the docs.",
            "turn-followup-worker-1",
        ),
        token_count(
            32,
            "turn-followup-worker-1",
            input_tokens=2600,
            cached_input_tokens=2200,
            output_tokens=220,
            reasoning_tokens=80,
            last_input_tokens=850,
        ),
    ]
    write_jsonl(root / "followup-worker.jsonl", followup_worker_rows)

    followup_reviewer_rows = [
        session_meta(
            minute=33,
            thread_id="demo-followup-reviewer",
            session_id=followup_session_id,
            parent_thread_id="demo-followup-root",
            role="guardian",
            nickname="Review",
        ),
        message(
            34,
            "user",
            "Confirm the follow-up stayed within the intended scope.",
            "turn-followup-reviewer-1",
        ),
        token_count(
            35,
            "turn-followup-reviewer-1",
            input_tokens=2500,
            cached_input_tokens=2100,
            output_tokens=240,
            reasoning_tokens=60,
            last_input_tokens=800,
        ),
    ]
    write_jsonl(root / "followup-reviewer.jsonl", followup_reviewer_rows)


def create_demo_database(
    out: str | Path = DEFAULT_DEMO_DB,
    sessions: str | Path = DEFAULT_DEMO_SESSIONS,
    *,
    keep_sessions: bool = False,
) -> IngestResult:
    out_path = Path(out).expanduser()
    sessions_path = Path(sessions).expanduser()

    if sessions_path.exists():
        shutil.rmtree(sessions_path)
    if out_path.exists():
        out_path.unlink()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    build_demo_sessions(sessions_path)
    result = ingest(str(sessions_path), str(out_path))
    if not keep_sessions:
        shutil.rmtree(sessions_path)
    return result
