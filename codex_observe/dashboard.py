from __future__ import annotations
from datetime import datetime

import argparse
import sqlite3
from pathlib import Path

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


def fmt_int(x) -> str:
    try:
        return f"{int(x):,}"
    except Exception:
        return "0"

def parse_ts(ts):
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


def sidebar_time_label(ts) -> str:
    d = parse_ts(ts)
    if d is None:
        return ""
    return d.strftime("%H:%M")


def short_millions(x) -> str:
    try:
        x = float(x or 0)
    except Exception:
        return "0"
    if x >= 1_000_000:
        return f"{x / 1_000_000:.1f}M"
    if x >= 1_000:
        return f"{x / 1_000:.1f}k"
    return str(int(x))


def clean_value(x) -> str:
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
        parent = r.get("parent_thread_id")
        if parent not in ids:
            parent = "__root__"
        by_parent.setdefault(parent, []).append(r)
    for v in by_parent.values():
        v.sort(key=lambda r: r.get("created_at") or r.get("first_seen") or "")

    lines: list[str] = []
    def rec(parent: str, prefix: str = ""):
        children = by_parent.get(parent, [])
        for i, r in enumerate(children):
            last = i == len(children) - 1
            branch = "└── " if last else "├── "
            child_prefix = prefix + ("    " if last else "│   ")
            label = role_label(r)
            short = (r["thread_id"] or "")[-8:]
            toks = fmt_int(r.get("final_input_tokens", 0))
            cached = fmt_int(r.get("final_cached_input_tokens", 0))
            tools = fmt_int(r.get("tool_call_count", 0))
            lines.append(f"{prefix}{branch}{label} [{short}] input={toks}, cached={cached}, tools={tools}")
            rec(r["thread_id"], child_prefix)
    lines.append(f"Conversation {root_session}")
    rec("__root__")
    return "\n".join(lines)


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
        SELECT
        c.*,
        COALESCE(tc.sidebar_tool_calls, 0) AS sidebar_tool_calls,
        COALESCE(
            (
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
            ORDER BY m.timestamp ASC
            LIMIT 1
            ),
            c.session_id
        ) AS preview
        FROM conversations c
        LEFT JOIN (
            SELECT
                session_id,
                COALESCE(SUM(tool_call_count), 0) AS sidebar_tool_calls
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

            preview = str(row.get("preview") or row["session_id"]).replace("\n", " ").strip()
            if len(preview) > 72:
                preview = preview[:69] + "..."

            selected = row["session_id"] == st.session_state["selected_session_id"]
            label = ("▶ " if selected else "") + preview

            if st.button(label, key=f"conv_{row['session_id']}", use_container_width=True):
                st.session_state["selected_session_id"] = row["session_id"]
                st.rerun()

            if selected:
                bits = []

                time_label = sidebar_time_label(row.get("last_seen"))
                if time_label:
                    bits.append(time_label)

                bits.append(f"{int(row.get('thread_count') or 0)} threads")
                bits.append(f"{fmt_int(row.get('sidebar_tool_calls') or 0)} tools")
                bits.append(f"{fmt_int(row.get('total_tokens') or 0)} tokens")

                st.caption(" • ".join(bits))

        session_id = st.session_state["selected_session_id"]

    conv = conversations[conversations.session_id == session_id].iloc[0]
    threads = read_sql(db, "SELECT * FROM threads WHERE session_id=? ORDER BY created_at, first_seen", (session_id,))
    usage = read_sql(db, "SELECT * FROM usage_snapshots WHERE thread_id IN (SELECT thread_id FROM threads WHERE session_id=?) ORDER BY timestamp, idx", (session_id,))
    tools = read_sql(db, "SELECT * FROM tool_calls WHERE thread_id IN (SELECT thread_id FROM threads WHERE session_id=?) ORDER BY timestamp", (session_id,))
    threads = threads.copy()
    threads["kind"] = threads.apply(thread_kind, axis=1)
    threads["label"] = threads.apply(role_label, axis=1)

    uncached = int(conv.total_uncached_input_tokens or 0)
    cache_pct = (int(conv.total_cached_input_tokens or 0) / int(conv.total_input_tokens or 1)) * 100

    workers = int((threads["kind"] == "worker").sum())
    guardians = int((threads["kind"] == "guardian").sum())
    explorers = int((threads["kind"] == "explorer").sum())
    tool_total = int(threads["tool_call_count"].fillna(0).sum())
    largest_thread = threads.sort_values("final_total_tokens", ascending=False).iloc[0] if not threads.empty else None

    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric("Threads", fmt_int(conv.thread_count))
    c2.metric("Workers", fmt_int(workers))
    c3.metric("Explorers", fmt_int(explorers))
    c4.metric("Guardians", fmt_int(guardians))
    c5.metric("Tools", fmt_int(tool_total))
    c6.metric("Cache hit", f"{cache_pct:.1f}%")
    c7.metric("Largest thread", short_millions(largest_thread["final_total_tokens"] if largest_thread is not None else 0))

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "Threads", "Tools", "Duplication", "Raw tables"])

    with tab1:
        st.subheader("Conversation tree")
        st.code(build_tree(threads, session_id), language="text")

        by_role = threads.copy()
        by_role["role"] = by_role.apply(role_label, axis=1)
        role_summary = by_role.groupby("role", dropna=False)[[
            "final_input_tokens", "final_cached_input_tokens", "final_uncached_input_tokens", "final_output_tokens", "final_reasoning_tokens", "tool_call_count"
        ]].sum().reset_index().sort_values("final_input_tokens", ascending=False)
        st.subheader("Token attribution by role/source")
        st.dataframe(role_summary, use_container_width=True, hide_index=True)
        if not role_summary.empty:
            st.bar_chart(role_summary.set_index("role")[["final_uncached_input_tokens", "final_cached_input_tokens", "final_output_tokens", "final_reasoning_tokens"]])

        st.subheader("Top agents by tokens")
        top_agents = threads.copy()
        top_agents["cache_pct"] = top_agents["final_cached_input_tokens"] / top_agents["final_input_tokens"].replace(0, 1) * 100
        top_agents = top_agents.sort_values("final_total_tokens", ascending=False)

        st.dataframe(
            top_agents[[
                "label", "kind", "first_seen", "last_seen",
                "tool_call_count", "final_input_tokens", "final_cached_input_tokens",
                "final_uncached_input_tokens", "final_output_tokens",
                "final_reasoning_tokens", "final_total_tokens", "cache_pct"
            ]],
            use_container_width=True,
            hide_index=True,
        )

        if not usage.empty:
            st.subheader("Context growth snapshots")
            timeline = usage.copy()
            timeline["timestamp"] = pd.to_datetime(timeline["timestamp"], errors="coerce")
            st.line_chart(timeline.set_index("timestamp")[["input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"]])

    with tab2:
        st.subheader("Threads")
        cols = ["created_at", "thread_id", "parent_thread_id", "thread_source", "source_kind", "agent_role", "agent_nickname", "turn_count", "tool_call_count", "final_input_tokens", "final_cached_input_tokens", "final_uncached_input_tokens", "final_output_tokens", "final_reasoning_tokens", "base_instruction_chars", "file_path"]
        st.dataframe(threads[[c for c in cols if c in threads.columns]], use_container_width=True, hide_index=True)

        st.subheader("Potential overhead indicators")
        overhead = threads.copy()
        overhead["role"] = overhead.apply(role_label, axis=1)
        overhead["input_per_output"] = overhead["final_input_tokens"] / overhead["final_output_tokens"].replace(0, 1)
        overhead["cached_pct"] = overhead["final_cached_input_tokens"] / overhead["final_input_tokens"].replace(0, 1) * 100
        overhead = overhead.sort_values("input_per_output", ascending=False)
        st.dataframe(overhead[["created_at", "role", "thread_id", "final_input_tokens", "final_output_tokens", "input_per_output", "cached_pct", "tool_call_count"]], use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("Tool calls")
        if tools.empty:
            st.info("No tool calls found in this conversation.")
        else:
            by_tool = tools.groupby("tool_name", dropna=False).agg(
                calls=("call_id", "count"),
                output_chars=("output_chars", "sum"),
            ).reset_index().sort_values("calls", ascending=False)

            st.subheader("Tool distribution")
            st.dataframe(by_tool, use_container_width=True, hide_index=True)
            st.bar_chart(by_tool.set_index("tool_name")["calls"])

            st.subheader("Tool calls by thread")
            tools_by_thread = tools.groupby("thread_id").agg(
                calls=("call_id", "count"),
                output_chars=("output_chars", "sum"),
            ).reset_index()
            tools_by_thread = tools_by_thread.merge(
                threads[["thread_id", "label", "kind"]],
                on="thread_id",
                how="left",
            ).sort_values("calls", ascending=False)

            st.dataframe(tools_by_thread, use_container_width=True, hide_index=True)

            st.subheader("Raw tool calls")
            st.dataframe(
                tools[["timestamp", "thread_id", "tool_name", "command", "workdir", "output_chars", "success"]],
                use_container_width=True,
                hide_index=True,
            )

    with tab4:
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
            LIMIT 200
        """, (session_id,))
        if dup.empty:
            st.info("No repeated large prompt blocks found with the current heuristics.")
        else:
            st.metric("Repeated-block approx tokens", fmt_int(dup["approx_tokens_replayed"].sum()))
            st.dataframe(dup, use_container_width=True, hide_index=True)

        st.caption("This uses approximate token counts for text fragments. Authoritative totals are still taken from Codex token_count events.")

    with tab5:
        st.subheader("Conversations")
        st.dataframe(conversations, use_container_width=True, hide_index=True)
        st.subheader("Usage snapshots")
        st.dataframe(usage, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
