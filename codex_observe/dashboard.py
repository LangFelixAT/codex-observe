from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(Path.home() / ".codex-observe" / "codex_observe.sqlite"))
    args, _ = p.parse_known_args()
    return args


@st.cache_data(show_spinner=False)
def read_sql(db: str, query: str, params: tuple = ()) -> pd.DataFrame:
    with sqlite3.connect(db) as conn:
        return pd.read_sql_query(query, conn, params=params)


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
            branch = "└── " if last else "├── "
            child_prefix = prefix + ("    " if last else "│   ")
            label = r.get("label") or role_label(r)
            short = (r.get("thread_id") or "")[-8:]
            toks = fmt_short(r.get("final_input_tokens", 0))
            uncached = fmt_short(r.get("final_uncached_input_tokens", 0))
            tools = fmt_int(r.get("tool_call_count", 0))
            lines.append(f"{prefix}{branch}{label} [{short}] input={toks}, uncached={uncached}, tools={tools}")
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
    threads = numericize(threads, [
        "event_count", "turn_count", "tool_call_count", "final_input_tokens",
        "final_cached_input_tokens", "final_uncached_input_tokens", "final_output_tokens",
        "final_reasoning_tokens", "final_total_tokens", "base_instruction_chars",
    ])
    threads["kind"] = threads.apply(thread_kind, axis=1)
    threads["label"] = threads.apply(role_label, axis=1)
    threads["cache_pct"] = threads["final_cached_input_tokens"] / threads["final_input_tokens"].replace(0, 1) * 100
    threads["output_plus_reasoning"] = threads["final_output_tokens"] + threads["final_reasoning_tokens"]
    threads["input_per_output"] = threads["final_input_tokens"] / threads["output_plus_reasoning"].replace(0, 1)
    threads["tokens_per_tool"] = threads["final_total_tokens"] / threads["tool_call_count"].replace(0, 1)
    return threads


def load_events_for_session(db: str, session_id: str) -> pd.DataFrame:
    return read_sql(db, """
        SELECT e.*
        FROM events e
        JOIN threads t ON t.thread_id = e.thread_id
        WHERE t.session_id=?
        ORDER BY e.timestamp, e.idx
    """, (session_id,))


def load_messages_for_session(db: str, session_id: str) -> pd.DataFrame:
    return read_sql(db, """
        SELECT m.*
        FROM messages m
        JOIN threads t ON t.thread_id = m.thread_id
        WHERE t.session_id=?
        ORDER BY m.timestamp
    """, (session_id,))


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
                return useful_text_preview(goal.get("objective") or goal.get("title") or goal, 500)
            return useful_text_preview(goal, 500)
    msgs = messages[messages["thread_id"] == thread_id]
    for _, m in msgs.iterrows():
        text = clean_value(m.get("text"))
        if not text:
            continue
        if text.startswith("# AGENTS.md instructions") or text.startswith("<environment_context>") or text.startswith("<INSTRUCTIONS>"):
            continue
        if "The following is the Codex agent history" in text:
            continue
        return useful_text_preview(text, 500)
    return ""


def compactions_df(events: pd.DataFrame, usage: pd.DataFrame, threads: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    mask = (events["type"] == "compacted") | (events["payload_type"] == "context_compacted")
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
        rows.append({
            "timestamp": e["timestamp"],
            "thread": label,
            "thread_id": tid,
            "event_type": e["type"] if e["type"] == "compacted" else e["payload_type"],
            "input_before": before_tok,
            "input_after_next_snapshot": after_tok,
            "delta_to_next_snapshot": after_tok - before_tok,
        })
    return pd.DataFrame(rows).sort_values("timestamp")


def token_jumps_df(usage: pd.DataFrame, threads: pd.DataFrame, limit: int = 30) -> pd.DataFrame:
    if usage.empty:
        return pd.DataFrame()
    u = numericize(usage, ["idx", "input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"])
    u = u.sort_values(["thread_id", "idx"]).copy()
    for col in ["input_tokens", "uncached_input_tokens", "total_tokens"]:
        u[f"delta_{col}"] = u.groupby("thread_id")[col].diff().fillna(u[col])
    u = u.merge(threads[["thread_id", "label", "kind"]], on="thread_id", how="left")
    cols = ["timestamp", "label", "kind", "thread_id", "delta_input_tokens", "delta_uncached_input_tokens", "delta_total_tokens", "input_tokens", "total_tokens"]
    return u.sort_values("delta_input_tokens", ascending=False)[cols].head(limit)


def guardian_overhead_df(threads: pd.DataFrame) -> pd.DataFrame:
    g = threads[threads["kind"] == "guardian"].copy()
    if g.empty:
        return pd.DataFrame()
    g["output_plus_reasoning"] = g["final_output_tokens"] + g["final_reasoning_tokens"]
    g["input_per_output"] = g["final_input_tokens"] / g["output_plus_reasoning"].replace(0, 1)
    return g.sort_values("final_input_tokens", ascending=False)[[
        "label", "first_seen", "last_seen", "thread_id", "final_input_tokens", "final_cached_input_tokens",
        "final_uncached_input_tokens", "final_output_tokens", "final_reasoning_tokens", "input_per_output"
    ]]


def findings_df(threads: pd.DataFrame, usage: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    findings = []
    if threads.empty:
        return pd.DataFrame(columns=["Finding", "Why it matters", "Evidence"])
    total = float(threads["final_total_tokens"].sum() or 1)
    root = threads[threads["kind"] == "root"]
    guardians = threads[threads["kind"] == "guardian"]
    workers = threads[threads["kind"] == "worker"]
    largest = threads.sort_values("final_total_tokens", ascending=False).iloc[0]
    findings.append({
        "Finding": "Largest thread dominates usage",
        "Why it matters": "A single long-lived thread often explains most token growth.",
        "Evidence": f"{largest['label']} used {fmt_short(largest['final_total_tokens'])} tokens ({largest['final_total_tokens']/total*100:.1f}% of thread totals).",
    })
    if not guardians.empty:
        gtot = guardians["final_input_tokens"].sum()
        findings.append({
            "Finding": "Guardian overhead",
            "Why it matters": "Guardian approvals can repeatedly replay large context with little output.",
            "Evidence": f"{len(guardians)} guardian threads used {fmt_short(gtot)} input tokens and {fmt_short(guardians['output_plus_reasoning'].sum())} output+reasoning tokens.",
        })
    if not workers.empty:
        w = workers.sort_values("final_total_tokens", ascending=False).iloc[0]
        findings.append({
            "Finding": "Most expensive worker",
            "Why it matters": "This is the best candidate to inspect for avoidable subagent work.",
            "Evidence": f"{w['label']} used {fmt_short(w['final_total_tokens'])} tokens across {fmt_int(w['tool_call_count'])} tools.",
        })
    comps = compactions_df(events, usage, threads)
    if not comps.empty:
        findings.append({
            "Finding": "Context compaction occurred",
            "Why it matters": "Compaction means at least one thread became large enough to require summarization/rewrite.",
            "Evidence": f"{len(comps)} compaction events found across {comps['thread_id'].nunique()} threads.",
        })
    jumps = token_jumps_df(usage, threads, limit=1)
    if not jumps.empty:
        j = jumps.iloc[0]
        findings.append({
            "Finding": "Largest token jump",
            "Why it matters": "Sudden jumps point to context replay, large tool output, or a major phase change.",
            "Evidence": f"{j['timestamp']} · {j['label']} · +{fmt_short(j['delta_input_tokens'])} input tokens.",
        })
    return pd.DataFrame(findings)


def render_agent_detail(selected_thread: pd.Series, threads: pd.DataFrame, usage: pd.DataFrame, tools: pd.DataFrame, messages: pd.DataFrame, events: pd.DataFrame) -> None:
    tid = selected_thread["thread_id"]
    st.subheader(selected_thread["label"])
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Kind", selected_thread["kind"])
    c2.metric("Input", fmt_short(selected_thread["final_input_tokens"]))
    c3.metric("Uncached", fmt_short(selected_thread["final_uncached_input_tokens"]))
    c4.metric("Tools", fmt_int(selected_thread["tool_call_count"]))
    c5.metric("Events", fmt_int(selected_thread["event_count"]))
    c6.metric("Cache", f"{selected_thread['cache_pct']:.1f}%")

    goal = worker_goal(messages, events, tid)
    if goal:
        st.markdown("**Likely goal / launch prompt**")
        st.info(goal)

    ut = usage[usage["thread_id"] == tid].copy()
    if not ut.empty:
        st.markdown("**Token timeline for this thread**")
        ut["timestamp"] = pd.to_datetime(ut["timestamp"], errors="coerce")
        st.line_chart(ut.set_index("timestamp")[["input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens", "reasoning_tokens"]])
        jumps = token_jumps_df(ut, threads, limit=10)
        if not jumps.empty:
            st.markdown("**Largest jumps in this thread**")
            st.dataframe(jumps, use_container_width=True, hide_index=True)

    comps = compactions_df(events[events["thread_id"] == tid], usage, threads)
    if not comps.empty:
        st.markdown("**Context compactions in this thread**")
        st.dataframe(comps, use_container_width=True, hide_index=True)

    tt = tools[tools["thread_id"] == tid].copy()
    if not tt.empty:
        st.markdown("**Tools in this thread**")
        by_tool = tt.groupby("tool_name", dropna=False).agg(calls=("call_id", "count"), output_chars=("output_chars", "sum")).reset_index().sort_values("calls", ascending=False)
        st.dataframe(by_tool, use_container_width=True, hide_index=True)
        st.dataframe(tt[["timestamp", "tool_name", "command", "workdir", "output_chars", "success"]], use_container_width=True, hide_index=True)

    mm = messages[messages["thread_id"] == tid].copy()
    if not mm.empty:
        st.markdown("**Messages / transcript snippets**")
        show = mm.copy()
        show["preview"] = show["text"].map(lambda x: useful_text_preview(x, 500))
        st.dataframe(show[["timestamp", "role", "source", "char_count", "approx_tokens", "preview"]].tail(50), use_container_width=True, hide_index=True)


def main() -> None:
    args = parse_args()
    db = str(Path(args.db).expanduser())
    st.set_page_config(page_title="Codex Observe", layout="wide")
    st.title("Codex Observe")
    st.caption("Offline dashboard for `.codex/sessions/**/*.jsonl` logs")

    if not Path(db).exists():
        st.error(f"Database not found: {db}. Run `codex-observe ingest ~/.codex/sessions --db {db}` first.")
        return

    conversations = read_sql(db, """
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
    """)
    if conversations.empty:
        st.warning("No conversations imported yet.")
        return

    with st.sidebar:
        st.header("Database")
        st.code(db)
        st.metric("Conversations", len(conversations))
        st.markdown("### Conversations")
        if "selected_session_id" not in st.session_state:
            st.session_state["selected_session_id"] = conversations.iloc[0]["session_id"]
        last_date = None
        for _, row in conversations.iterrows():
            day = str(row.get("last_seen") or "")[:10]
            if day != last_date:
                st.markdown(f"#### {day or 'Unknown date'}")
                last_date = day
            preview = useful_text_preview(row.get("preview") or row["session_id"], 72)
            selected = row["session_id"] == st.session_state["selected_session_id"]
            label = ("▶ " if selected else "") + preview
            if st.button(label, key=f"conv_{row['session_id']}", use_container_width=True):
                st.session_state["selected_session_id"] = row["session_id"]
                st.rerun()
            if selected:
                bits = []
                t = sidebar_time_label(row.get("last_seen"))
                if t:
                    bits.append(t)
                bits.append(f"{int(row.get('thread_count') or 0)} threads")
                bits.append(f"{fmt_int(row.get('sidebar_tool_calls') or 0)} tools")
                bits.append(f"{fmt_short(row.get('total_tokens') or 0)} tokens")
                st.caption(" • ".join(bits))
        session_id = st.session_state["selected_session_id"]

    conv = conversations[conversations.session_id == session_id].iloc[0]
    threads = read_sql(db, "SELECT * FROM threads WHERE session_id=? ORDER BY created_at, first_seen", (session_id,))
    usage = read_sql(db, "SELECT * FROM usage_snapshots WHERE thread_id IN (SELECT thread_id FROM threads WHERE session_id=?) ORDER BY timestamp, idx", (session_id,))
    tools = read_sql(db, "SELECT * FROM tool_calls WHERE thread_id IN (SELECT thread_id FROM threads WHERE session_id=?) ORDER BY timestamp", (session_id,))
    events = load_events_for_session(db, session_id)
    messages = load_messages_for_session(db, session_id)

    threads = prepare_threads(threads)
    usage = numericize(usage, ["idx", "input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "last_input_tokens", "last_total_tokens"])
    tools = numericize(tools, ["timeout_ms", "success", "duration_ms", "output_chars"])

    cache_pct = (int(conv.total_cached_input_tokens or 0) / int(conv.total_input_tokens or 1)) * 100
    workers = int((threads["kind"] == "worker").sum())
    guardians = int((threads["kind"] == "guardian").sum())
    explorers = int((threads["kind"] == "explorer").sum())
    tool_total = int(threads["tool_call_count"].fillna(0).sum())
    largest_thread = threads.sort_values("final_total_tokens", ascending=False).iloc[0] if not threads.empty else None
    compactions = compactions_df(events, usage, threads)

    c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
    c1.metric("Threads", fmt_int(conv.thread_count))
    c2.metric("Workers", fmt_int(workers))
    c3.metric("Explorers", fmt_int(explorers))
    c4.metric("Guardians", fmt_int(guardians))
    c5.metric("Tools", fmt_int(tool_total))
    c6.metric("Cache hit", f"{cache_pct:.1f}%")
    c7.metric("Compactions", fmt_int(len(compactions)))
    c8.metric("Largest thread", fmt_short(largest_thread["final_total_tokens"] if largest_thread is not None else 0))

    tab_overview, tab_agent, tab_timeline, tab_tools, tab_dup, tab_raw = st.tabs([
        "Overview", "Agent detail", "Timeline & jumps", "Tools", "Duplication", "Raw tables"
    ])

    with tab_overview:
        st.subheader("Why this run was expensive")
        st.dataframe(findings_df(threads, usage, events), use_container_width=True, hide_index=True)

        st.subheader("Conversation tree")
        st.code(build_tree(threads, session_id), language="text")

        st.subheader("Cost attribution by agent/thread")
        attrib = threads.sort_values("final_total_tokens", ascending=False).copy()
        total_tokens = float(attrib["final_total_tokens"].sum() or 1)
        attrib["share_pct"] = attrib["final_total_tokens"] / total_tokens * 100
        st.dataframe(attrib[["label", "kind", "final_total_tokens", "final_uncached_input_tokens", "tool_call_count", "share_pct", "cache_pct"]], use_container_width=True, hide_index=True)
        st.bar_chart(attrib.set_index("label")[["final_uncached_input_tokens", "final_cached_input_tokens", "final_output_tokens", "final_reasoning_tokens"]])

        st.subheader("Cost attribution by role/source")
        role_summary = threads.groupby("label", dropna=False)[[
            "final_input_tokens", "final_cached_input_tokens", "final_uncached_input_tokens",
            "final_output_tokens", "final_reasoning_tokens", "tool_call_count",
        ]].sum().reset_index().sort_values("final_input_tokens", ascending=False)
        st.dataframe(role_summary, use_container_width=True, hide_index=True)

        st.subheader("Efficiency / overhead indicators")
        eff = threads.sort_values("input_per_output", ascending=False).copy()
        st.dataframe(eff[["label", "kind", "final_input_tokens", "output_plus_reasoning", "input_per_output", "tokens_per_tool", "tool_call_count", "cache_pct"]], use_container_width=True, hide_index=True)

        st.subheader("Guardian overhead")
        gh = guardian_overhead_df(threads)
        if gh.empty:
            st.info("No guardian threads found in this conversation.")
        else:
            g_total_in = int(gh["final_input_tokens"].sum())
            g_total_out = int((gh["final_output_tokens"] + gh["final_reasoning_tokens"]).sum())
            gc1, gc2, gc3, gc4 = st.columns(4)
            gc1.metric("Guardian runs", fmt_int(len(gh)))
            gc2.metric("Guardian input", fmt_short(g_total_in))
            gc3.metric("Output + reasoning", fmt_short(g_total_out))
            gc4.metric("Input/output ratio", fmt_short(g_total_in / max(g_total_out, 1)))
            st.dataframe(gh, use_container_width=True, hide_index=True)

    with tab_agent:
        st.subheader("Worker / thread detail")
        options = []
        for _, r in threads.sort_values("final_total_tokens", ascending=False).iterrows():
            options.append((f"{r['label']} · {fmt_short(r['final_total_tokens'])} · {r['thread_id'][-8:]}", r["thread_id"]))
        if options:
            selected_label = st.selectbox("Select a thread", [o[0] for o in options])
            selected_tid = dict(options)[selected_label]
            selected_thread = threads[threads["thread_id"] == selected_tid].iloc[0]
            render_agent_detail(selected_thread, threads, usage, tools, messages, events)

    with tab_timeline:
        st.subheader("Spawn graph / thread lifecycle")
        lifecycle = threads[["label", "kind", "thread_id", "parent_thread_id", "first_seen", "last_seen", "final_total_tokens", "tool_call_count"]].sort_values("first_seen")
        st.dataframe(lifecycle, use_container_width=True, hide_index=True)
        st.code(build_tree(threads, session_id), language="text")

        st.subheader("Largest token jumps")
        jumps = token_jumps_df(usage, threads, limit=50)
        if jumps.empty:
            st.info("No token snapshots found.")
        else:
            st.dataframe(jumps, use_container_width=True, hide_index=True)

        st.subheader("Context growth snapshots")
        if usage.empty:
            st.info("No usage snapshots found.")
        else:
            timeline = usage.merge(threads[["thread_id", "label"]], on="thread_id", how="left")
            timeline["timestamp"] = pd.to_datetime(timeline["timestamp"], errors="coerce")
            st.line_chart(timeline.set_index("timestamp")[["input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens", "reasoning_tokens"]])

        st.subheader("Context compactions")
        if compactions.empty:
            st.info("No context compaction events found.")
        else:
            st.dataframe(compactions, use_container_width=True, hide_index=True)

    with tab_tools:
        st.subheader("Tool calls")
        if tools.empty:
            st.info("No tool calls found in this conversation.")
        else:
            by_tool = tools.groupby("tool_name", dropna=False).agg(calls=("call_id", "count"), output_chars=("output_chars", "sum")).reset_index().sort_values("calls", ascending=False)
            st.subheader("Tool distribution")
            st.dataframe(by_tool, use_container_width=True, hide_index=True)
            st.bar_chart(by_tool.set_index("tool_name")["calls"])

            st.subheader("Tool calls by thread")
            tools_by_thread = tools.groupby("thread_id").agg(calls=("call_id", "count"), output_chars=("output_chars", "sum")).reset_index()
            tools_by_thread = tools_by_thread.merge(threads[["thread_id", "label", "kind", "final_total_tokens"]], on="thread_id", how="left").sort_values("calls", ascending=False)
            tools_by_thread["tokens_per_tool"] = tools_by_thread["final_total_tokens"] / tools_by_thread["calls"].replace(0, 1)
            st.dataframe(tools_by_thread, use_container_width=True, hide_index=True)

            st.subheader("Largest tool outputs")
            st.dataframe(tools.sort_values("output_chars", ascending=False)[["timestamp", "thread_id", "tool_name", "command", "output_chars", "success"]].head(100), use_container_width=True, hide_index=True)

            st.subheader("Raw tool calls")
            st.dataframe(tools[["timestamp", "thread_id", "tool_name", "command", "workdir", "output_chars", "success"]], use_container_width=True, hide_index=True)

    with tab_dup:
        st.subheader("Repeated prompt blocks")
        dup = read_sql(db, """
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
        """, (session_id,))
        if dup.empty:
            st.info("No repeated large prompt blocks found with the current heuristics.")
        else:
            d1, d2, d3 = st.columns(3)
            d1.metric("Repeated approx tokens", fmt_short(dup["approx_tokens_replayed"].sum()))
            d2.metric("Repeated blocks", fmt_int(len(dup)))
            d3.metric("Threads involved", fmt_int(dup["threads"].max()))
            by_label = dup.groupby("label").agg(blocks=("block_hash", "count"), replayed_tokens=("approx_tokens_replayed", "sum"), seen=("seen", "sum")).reset_index().sort_values("replayed_tokens", ascending=False)
            st.subheader("Duplication breakdown")
            st.dataframe(by_label, use_container_width=True, hide_index=True)
            st.bar_chart(by_label.set_index("label")["replayed_tokens"])
            st.subheader("Repeated blocks")
            st.dataframe(dup, use_container_width=True, hide_index=True)
        st.caption("Duplication tokens are approximate text-fragment estimates. Authoritative usage totals still come from Codex token_count events.")

    with tab_raw:
        st.subheader("Conversations")
        st.dataframe(conversations, use_container_width=True, hide_index=True)
        st.subheader("Threads")
        st.dataframe(threads, use_container_width=True, hide_index=True)
        st.subheader("Usage snapshots")
        st.dataframe(usage, use_container_width=True, hide_index=True)
        st.subheader("Events")
        st.dataframe(events, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
