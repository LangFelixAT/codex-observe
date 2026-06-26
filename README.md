# Codex Observe

Offline observability for OpenAI Codex `.jsonl` session logs.

This project scans `~/.codex/sessions/**/*.jsonl`, stores a normalized view in SQLite, and serves a Streamlit dashboard for understanding multi-agent/subagent token usage, tool calls, repeated prompt context, cache efficiency, and conversation trees.

## Why this exists

Codex stores session files under a date-based folder structure such as:

```text
~/.codex/sessions/2026/06/26/*.jsonl
```

Those folders are storage buckets, not reliable logical boundaries. A conversation may continue across days, and subagents/guardian checks are separate JSONL files. Codex Observe therefore scans the whole tree and groups records by `session_meta.session_id`.

## Install

From this directory:

```bash
python -m pip install -e .
```

## Quick start

```bash
codex-observe ingest ~/.codex/sessions
codex-observe serve
```

Or ingest and serve in one step:

```bash
codex-observe scan-and-serve ~/.codex/sessions
```

By default the SQLite database is written to:

```text
~/.codex-observe/codex_observe.sqlite
```

Use a custom DB path with:

```bash
codex-observe ingest ~/.codex/sessions --db ./codex_observe.sqlite
codex-observe serve --db ./codex_observe.sqlite
```

## What the dashboard shows

- Conversation tree reconstructed from `session_id`, thread id, and `parent_thread_id`
- Threads/subagents by role, nickname, source type, and parent
- Raw, cached, uncached, output, and reasoning tokens
- Cache efficiency
- Token attribution by agent role/source
- Tool calls, command text, output size, and patch events
- Context growth over time from token snapshots
- Repeated prompt blocks such as AGENTS.md, guardian transcript wrappers, permissions blocks, and large replayed messages
- High-overhead threads, for example huge input with tiny output

## Token accounting model

Do **not** sum every `token_count` event. Many of them are cumulative snapshots.

Codex Observe uses:

- final token snapshot per thread for thread/conversation totals
- per-snapshot timelines for context growth charts
- `last_token_usage` fields for future per-turn analysis

This avoids the most common source of absurd over-counting.

## Data model

Main tables:

- `files` — imported JSONL paths, hashes, duplicate status
- `conversations` — grouped by `session_meta.session_id`
- `threads` — one row per JSONL thread/session file
- `events` — raw normalized event stream
- `usage_snapshots` — parsed token_count events
- `tool_calls` — function calls and outputs
- `messages` — extracted user/assistant/developer text
- `prompt_blocks` — hashed large prompt fragments for duplication analysis

## Multi-day conversations

Always scan the entire sessions tree:

```bash
codex-observe ingest ~/.codex/sessions
```

The importer ignores folder dates when building logical conversations. Dates are still useful for filtering later, but `session_id` is the primary grouping key.

## Duplicate files

The importer dedupes by SHA-256 content hash and stores duplicate paths in the `files` table. If two files have the same content, only the first one is ingested into event tables.

## Limitations

- Codex's JSONL schema is not treated as stable; the parser is intentionally permissive and event-driven.
- Approximate token counts for repeated prompt fragments use `len(text) / 4`. Authoritative totals still come from Codex `token_count` events.
- The dashboard can infer that subagents/guardians were spawned, but not necessarily the hidden scheduler rationale for spawning them.
- Cost calculation is not included yet because model pricing, cache pricing, and plan semantics can change. The schema keeps enough fields to add it later.

## Useful development commands

```bash
python -m codex_observe.cli ingest /path/to/jsonls --db /tmp/codex_observe.sqlite
python -m streamlit run codex_observe/dashboard.py -- --db /tmp/codex_observe.sqlite
```

## Suggested next features

- Pricing configuration and cost estimates
- Per-user-prompt attribution
- Better prompt-block segmentation
- Export to CSV/Parquet
- Live tailing mode
- Optional OpenTelemetry import
