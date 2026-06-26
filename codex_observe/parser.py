from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .schema import SCHEMA_SQL


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_event_pk(thread_id: str, idx: int, raw: str) -> str:
    return hashlib.sha256(f"{thread_id}:{idx}:".encode() + raw.encode("utf-8", "replace")).hexdigest()


def approx_tokens(text: str) -> int:
    # Cheap approximation. The authoritative token counts come from token_count events.
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def sqlite_scalar(value: Any) -> Any:
    """Return a SQLite-bindable scalar, JSON-encoding containers defensively."""
    if value is None or isinstance(value, (str, int, float, bytes)):
        return value
    if isinstance(value, bool):
        return int(value)
    return json_dumps(value)


def get_turn_id(payload: dict[str, Any]) -> str | None:
    return (
        payload.get("turn_id")
        or payload.get("internal_chat_message_metadata_passthrough", {}).get("turn_id")
        or payload.get("metadata", {}).get("turn_id")
    )


def source_kind(source: Any) -> str | None:
    if isinstance(source, str):
        return source
    if isinstance(source, dict):
        if "subagent" in source:
            sub = source.get("subagent") or {}
            if isinstance(sub, dict):
                if sub.get("other"):
                    return sub.get("other")
                if isinstance(sub.get("thread_spawn"), dict):
                    return "thread_spawn"
                return sub.get("agent_role") or "subagent"
            return "subagent"
        return next(iter(source.keys()), None)
    return None


def extract_agent(meta: dict[str, Any]) -> tuple[str | None, str | None]:
    src = meta.get("source")
    role = None
    nick = None
    if isinstance(src, dict):
        sub = src.get("subagent")
        if isinstance(sub, dict):
            spawn = sub.get("thread_spawn") if isinstance(sub.get("thread_spawn"), dict) else {}
            role = spawn.get("agent_role") or sub.get("agent_role") or sub.get("role") or sub.get("other")
            nick = spawn.get("agent_nickname") or sub.get("agent_nickname") or sub.get("nickname")
    return role, nick or ""


def read_jsonl(path: Path) -> list[tuple[int, dict[str, Any], str]]:
    rows = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, raw in enumerate(f):
            raw = raw.rstrip("\n")
            if not raw.strip():
                continue
            try:
                rows.append((idx, json.loads(raw), raw))
            except json.JSONDecodeError:
                # Keep going; schema drift / partial writes should not kill ingestion.
                continue
    return rows


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("input_text"), str):
                    parts.append(item["input_text"])
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return ""


def extract_message_text(payload: dict[str, Any]) -> tuple[str | None, str]:
    pt = payload.get("type")
    if pt == "message":
        return payload.get("role"), text_from_content(payload.get("content"))
    if pt in {"user_message", "agent_message"}:
        return ("user" if pt == "user_message" else "assistant"), payload.get("message") or ""
    return None, ""


def usage_from_payload(payload: dict[str, Any]) -> dict[str, int] | None:
    if payload.get("type") != "token_count":
        return None
    info = payload.get("info") or {}
    total = info.get("total_token_usage") or {}
    last = info.get("last_token_usage") or {}
    def g(d: dict[str, Any], key: str) -> int:
        v = d.get(key, 0)
        return int(v or 0)
    return {
        "input_tokens": g(total, "input_tokens"),
        "cached_input_tokens": g(total, "cached_input_tokens"),
        "uncached_input_tokens": max(0, g(total, "input_tokens") - g(total, "cached_input_tokens")),
        "output_tokens": g(total, "output_tokens"),
        "reasoning_tokens": g(total, "reasoning_output_tokens"),
        "total_tokens": g(total, "total_tokens"),
        "last_input_tokens": g(last, "input_tokens"),
        "last_cached_input_tokens": g(last, "cached_input_tokens"),
        "last_uncached_input_tokens": max(0, g(last, "input_tokens") - g(last, "cached_input_tokens")),
        "last_output_tokens": g(last, "output_tokens"),
        "last_reasoning_tokens": g(last, "reasoning_output_tokens"),
        "last_total_tokens": g(last, "total_tokens"),
        "model_context_window": int(info.get("model_context_window") or 0),
    }


def parse_tool_call(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("type") != "function_call":
        return None
    args_raw = payload.get("arguments") or "{}"
    args = {}
    try:
        args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
    except json.JSONDecodeError:
        args = {"_raw": args_raw}
    return {
        "call_id": payload.get("call_id") or payload.get("id"),
        "tool_name": payload.get("name"),
        "arguments_json": json_dumps(args),
        "command": args.get("command") if isinstance(args, dict) else None,
        "workdir": args.get("workdir") if isinstance(args, dict) else None,
        "timeout_ms": args.get("timeout_ms") if isinstance(args, dict) else None,
        "turn_id": get_turn_id(payload),
    }


def prompt_blocks_for_message(text: str) -> list[tuple[str, str]]:
    """Return labelled large chunks for duplication analysis."""
    blocks: list[tuple[str, str]] = []
    if not text or len(text) < 400:
        return blocks

    # Known Codex/Codex-guardian wrappers.
    patterns = [
        ("AGENTS.md", r"# AGENTS\.md instructions.*?(?=\n(?:The following is|>>> TRANSCRIPT START|\[\d+\] |$))"),
        ("transcript", r">>> TRANSCRIPT START\n.*?(?=\n>>> TRANSCRIPT END|$)"),
        ("permissions", r"<permissions instructions>.*?</permissions instructions>"),
        ("guardian_preamble", r"The following is the Codex agent history.*?(?=>>> TRANSCRIPT START|$)"),
    ]
    for label, pat in patterns:
        for m in re.finditer(pat, text, flags=re.DOTALL):
            chunk = m.group(0).strip()
            if len(chunk) >= 200:
                blocks.append((label, chunk))

    # Generic fallback: hash large message if no known block found.
    if not blocks and len(text) >= 2000:
        blocks.append(("large_message", text.strip()))
    return blocks


@dataclass
class IngestResult:
    files_seen: int = 0
    files_imported: int = 0
    duplicate_files: int = 0
    threads: int = 0
    events: int = 0


class CodexIngestor:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def ingest_paths(self, roots: Iterable[Path]) -> IngestResult:
        result = IngestResult()
        paths: list[Path] = []
        for root in roots:
            root = Path(root).expanduser()
            if root.is_file() and root.suffix == ".jsonl":
                paths.append(root)
            elif root.is_dir():
                paths.extend(root.rglob("*.jsonl"))
        for path in sorted(set(paths)):
            r = self.ingest_file(path)
            result.files_seen += 1
            result.files_imported += r.files_imported
            result.duplicate_files += r.duplicate_files
            result.threads += r.threads
            result.events += r.events
        self.recompute_rollups()
        self.conn.commit()
        return result

    def ingest_file(self, path: Path) -> IngestResult:
        result = IngestResult(files_seen=1)
        path = path.resolve()
        stat = path.stat()
        digest = sha256_file(path)
        existing = self.conn.execute("SELECT path, thread_id FROM files WHERE sha256=?", (digest,)).fetchone()
        if existing and existing["path"] != str(path):
            self.conn.execute(
                "INSERT OR REPLACE INTO files(path,sha256,size_bytes,mtime,imported_at,thread_id,is_duplicate,duplicate_of) VALUES(?,?,?,?,?,?,1,?)",
                (str(path), digest, stat.st_size, stat.st_mtime, utc_now(), existing["thread_id"], existing["path"]),
            )
            result.duplicate_files = 1
            return result

        rows = read_jsonl(path)
        if not rows:
            return result
        meta_obj = next((o for _, o, _ in rows if o.get("type") == "session_meta"), None)
        if not meta_obj:
            return result
        meta = meta_obj.get("payload") or {}
        thread_id = meta.get("id") or path.stem
        session_id = meta.get("session_id") or thread_id
        parent_thread_id = meta.get("parent_thread_id")
        role, nick = extract_agent(meta)
        skind = source_kind(meta.get("source"))
        base_inst = meta.get("base_instructions") or {}
        base_text = base_inst.get("text") if isinstance(base_inst, dict) else None
        timestamps = [o.get("timestamp") for _, o, _ in rows if o.get("timestamp")]
        first_seen = min(timestamps) if timestamps else meta.get("timestamp")
        last_seen = max(timestamps) if timestamps else meta.get("timestamp")
        turn_ids = set()
        tool_count = 0

        self.conn.execute(
            """INSERT OR REPLACE INTO threads(
                thread_id,session_id,parent_thread_id,file_path,thread_source,source_kind,agent_role,agent_nickname,cwd,cli_version,model_provider,base_instruction_chars,created_at,first_seen,last_seen,event_count
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                thread_id, session_id, parent_thread_id, str(path), meta.get("thread_source"), skind, role, nick,
                meta.get("cwd"), meta.get("cli_version"), meta.get("model_provider"), len(base_text or ""), meta.get("timestamp"),
                first_seen, last_seen, len(rows)
            ),
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO files(path,sha256,size_bytes,mtime,imported_at,thread_id,is_duplicate,duplicate_of) VALUES(?,?,?,?,?,?,0,NULL)",
            (str(path), digest, stat.st_size, stat.st_mtime, utc_now(), thread_id),
        )

        # Clear previous event-derived rows for this thread before reimporting.
        for table in ["events", "usage_snapshots", "tool_calls", "messages", "prompt_blocks"]:
            self.conn.execute(f"DELETE FROM {table} WHERE thread_id=?", (thread_id,))

        pending_calls: dict[str, dict[str, Any]] = {}
        for idx, obj, raw in rows:
            typ = obj.get("type")
            payload = obj.get("payload") or {}
            ptype = payload.get("type") if isinstance(payload, dict) else None
            ts = obj.get("timestamp")
            turn_id = get_turn_id(payload) if isinstance(payload, dict) else None
            if turn_id:
                turn_ids.add(turn_id)
            event_pk = stable_event_pk(thread_id, idx, raw)
            self.conn.execute(
                "INSERT OR REPLACE INTO events(event_pk,thread_id,idx,timestamp,type,payload_type,turn_id,payload_json) VALUES(?,?,?,?,?,?,?,?)",
                (event_pk, thread_id, idx, ts, typ, ptype, turn_id, json_dumps(payload)),
            )

            if isinstance(payload, dict):
                usage = usage_from_payload(payload)
                if usage:
                    self.conn.execute(
                        """INSERT OR REPLACE INTO usage_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (event_pk, thread_id, idx, ts, turn_id, usage["input_tokens"], usage["cached_input_tokens"], usage["uncached_input_tokens"], usage["output_tokens"], usage["reasoning_tokens"], usage["total_tokens"], usage["last_input_tokens"], usage["last_cached_input_tokens"], usage["last_uncached_input_tokens"], usage["last_output_tokens"], usage["last_reasoning_tokens"], usage["last_total_tokens"], usage["model_context_window"]),
                    )

                role_msg, text = extract_message_text(payload)
                if text:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO messages(event_pk,thread_id,timestamp,turn_id,role,source,text,char_count,approx_tokens) VALUES(?,?,?,?,?,?,?,?,?)",
                        (event_pk, thread_id, ts, turn_id, role_msg, ptype or typ, text, len(text), approx_tokens(text)),
                    )
                    for label, chunk in prompt_blocks_for_message(text):
                        normalized = re.sub(r"\s+", " ", chunk).strip()
                        bh = hashlib.sha256(normalized.encode("utf-8", "replace")).hexdigest()
                        self.conn.execute(
                            "INSERT OR REPLACE INTO prompt_blocks(block_hash,thread_id,event_pk,timestamp,label,char_count,approx_tokens,preview) VALUES(?,?,?,?,?,?,?,?)",
                            (bh, thread_id, event_pk, ts, label, len(chunk), approx_tokens(chunk), chunk[:300].replace("\n", " ")),
                        )

                call = parse_tool_call(payload)
                if call and call.get("call_id"):
                    tool_count += 1
                    pending_calls[call["call_id"]] = call
                    self.conn.execute(
                        """INSERT OR REPLACE INTO tool_calls(call_id,thread_id,turn_id,timestamp,tool_name,arguments_json,command,workdir,timeout_ms,output,success,duration_ms,output_chars) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (call["call_id"], thread_id, call.get("turn_id"), ts, sqlite_scalar(call.get("tool_name")), sqlite_scalar(call.get("arguments_json")), sqlite_scalar(call.get("command")), sqlite_scalar(call.get("workdir")), sqlite_scalar(call.get("timeout_ms")), None, None, None, None),
                    )
                elif payload.get("type") == "function_call_output":
                    cid = payload.get("call_id")
                    out = payload.get("output") or ""
                    out_text = sqlite_scalar(out)
                    self.conn.execute(
                        "UPDATE tool_calls SET output=?, output_chars=? WHERE call_id=? AND thread_id=?",
                        (out_text, len(str(out_text or "")), cid, thread_id),
                    )
                elif payload.get("type") == "patch_apply_end":
                    cid = payload.get("call_id")
                    out = (payload.get("stdout") or "") + (payload.get("stderr") or "")
                    out_text = sqlite_scalar(out)
                    self.conn.execute(
                        "UPDATE tool_calls SET output=?, output_chars=?, success=? WHERE call_id=? AND thread_id=?",
                        (out_text, len(str(out_text or "")), 1 if payload.get("success") else 0, cid, thread_id),
                    )

        self.conn.execute("UPDATE threads SET turn_count=?, tool_call_count=? WHERE thread_id=?", (len(turn_ids), tool_count, thread_id))
        self._update_thread_final_usage(thread_id)
        result.files_imported = 1
        result.threads = 1
        result.events = len(rows)
        return result

    def _update_thread_final_usage(self, thread_id: str) -> None:
        row = self.conn.execute(
            "SELECT * FROM usage_snapshots WHERE thread_id=? ORDER BY idx DESC LIMIT 1", (thread_id,)
        ).fetchone()
        if not row:
            return
        self.conn.execute(
            """UPDATE threads SET final_input_tokens=?, final_cached_input_tokens=?, final_uncached_input_tokens=?, final_output_tokens=?, final_reasoning_tokens=?, final_total_tokens=? WHERE thread_id=?""",
            (row["input_tokens"], row["cached_input_tokens"], row["uncached_input_tokens"], row["output_tokens"], row["reasoning_tokens"], row["total_tokens"], thread_id),
        )

    def recompute_rollups(self) -> None:
        self.conn.execute("DELETE FROM conversations")
        self.conn.execute(
            """INSERT INTO conversations(session_id,first_seen,last_seen,cwd,thread_count,total_input_tokens,total_cached_input_tokens,total_uncached_input_tokens,total_output_tokens,total_reasoning_tokens,total_tokens)
            SELECT session_id, MIN(first_seen), MAX(last_seen), MIN(cwd), COUNT(*),
                   SUM(final_input_tokens), SUM(final_cached_input_tokens), SUM(final_uncached_input_tokens),
                   SUM(final_output_tokens), SUM(final_reasoning_tokens), SUM(final_total_tokens)
            FROM threads GROUP BY session_id"""
        )


def ingest(sessions_path: str, db_path: str) -> IngestResult:
    ing = CodexIngestor(Path(db_path).expanduser())
    try:
        return ing.ingest_paths([Path(sessions_path).expanduser()])
    finally:
        ing.close()
