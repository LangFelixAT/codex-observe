from __future__ import annotations

import datetime as dt
import hashlib
import json
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
    return hashlib.sha256(
        f"{thread_id}:{idx}:".encode() + raw.encode("utf-8", "replace")
    ).hexdigest()


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
            spawn = (
                sub.get("thread_spawn")
                if isinstance(sub.get("thread_spawn"), dict)
                else {}
            )
            role = (
                spawn.get("agent_role")
                or sub.get("agent_role")
                or sub.get("role")
                or sub.get("other")
            )
            nick = (
                spawn.get("agent_nickname")
                or sub.get("agent_nickname")
                or sub.get("nickname")
            )
    return role, nick or ""


@dataclass
class JsonlReadResult:
    rows: list[tuple[int, dict[str, Any], str]]
    blank_lines: int = 0
    malformed_lines: int = 0


def read_jsonl(path: Path) -> JsonlReadResult:
    rows = []
    blank_lines = 0
    malformed_lines = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, raw in enumerate(f):
            raw = raw.rstrip("\n")
            if idx == 0:
                raw = raw.lstrip("\ufeff")
            if not raw.strip():
                blank_lines += 1
                continue
            try:
                rows.append((idx, json.loads(raw), raw))
            except json.JSONDecodeError:
                # Keep going; schema drift / partial writes should not kill ingestion.
                malformed_lines += 1
                continue
    return JsonlReadResult(
        rows=rows, blank_lines=blank_lines, malformed_lines=malformed_lines
    )


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
        return ("user" if pt == "user_message" else "assistant"), payload.get(
            "message"
        ) or ""
    return None, ""


def usage_from_payload(payload: dict[str, Any]) -> dict[str, int] | None:
    if payload.get("type") != "token_count":
        return None
    info = payload.get("info") or {}
    total = (
        info.get("total_token_usage")
        or payload.get("total_token_usage")
        or info.get("usage")
        or payload.get("usage")
        or {}
    )
    last = info.get("last_token_usage") or payload.get("last_token_usage") or {}

    def g(d: dict[str, Any], key: str, *aliases: str) -> int:
        for candidate in (key, *aliases):
            if candidate in d:
                try:
                    return int(d.get(candidate) or 0)
                except (TypeError, ValueError):
                    return 0
        return 0

    def nested_g(
        d: dict[str, Any], container: str, key: str, *container_aliases: str
    ) -> int:
        for name in (container, *container_aliases):
            nested = d.get(name)
            if isinstance(nested, dict):
                return g(nested, key)
        return 0

    def cached(d: dict[str, Any]) -> int:
        return g(d, "cached_input_tokens") or nested_g(
            d, "input_token_details", "cached_tokens", "input_tokens_details"
        )

    def reasoning(d: dict[str, Any]) -> int:
        return g(d, "reasoning_output_tokens", "reasoning_tokens") or nested_g(
            d, "output_token_details", "reasoning_tokens", "output_tokens_details"
        )

    total_input = g(total, "input_tokens")
    total_cached = cached(total)
    total_output = g(total, "output_tokens")
    total_reasoning = reasoning(total)
    total_tokens = (
        g(total, "total_tokens") or total_input + total_output + total_reasoning
    )

    last_input = g(last, "input_tokens")
    last_cached = cached(last)
    last_output = g(last, "output_tokens")
    last_reasoning = reasoning(last)
    last_total = g(last, "total_tokens") or last_input + last_output + last_reasoning

    return {
        "input_tokens": total_input,
        "cached_input_tokens": total_cached,
        "uncached_input_tokens": max(0, total_input - total_cached),
        "output_tokens": total_output,
        "reasoning_tokens": total_reasoning,
        "total_tokens": total_tokens,
        "last_input_tokens": last_input,
        "last_cached_input_tokens": last_cached,
        "last_uncached_input_tokens": max(0, last_input - last_cached),
        "last_output_tokens": last_output,
        "last_reasoning_tokens": last_reasoning,
        "last_total_tokens": last_total,
        "model_context_window": int(
            info.get("model_context_window") or payload.get("model_context_window") or 0
        ),
    }


def parse_tool_call(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize the several tool-call shapes Codex emits into one row."""
    ptype = payload.get("type")

    if ptype == "function_call":
        args_raw = payload.get("arguments") or "{}"
        args = {}
        try:
            args = (
                json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
            )
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

    if ptype == "custom_tool_call":
        name = payload.get("name") or payload.get("tool_name") or "custom_tool"
        inp = (
            payload.get("input")
            or payload.get("arguments")
            or payload.get("content")
            or ""
        )
        args = {"input": inp}
        return {
            "call_id": payload.get("call_id") or payload.get("id"),
            "tool_name": name,
            "arguments_json": json_dumps(args),
            "command": inp if isinstance(inp, str) else None,
            "workdir": None,
            "timeout_ms": None,
            "turn_id": get_turn_id(payload),
        }

    if ptype == "tool_search_call":
        args = {
            k: payload.get(k) for k in ["query", "queries", "pattern"] if k in payload
        }
        return {
            "call_id": payload.get("call_id") or payload.get("id"),
            "tool_name": payload.get("name") or "tool_search",
            "arguments_json": json_dumps(args),
            "command": args.get("query") or args.get("pattern"),
            "workdir": None,
            "timeout_ms": None,
            "turn_id": get_turn_id(payload),
        }

    return None


def prompt_blocks_for_message(text: str) -> list[tuple[str, str]]:
    """Return labelled large chunks for duplication analysis."""
    blocks: list[tuple[str, str]] = []
    if not text or len(text) < 400:
        return blocks

    # Known Codex/Codex-guardian wrappers.
    patterns = [
        (
            "AGENTS.md",
            r"# AGENTS\.md instructions.*?(?=\n(?:The following is|>>> TRANSCRIPT START|\[\d+\] |$))",
        ),
        ("transcript", r">>> TRANSCRIPT START\n.*?(?=\n>>> TRANSCRIPT END|$)"),
        ("permissions", r"<permissions instructions>.*?</permissions instructions>"),
        (
            "guardian_preamble",
            r"The following is the Codex agent history.*?(?=>>> TRANSCRIPT START|$)",
        ),
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
    files_matched: int = 0
    files_skipped_by_limit: int = 0
    newest_files_limit: int | None = None
    files_seen: int = 0
    files_imported: int = 0
    duplicate_files: int = 0
    empty_files: int = 0
    malformed_files: int = 0
    malformed_lines: int = 0
    missing_meta_files: int = 0
    unreadable_files: int = 0
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

    def ingest_paths(
        self, roots: Iterable[Path], newest_files: int | None = None
    ) -> IngestResult:
        result = IngestResult(newest_files_limit=newest_files)
        paths: list[Path] = []
        for root in roots:
            root = Path(root).expanduser()
            if root.is_file() and root.suffix == ".jsonl":
                paths.append(root)
            elif root.is_dir():
                paths.extend(root.rglob("*.jsonl"))
        selected_paths = sorted(set(paths))
        result.files_matched = len(selected_paths)
        if newest_files is not None:
            limit = max(1, int(newest_files))
            selected_paths = sorted(
                selected_paths, key=lambda path: (_path_mtime_sort_key(path), str(path))
            )[:limit]
            result.files_skipped_by_limit = max(
                0, result.files_matched - len(selected_paths)
            )
        for path in selected_paths:
            try:
                r = self.ingest_file(path)
            except OSError:
                result.files_seen += 1
                result.unreadable_files += 1
                continue
            result.files_seen += 1
            result.files_imported += r.files_imported
            result.duplicate_files += r.duplicate_files
            result.empty_files += r.empty_files
            result.malformed_files += r.malformed_files
            result.malformed_lines += r.malformed_lines
            result.missing_meta_files += r.missing_meta_files
            result.unreadable_files += r.unreadable_files
            result.threads += r.threads
            result.events += r.events
        self.recompute_rollups()
        self._record_ingest_run(result)
        self.conn.commit()
        return result

    def _record_ingest_run(self, result: IngestResult) -> None:
        self.conn.execute(
            """INSERT INTO ingest_runs(
                imported_at,scan_mode,newest_files,files_matched,files_seen,files_imported,files_skipped_by_limit,
                duplicate_files,empty_files,malformed_files,malformed_lines,missing_meta_files,unreadable_files,threads,events
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                utc_now(),
                "newest_files" if result.newest_files_limit is not None else "all",
                result.newest_files_limit,
                result.files_matched,
                result.files_seen,
                result.files_imported,
                result.files_skipped_by_limit,
                result.duplicate_files,
                result.empty_files,
                result.malformed_files,
                result.malformed_lines,
                result.missing_meta_files,
                result.unreadable_files,
                result.threads,
                result.events,
            ),
        )

    def _delete_thread_rows(self, thread_id: str) -> None:
        for table in [
            "events",
            "usage_snapshots",
            "tool_calls",
            "messages",
            "prompt_blocks",
        ]:
            self.conn.execute(f"DELETE FROM {table} WHERE thread_id=?", (thread_id,))
        self.conn.execute("DELETE FROM threads WHERE thread_id=?", (thread_id,))

    def ingest_file(self, path: Path) -> IngestResult:
        result = IngestResult(files_seen=1)
        path = path.resolve()
        path_key = str(path)
        stat = path.stat()
        digest = sha256_file(path)
        path_row = self.conn.execute(
            "SELECT path, sha256, thread_id, is_duplicate, duplicate_of FROM files WHERE path=?",
            (path_key,),
        ).fetchone()
        canonical = self.conn.execute(
            "SELECT path, thread_id FROM files WHERE sha256=? AND path<>? AND is_duplicate=0 ORDER BY path LIMIT 1",
            (digest, path_key),
        ).fetchone()
        if canonical:
            if (
                path_row
                and path_row["thread_id"]
                and path_row["thread_id"] != canonical["thread_id"]
            ):
                self._delete_thread_rows(path_row["thread_id"])
            self.conn.execute(
                "INSERT OR REPLACE INTO files(path,sha256,size_bytes,mtime,imported_at,thread_id,is_duplicate,duplicate_of) VALUES(?,?,?,?,?,?,1,?)",
                (
                    path_key,
                    digest,
                    stat.st_size,
                    stat.st_mtime,
                    utc_now(),
                    canonical["thread_id"],
                    canonical["path"],
                ),
            )
            result.duplicate_files = 1
            return result
        if path_row and path_row["is_duplicate"] and path_row["sha256"] == digest:
            self.conn.execute(
                "UPDATE files SET size_bytes=?, mtime=?, imported_at=? WHERE path=?",
                (stat.st_size, stat.st_mtime, utc_now(), path_key),
            )
            result.duplicate_files = 1
            return result

        read_result = read_jsonl(path)
        rows = read_result.rows
        result.malformed_lines = read_result.malformed_lines
        if read_result.malformed_lines:
            result.malformed_files = 1
        if not rows:
            if not read_result.malformed_lines:
                result.empty_files = 1
            return result
        meta_obj = next(
            (o for _, o, _ in rows if o.get("type") == "session_meta"), None
        )
        if not meta_obj:
            result.missing_meta_files = 1
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

        if path_row and path_row["thread_id"] and path_row["thread_id"] != thread_id:
            self._delete_thread_rows(path_row["thread_id"])

        self.conn.execute(
            """INSERT OR REPLACE INTO threads(
                thread_id,session_id,parent_thread_id,file_path,thread_source,source_kind,agent_role,agent_nickname,cwd,cli_version,model_provider,base_instruction_chars,created_at,first_seen,last_seen,event_count
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                thread_id,
                session_id,
                parent_thread_id,
                str(path),
                meta.get("thread_source"),
                skind,
                role,
                nick,
                meta.get("cwd"),
                meta.get("cli_version"),
                meta.get("model_provider"),
                len(base_text or ""),
                meta.get("timestamp"),
                first_seen,
                last_seen,
                len(rows),
            ),
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO files(path,sha256,size_bytes,mtime,imported_at,thread_id,is_duplicate,duplicate_of) VALUES(?,?,?,?,?,?,0,NULL)",
            (str(path), digest, stat.st_size, stat.st_mtime, utc_now(), thread_id),
        )

        # Clear previous event-derived rows for this thread before reimporting.
        for table in [
            "events",
            "usage_snapshots",
            "tool_calls",
            "messages",
            "prompt_blocks",
        ]:
            self.conn.execute(f"DELETE FROM {table} WHERE thread_id=?", (thread_id,))

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
                (
                    event_pk,
                    thread_id,
                    idx,
                    ts,
                    typ,
                    ptype,
                    turn_id,
                    json_dumps(payload),
                ),
            )

            if isinstance(payload, dict):
                usage = usage_from_payload(payload)
                if usage:
                    self.conn.execute(
                        """INSERT OR REPLACE INTO usage_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            event_pk,
                            thread_id,
                            idx,
                            ts,
                            turn_id,
                            usage["input_tokens"],
                            usage["cached_input_tokens"],
                            usage["uncached_input_tokens"],
                            usage["output_tokens"],
                            usage["reasoning_tokens"],
                            usage["total_tokens"],
                            usage["last_input_tokens"],
                            usage["last_cached_input_tokens"],
                            usage["last_uncached_input_tokens"],
                            usage["last_output_tokens"],
                            usage["last_reasoning_tokens"],
                            usage["last_total_tokens"],
                            usage["model_context_window"],
                        ),
                    )

                role_msg, text = extract_message_text(payload)
                if text:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO messages(event_pk,thread_id,timestamp,turn_id,role,source,text,char_count,approx_tokens) VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            event_pk,
                            thread_id,
                            ts,
                            turn_id,
                            role_msg,
                            ptype or typ,
                            text,
                            len(text),
                            approx_tokens(text),
                        ),
                    )
                    for label, chunk in prompt_blocks_for_message(text):
                        normalized = re.sub(r"\s+", " ", chunk).strip()
                        bh = hashlib.sha256(
                            normalized.encode("utf-8", "replace")
                        ).hexdigest()
                        self.conn.execute(
                            "INSERT OR REPLACE INTO prompt_blocks(block_hash,thread_id,event_pk,timestamp,label,char_count,approx_tokens,preview) VALUES(?,?,?,?,?,?,?,?)",
                            (
                                bh,
                                thread_id,
                                event_pk,
                                ts,
                                label,
                                len(chunk),
                                approx_tokens(chunk),
                                chunk[:300].replace("\n", " "),
                            ),
                        )

                call = parse_tool_call(payload)
                if call and call.get("call_id"):
                    tool_count += 1
                    self.conn.execute(
                        """INSERT OR REPLACE INTO tool_calls(call_id,thread_id,turn_id,timestamp,tool_name,arguments_json,command,workdir,timeout_ms,output,success,duration_ms,output_chars) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            call["call_id"],
                            thread_id,
                            call.get("turn_id"),
                            ts,
                            sqlite_scalar(call.get("tool_name")),
                            sqlite_scalar(call.get("arguments_json")),
                            sqlite_scalar(call.get("command")),
                            sqlite_scalar(call.get("workdir")),
                            sqlite_scalar(call.get("timeout_ms")),
                            None,
                            None,
                            None,
                            None,
                        ),
                    )
                elif payload.get("type") in {
                    "function_call_output",
                    "custom_tool_call_output",
                    "tool_search_output",
                }:
                    cid = payload.get("call_id") or payload.get("id")
                    out = ""
                    for key in ("output", "content", "result"):
                        if key in payload:
                            out = payload[key]
                            break
                    out_text = sqlite_scalar(out)
                    self.conn.execute(
                        "UPDATE tool_calls SET output=?, output_chars=? WHERE call_id=? AND thread_id=?",
                        (
                            out_text,
                            len(str(out_text if out_text is not None else "")),
                            cid,
                            thread_id,
                        ),
                    )
                elif payload.get("type") == "patch_apply_end":
                    cid = payload.get("call_id")
                    out = (payload.get("stdout") or "") + (payload.get("stderr") or "")
                    out_text = sqlite_scalar(out)
                    self.conn.execute(
                        "UPDATE tool_calls SET output=?, output_chars=?, success=? WHERE call_id=? AND thread_id=?",
                        (
                            out_text,
                            len(str(out_text if out_text is not None else "")),
                            1 if payload.get("success") else 0,
                            cid,
                            thread_id,
                        ),
                    )

        self.conn.execute(
            "UPDATE threads SET turn_count=?, tool_call_count=? WHERE thread_id=?",
            (len(turn_ids), tool_count, thread_id),
        )
        self._update_thread_final_usage(thread_id)
        result.files_imported = 1
        result.threads = 1
        result.events = len(rows)
        return result

    def _update_thread_final_usage(self, thread_id: str) -> None:
        row = self.conn.execute(
            "SELECT * FROM usage_snapshots WHERE thread_id=? ORDER BY idx DESC LIMIT 1",
            (thread_id,),
        ).fetchone()
        if not row:
            return
        self.conn.execute(
            """UPDATE threads SET final_input_tokens=?, final_cached_input_tokens=?, final_uncached_input_tokens=?, final_output_tokens=?, final_reasoning_tokens=?, final_total_tokens=? WHERE thread_id=?""",
            (
                row["input_tokens"],
                row["cached_input_tokens"],
                row["uncached_input_tokens"],
                row["output_tokens"],
                row["reasoning_tokens"],
                row["total_tokens"],
                thread_id,
            ),
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


def _path_mtime_sort_key(path: Path) -> float:
    try:
        return -path.stat().st_mtime
    except OSError:
        return float("inf")


def ingest(
    sessions_path: str, db_path: str, newest_files: int | None = None
) -> IngestResult:
    ing = CodexIngestor(Path(db_path).expanduser())
    try:
        return ing.ingest_paths([Path(sessions_path).expanduser()], newest_files)
    finally:
        ing.close()
