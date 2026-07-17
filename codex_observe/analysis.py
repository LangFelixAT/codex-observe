from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Any

import pandas as pd


def fmt_int(x: Any) -> str:
    try:
        return f"{int(float(x)):,}"
    except Exception:
        return "0"


def fmt_short(x: Any) -> str:
    try:
        x = float(x or 0)
    except Exception:
        return "0"
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1_000_000_000:
        return f"{sign}{x / 1_000_000_000:.1f}B"
    if x >= 1_000_000:
        return f"{sign}{x / 1_000_000:.1f}M"
    if x >= 1_000:
        return f"{sign}{x / 1_000:.1f}k"
    return f"{sign}{int(x)}"


def parse_ts(ts: Any):
    if ts is None:
        return None
    try:
        if pd.isna(ts):
            return None
    except Exception:
        pass
    s = str(ts).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def sidebar_time_label(ts: Any) -> str:
    d = parse_ts(ts)
    return d.strftime("%H:%M") if d else ""


def clean_value(x: Any) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    s = str(x).strip()
    if s.lower() in {"", "nan", "none", "null"}:
        return ""
    return s


def thread_kind(row) -> str:
    role = clean_value(row.get("agent_role"))
    source_kind = clean_value(row.get("source_kind"))
    parent = clean_value(row.get("parent_thread_id"))
    nick = clean_value(row.get("agent_nickname"))
    thread_source = clean_value(row.get("thread_source"))

    if role == "guardian" or source_kind == "guardian":
        return "guardian"
    if role == "explorer":
        return "explorer"
    if not parent:
        return "root"
    if nick or thread_source == "subagent" or source_kind == "thread_spawn":
        return "worker"
    return "unknown"


def role_label(row) -> str:
    kind = thread_kind(row)
    nick = clean_value(row.get("agent_nickname"))
    if kind == "root":
        return "Root"
    if kind == "guardian":
        return "Guardian"
    if kind == "explorer":
        return f"Explorer ({nick})" if nick else "Explorer"
    if kind == "worker":
        return f"Worker ({nick})" if nick else "Worker"
    return "Unknown"


def build_tree(threads: pd.DataFrame, root_session: str) -> str:
    if threads.empty:
        return ""
    by_parent: dict[str, list[dict]] = {}
    rows = threads.to_dict("records")
    ids = {r["thread_id"] for r in rows}
    for r in rows:
        parent = clean_value(r.get("parent_thread_id"))
        if parent not in ids:
            parent = "__root__"
        by_parent.setdefault(parent, []).append(r)
    for v in by_parent.values():
        v.sort(key=lambda r: r.get("created_at") or r.get("first_seen") or "")

    lines: list[str] = [f"Conversation {root_session}"]

    def rec(parent: str, prefix: str = ""):
        children = by_parent.get(parent, [])
        for i, r in enumerate(children):
            last = i == len(children) - 1
            branch = "+-- " if last else "|-- "
            child_prefix = prefix + ("    " if last else "|   ")
            label = r.get("label") or role_label(r)
            short = (r.get("thread_id") or "")[-8:]
            toks = fmt_short(r.get("final_input_tokens", 0))
            uncached = fmt_short(r.get("final_uncached_input_tokens", 0))
            tools = fmt_int(r.get("tool_call_count", 0))
            lines.append(
                f"{prefix}{branch}{label} [{short}] input={toks}, uncached={uncached}, tools={tools}"
            )
            rec(r["thread_id"], child_prefix)

    rec("__root__")
    return "\n".join(lines)


def numericize(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df


def prepare_threads(threads: pd.DataFrame) -> pd.DataFrame:
    threads = numericize(
        threads,
        [
            "event_count",
            "turn_count",
            "tool_call_count",
            "final_input_tokens",
            "final_cached_input_tokens",
            "final_uncached_input_tokens",
            "final_output_tokens",
            "final_reasoning_tokens",
            "final_total_tokens",
            "base_instruction_chars",
        ],
    )
    threads["kind"] = threads.apply(thread_kind, axis=1)
    threads["label"] = threads.apply(role_label, axis=1)
    threads["cache_pct"] = (
        threads["final_cached_input_tokens"]
        / threads["final_input_tokens"].replace(0, 1)
        * 100
    )
    threads["output_plus_reasoning"] = (
        threads["final_output_tokens"] + threads["final_reasoning_tokens"]
    )
    threads["input_per_output"] = threads["final_input_tokens"] / threads[
        "output_plus_reasoning"
    ].replace(0, 1)
    threads["tokens_per_tool"] = threads["final_total_tokens"] / threads[
        "tool_call_count"
    ].replace(0, 1)
    return threads


def json_loads_safe(s: Any) -> dict[str, Any]:
    if not isinstance(s, str) or not s:
        return {}
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {"value": obj}
    except Exception:
        return {}


def useful_text_preview(text: Any, limit: int = 260) -> str:
    s = clean_value(text).replace("\r", " ").replace("\n", " ")
    s = " ".join(s.split())
    if len(s) > limit:
        return s[: limit - 3] + "..."
    return s


def worker_goal(messages: pd.DataFrame, events: pd.DataFrame, thread_id: str) -> str:
    ev = events[events["thread_id"] == thread_id]
    for _, row in ev.iterrows():
        payload = json_loads_safe(row.get("payload_json"))
        if payload.get("type") == "thread_goal_updated":
            goal = payload.get("goal")
            if isinstance(goal, dict):
                return useful_text_preview(
                    goal.get("objective") or goal.get("title") or goal, 500
                )
            return useful_text_preview(goal, 500)
    msgs = messages[messages["thread_id"] == thread_id]
    for _, m in msgs.iterrows():
        text = clean_value(m.get("text"))
        if not text:
            continue
        if (
            text.startswith("# AGENTS.md instructions")
            or text.startswith("<environment_context>")
            or text.startswith("<INSTRUCTIONS>")
        ):
            continue
        if "The following is the Codex agent history" in text:
            continue
        return useful_text_preview(text, 500)
    return ""


def compactions_df(
    events: pd.DataFrame, usage: pd.DataFrame, threads: pd.DataFrame
) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    mask = (events["type"] == "compacted") | (
        events["payload_type"] == "context_compacted"
    )
    comp = events[mask].copy()
    if comp.empty:
        return comp
    rows = []
    for _, e in comp.iterrows():
        tid = e["thread_id"]
        u = usage[usage["thread_id"] == tid].copy()
        before = u[u["idx"] <= e["idx"]].sort_values("idx").tail(1)
        after = u[u["idx"] > e["idx"]].sort_values("idx").head(1)
        before_tok = int(before["input_tokens"].iloc[0]) if not before.empty else 0
        after_tok = int(after["input_tokens"].iloc[0]) if not after.empty else 0
        trow = threads[threads["thread_id"] == tid].head(1)
        label = trow["label"].iloc[0] if not trow.empty else tid[-8:]
        rows.append(
            {
                "timestamp": e["timestamp"],
                "thread": label,
                "thread_id": tid,
                "event_type": e["type"]
                if e["type"] == "compacted"
                else e["payload_type"],
                "input_before": before_tok,
                "input_after_next_snapshot": after_tok,
                "delta_to_next_snapshot": after_tok - before_tok,
            }
        )
    return pd.DataFrame(rows).sort_values("timestamp")


def token_jumps_df(
    usage: pd.DataFrame, threads: pd.DataFrame, limit: int = 30
) -> pd.DataFrame:
    if usage.empty:
        return pd.DataFrame()
    u = numericize(
        usage,
        [
            "idx",
            "input_tokens",
            "cached_input_tokens",
            "uncached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
        ],
    )
    u = u.sort_values(["thread_id", "idx"]).copy()
    for col in ["input_tokens", "uncached_input_tokens", "total_tokens"]:
        u[f"delta_{col}"] = u.groupby("thread_id")[col].diff().fillna(u[col])
    u = u.merge(threads[["thread_id", "label", "kind"]], on="thread_id", how="left")
    cols = [
        "timestamp",
        "label",
        "kind",
        "thread_id",
        "delta_input_tokens",
        "delta_uncached_input_tokens",
        "delta_total_tokens",
        "input_tokens",
        "total_tokens",
    ]
    return u.sort_values("delta_input_tokens", ascending=False)[cols].head(limit)


def guardian_overhead_df(threads: pd.DataFrame) -> pd.DataFrame:
    g = threads[threads["kind"] == "guardian"].copy()
    if g.empty:
        return pd.DataFrame()
    g["output_plus_reasoning"] = g["final_output_tokens"] + g["final_reasoning_tokens"]
    g["input_per_output"] = g["final_input_tokens"] / g[
        "output_plus_reasoning"
    ].replace(0, 1)
    return g.sort_values("final_input_tokens", ascending=False)[
        [
            "label",
            "first_seen",
            "last_seen",
            "thread_id",
            "final_input_tokens",
            "final_cached_input_tokens",
            "final_uncached_input_tokens",
            "final_output_tokens",
            "final_reasoning_tokens",
            "input_per_output",
        ]
    ]


def diagnostics_df(
    threads: pd.DataFrame,
    usage: pd.DataFrame,
    events: pd.DataFrame,
    tools: pd.DataFrame,
    duplicated_blocks: pd.DataFrame,
) -> pd.DataFrame:
    columns = ["Priority", "Diagnostic", "Action", "Evidence"]
    if threads.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, str]] = []
    total_tokens = float(threads["final_total_tokens"].sum() or 1)
    largest = threads.sort_values("final_total_tokens", ascending=False).iloc[0]
    largest_share = float(largest["final_total_tokens"]) / total_tokens * 100
    rows.append(
        {
            "Priority": "High" if largest_share >= 50 else "Medium",
            "Diagnostic": "Largest thread drives the run",
            "Action": "Inspect this thread first; shortening its context or splitting its work is the most likely way to reduce cost.",
            "Evidence": f"{largest['label']} used {fmt_short(largest['final_total_tokens'])} tokens ({largest_share:.1f}% of thread totals).",
        }
    )

    jumps = token_jumps_df(usage, threads, limit=1)
    if not jumps.empty:
        jump = jumps.iloc[0]
        rows.append(
            {
                "Priority": "High"
                if float(jump["delta_input_tokens"] or 0) >= 10_000
                else "Medium",
                "Diagnostic": "Largest context jump",
                "Action": "Open the timeline around this point and look for large pasted context, command output, or a handoff/compaction boundary.",
                "Evidence": f"{jump['timestamp']} | {jump['label']} | +{fmt_short(jump['delta_input_tokens'])} input tokens.",
            }
        )

    if not tools.empty and "output_chars" in tools.columns:
        tool_rows = numericize(tools, ["output_chars"])
        largest_tool = tool_rows.sort_values("output_chars", ascending=False).head(1)
        if (
            not largest_tool.empty
            and int(largest_tool.iloc[0]["output_chars"] or 0) > 0
        ):
            row = largest_tool.iloc[0]
            tool_name = clean_value(row.get("tool_name")) or "unknown tool"
            command = (
                useful_text_preview(row.get("command"), 90)
                or "command omitted by privacy boundary"
            )
            rows.append(
                {
                    "Priority": "High"
                    if int(row["output_chars"] or 0) >= 20_000
                    else "Medium",
                    "Diagnostic": "Largest tool output",
                    "Action": "Consider narrowing this command or summarizing its output before feeding it back into the conversation.",
                    "Evidence": f"{tool_name} produced {fmt_short(row['output_chars'])} chars | {command}.",
                }
            )

    if not duplicated_blocks.empty:
        dup_total = int(
            pd.to_numeric(
                duplicated_blocks.get("approx_tokens_replayed"), errors="coerce"
            )
            .fillna(0)
            .sum()
        )
        if dup_total > 0:
            top_dup = duplicated_blocks.sort_values(
                "approx_tokens_replayed", ascending=False
            ).iloc[0]
            rows.append(
                {
                    "Priority": "High" if dup_total >= 10_000 else "Medium",
                    "Diagnostic": "Repeated prompt blocks",
                    "Action": "Look for reusable instructions or transcript blocks that can be referenced once instead of replayed into multiple workers.",
                    "Evidence": f"{fmt_short(dup_total)} approximate replayed tokens; top block {top_dup.get('label', 'unknown')} seen {fmt_int(top_dup.get('seen', 0))} times.",
                }
            )

    comps = compactions_df(events, usage, threads)
    if not comps.empty:
        rows.append(
            {
                "Priority": "Medium",
                "Diagnostic": "Context compaction occurred",
                "Action": "Inspect the thread before and after compaction; this marks a point where context became large enough to rewrite.",
                "Evidence": f"{len(comps)} compaction events across {comps['thread_id'].nunique()} threads.",
            }
        )

    guardians = threads[threads["kind"] == "guardian"]
    if not guardians.empty:
        guardian_input = int(guardians["final_input_tokens"].sum())
        guardian_output = int(
            (
                guardians["final_output_tokens"] + guardians["final_reasoning_tokens"]
            ).sum()
        )
        rows.append(
            {
                "Priority": "Medium" if guardian_input else "Low",
                "Diagnostic": "Guardian overhead",
                "Action": "Review whether approval prompts are replaying more context than needed for the decision being made.",
                "Evidence": f"{len(guardians)} guardian threads used {fmt_short(guardian_input)} input tokens and {fmt_short(guardian_output)} output+reasoning tokens.",
            }
        )

    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values("Priority", key=lambda s: s.map(priority_order))
        .reset_index(drop=True)
    )


PLAYBOOK_BY_DIAGNOSTIC = {
    "Run spans multiple days": (
        "Start a fresh Codex session at each durable checkpoint",
        "Multi-day sessions accumulate stale context and repeated approval overhead. Close the loop with a short handoff, then start a new session for the next phase.",
        "Targets long-running session accumulation.",
    ),
    "Largest thread drives the run": (
        "Set a stop condition for the dominant thread",
        "Long-lived root or worker threads usually explain the next run's cost. Split work earlier or ask the agent to stop after a concrete checkpoint.",
        "Targets the largest total-token driver.",
    ),
    "Largest context jump": (
        "Gate large context before it enters the chat",
        "Big jumps often come from pasted logs, broad file reads, or handoffs. Summarize, filter, or attach only the lines needed for the next decision.",
        "Targets sudden input-token growth.",
    ),
    "Largest tool output": (
        "Narrow bulky commands before sharing output",
        "Prefer targeted searches, counts, or saved artifacts over feeding full command output back into the conversation.",
        "Targets bulky tool-output feedback loops.",
    ),
    "Repeated prompt blocks": (
        "Reference stable instructions instead of replaying them",
        "Repeated launch prompts and transcript blocks compound across workers. Keep canonical instructions in files and point workers to the relevant section.",
        "Targets repeated prompt-token replay.",
    ),
    "Context compaction occurred": (
        "Create handoff checkpoints before compaction",
        "Compaction is a late signal that the run grew large. Write a short state summary before the model has to rewrite context under pressure.",
        "Targets late-run context churn.",
    ),
    "Guardian overhead": (
        "Limit approval context before guardian checks",
        "Approval threads should contain the decision, risk, and smallest useful evidence set rather than the full working context.",
        "Targets approval-context overhead.",
    ),
}


def next_run_playbook_df(diagnostics: pd.DataFrame, limit: int = 7) -> pd.DataFrame:
    columns = ["Step", "Habit", "Impact", "Why", "Source"]
    if diagnostics.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, str | int]] = []
    seen: set[str] = set()
    for _, row in diagnostics.iterrows():
        diagnostic = clean_value(row.get("Diagnostic"))
        if diagnostic in seen or diagnostic not in PLAYBOOK_BY_DIAGNOSTIC:
            continue
        habit, why, impact = PLAYBOOK_BY_DIAGNOSTIC[diagnostic]
        evidence = clean_value(row.get("Evidence"))
        rows.append(
            {
                "Step": len(rows) + 1,
                "Habit": habit,
                "Impact": impact,
                "Why": why,
                "Source": f"{diagnostic}: {evidence}" if evidence else diagnostic,
            }
        )
        seen.add(diagnostic)
        if len(rows) >= limit:
            break

    return pd.DataFrame(rows, columns=columns)


def opportunity_df(summary: dict[str, Any], limit: int = 4) -> pd.DataFrame:
    columns = ["Rank", "Habit", "Driver", "Scale", "Why"]
    total_tokens = float(summary.get("total_tokens") or 0)
    rows: list[dict[str, Any]] = []

    def token_scale(value: Any) -> str:
        share = float(value or 0) / (total_tokens or 1) * 100
        return f"{fmt_short(value)} tokens ({share:.1f}% of run)"

    def input_token_scale(value: Any) -> str:
        share = float(value or 0) / (total_tokens or 1) * 100
        return f"{fmt_short(value)} input tokens ({share:.1f}% of run)"

    duration_hours = float(summary.get("session_duration_hours") or 0)
    if duration_hours >= 24:
        days = duration_hours / 24
        rows.append(
            {
                "Habit": "Start a fresh Codex session at each durable checkpoint",
                "Driver": "Session duration",
                "Scale": f"{days:.1f} days",
                "Why": "Long-running sessions accumulate stale context; checkpointing and restarting makes the next run easier to control.",
                "_sort": int(summary.get("total_tokens") or 0) * 1.1,
            }
        )

    largest_thread = int(summary.get("largest_thread_tokens") or 0)
    if largest_thread > 0:
        rows.append(
            {
                "Habit": "Set a stop condition for the dominant thread",
                "Driver": "Largest thread",
                "Scale": token_scale(largest_thread),
                "Why": "This is the biggest aggregate token pool to shorten or split first.",
                "_sort": largest_thread,
            }
        )

    repeated = int(summary.get("repeated_prompt_tokens") or 0)
    if repeated > 0:
        rows.append(
            {
                "Habit": "Reference stable instructions instead of replaying them",
                "Driver": "Repeated prompt blocks",
                "Scale": token_scale(repeated),
                "Why": "These tokens are replayed context that can often move into a shared file or shorter reference.",
                "_sort": repeated,
            }
        )

    guardian_input = int(summary.get("guardian_input_tokens") or 0)
    if guardian_input > 0:
        rows.append(
            {
                "Habit": "Limit approval context before guardian checks",
                "Driver": "Guardian overhead",
                "Scale": input_token_scale(guardian_input),
                "Why": "Guardian approval threads can replay large context for small decisions; keep approvals narrow and checkpoint before they repeat.",
                "_sort": guardian_input,
            }
        )

    uncached = int(summary.get("uncached_input_tokens") or 0)
    if uncached > 0:
        rows.append(
            {
                "Habit": "Gate large context before it enters the chat",
                "Driver": "Uncached input",
                "Scale": token_scale(uncached),
                "Why": "Uncached input is the freshest context cost and is usually where filtering pays back quickly.",
                "_sort": uncached,
            }
        )

    tool_chars = int(summary.get("largest_tool_output_chars") or 0)
    if tool_chars > 0:
        rows.append(
            {
                "Habit": "Narrow bulky commands before sharing output",
                "Driver": "Largest tool output",
                "Scale": f"{fmt_short(tool_chars)} chars returned by one tool",
                "Why": "Large outputs often become expensive when they are pasted back into later turns.",
                "_sort": tool_chars / 4,
            }
        )

    compactions = int(summary.get("compactions") or 0)
    if compactions > 0:
        rows.append(
            {
                "Habit": "Create handoff checkpoints before compaction",
                "Driver": "Context compaction",
                "Scale": f"{fmt_int(compactions)} compaction event(s)",
                "Why": "Compaction is a late signal that the run outgrew its working context.",
                "_sort": compactions,
            }
        )

    if not rows:
        return pd.DataFrame(columns=columns)

    rows = sorted(rows, key=lambda row: float(row["_sort"] or 0), reverse=True)[:limit]
    for index, row in enumerate(rows, start=1):
        row["Rank"] = index
        row.pop("_sort", None)
    return pd.DataFrame(rows, columns=columns)


def findings_df(
    threads: pd.DataFrame, usage: pd.DataFrame, events: pd.DataFrame
) -> pd.DataFrame:
    findings = []
    if threads.empty:
        return pd.DataFrame(columns=["Finding", "Why it matters", "Evidence"])
    total = float(threads["final_total_tokens"].sum() or 1)
    guardians = threads[threads["kind"] == "guardian"]
    workers = threads[threads["kind"] == "worker"]
    largest = threads.sort_values("final_total_tokens", ascending=False).iloc[0]
    findings.append(
        {
            "Finding": "Largest thread dominates usage",
            "Why it matters": "A single long-lived thread often explains most token growth.",
            "Evidence": f"{largest['label']} used {fmt_short(largest['final_total_tokens'])} tokens ({largest['final_total_tokens'] / total * 100:.1f}% of thread totals).",
        }
    )
    if not guardians.empty:
        gtot = guardians["final_input_tokens"].sum()
        findings.append(
            {
                "Finding": "Guardian overhead",
                "Why it matters": "Guardian approvals can repeatedly replay large context with little output.",
                "Evidence": f"{len(guardians)} guardian threads used {fmt_short(gtot)} input tokens and {fmt_short(guardians['output_plus_reasoning'].sum())} output+reasoning tokens.",
            }
        )
    if not workers.empty:
        w = workers.sort_values("final_total_tokens", ascending=False).iloc[0]
        findings.append(
            {
                "Finding": "Most expensive worker",
                "Why it matters": "This is the best candidate to inspect for avoidable subagent work.",
                "Evidence": f"{w['label']} used {fmt_short(w['final_total_tokens'])} tokens across {fmt_int(w['tool_call_count'])} tools.",
            }
        )
    comps = compactions_df(events, usage, threads)
    if not comps.empty:
        findings.append(
            {
                "Finding": "Context compaction occurred",
                "Why it matters": "Compaction means at least one thread became large enough to require summarization/rewrite.",
                "Evidence": f"{len(comps)} compaction events found across {comps['thread_id'].nunique()} threads.",
            }
        )
    jumps = token_jumps_df(usage, threads, limit=1)
    if not jumps.empty:
        j = jumps.iloc[0]
        findings.append(
            {
                "Finding": "Largest token jump",
                "Why it matters": "Sudden jumps point to context replay, large tool output, or a major phase change.",
                "Evidence": f"{j['timestamp']} | {j['label']} | +{fmt_short(j['delta_input_tokens'])} input tokens.",
            }
        )
    return pd.DataFrame(findings)


def diagnostics_cards_html(diagnostics: pd.DataFrame) -> str:
    if diagnostics.empty:
        return ""
    cards = []
    for _, row in diagnostics.iterrows():
        priority = html.escape(clean_value(row.get("Priority")) or "Info")
        title = html.escape(clean_value(row.get("Diagnostic")) or "Diagnostic")
        action = html.escape(clean_value(row.get("Action")))
        evidence = html.escape(clean_value(row.get("Evidence")))
        cards.append(
            "\n".join(
                [
                    '<article class="co-diagnostic">',
                    f'  <div class="co-diagnostic-priority">{priority}</div>',
                    f"  <h3>{title}</h3>",
                    f'  <p class="co-diagnostic-action">{action}</p>',
                    f'  <p class="co-diagnostic-evidence">{evidence}</p>',
                    "</article>",
                ]
            )
        )
    return '<section class="co-diagnostics">\n' + "\n".join(cards) + "\n</section>"


def opportunity_html(opportunities: pd.DataFrame) -> str:
    if opportunities.empty:
        return ""
    cards = []
    for _, row in opportunities.iterrows():
        rank = html.escape(clean_value(row.get("Rank")))
        habit = html.escape(clean_value(row.get("Habit")))
        driver = html.escape(clean_value(row.get("Driver")))
        scale = html.escape(clean_value(row.get("Scale")))
        why = html.escape(clean_value(row.get("Why")))
        cards.append(
            "\n".join(
                [
                    '<article class="co-opportunity">',
                    f'  <div class="co-opportunity-rank">{rank}</div>',
                    "  <div>",
                    f"    <h3>{habit}</h3>",
                    f'    <p class="co-opportunity-scale">{driver}: {scale}</p>',
                    f"    <p>{why}</p>",
                    "  </div>",
                    "</article>",
                ]
            )
        )
    return '<section class="co-opportunities">\n' + "\n".join(cards) + "\n</section>"


def playbook_html(playbook: pd.DataFrame) -> str:
    if playbook.empty:
        return ""
    cards = []
    for _, row in playbook.iterrows():
        step = html.escape(clean_value(row.get("Step")))
        habit = html.escape(clean_value(row.get("Habit")))
        impact = html.escape(clean_value(row.get("Impact")))
        why = html.escape(clean_value(row.get("Why")))
        source = html.escape(clean_value(row.get("Source")))
        cards.append(
            "\n".join(
                [
                    '<article class="co-playbook-step">',
                    f'  <div class="co-playbook-number">{step}</div>',
                    "  <div>",
                    f"    <h3>{habit}</h3>",
                    f'    <p class="co-playbook-impact">{impact}</p>',
                    f"    <p>{why}</p>",
                    f"    <p>{source}</p>",
                    "  </div>",
                    "</article>",
                ]
            )
        )
    return '<section class="co-playbook">\n' + "\n".join(cards) + "\n</section>"
