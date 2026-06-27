# Codex Observe

Offline observability dashboard for Codex `.jsonl` session logs.

## Install locally

```bash
cd codex-observe
python -m pip install -e .
```

## Run

Ingest sessions and open the dashboard:

```bash
codex-observe scan-and-serve ~/.codex/sessions
```

On Windows CMD:

```bat
codex-observe scan-and-serve "%USERPROFILE%\.codex\sessions"
```

The default database is stored at:

```text
~/.codex-observe/codex_observe.sqlite
```

To serve an existing database without scanning first:

```bash
codex-observe serve --db ~/.codex-observe/codex_observe.sqlite
```

`serve` and `scan-and-serve` accept `--host` and `--port`. These are passed to Streamlit before the dashboard app arguments:

```bash
codex-observe serve --db ./codex_observe.sqlite --host 127.0.0.1 --port 9999
codex-observe scan-and-serve ~/.codex/sessions --db ./codex_observe.sqlite --host 127.0.0.1 --port 9999
```

## Supported log shapes

The parser is defensive because Codex JSONL payloads are not guaranteed stable. The currently supported shapes are:

- `session_meta` rows with thread/session metadata, including root sessions and spawned subagent threads.
- Message payloads with `type=message` plus `role` and `content`, and legacy `user_message` / `agent_message` payloads.
- `token_count` payloads with `total_token_usage`, `last_token_usage`, and `model_context_window`.
- Tool calls: `function_call`, `custom_tool_call`, and `tool_search_call`.
- Tool outputs: `function_call_output`, `custom_tool_call_output`, `tool_search_output`, and `patch_apply_end`.
- Compaction markers from top-level `compacted` events and `context_compacted` payloads.
- Large prompt blocks extracted from message text for duplication analysis.

Unknown and unsupported payloads are still retained in `events.payload_json` so raw source data remains inspectable after ingestion.

## Derived values

Authoritative token totals come from Codex `token_count` events. Conversation and thread rollups use the final token snapshot for each thread.

Approximate token values are only text-size estimates used for message snippets and repeated prompt block analysis. They are not authoritative billing or model-usage counts.

Re-importing the same file path refreshes the event-derived rows for that thread. Importing identical content from a different path records a duplicate file row and points it at the canonical imported path.

## What it shows

- conversation list grouped by day
- root / worker / explorer / guardian labeling
- token attribution by thread and role
- cache-adjusted token totals
- worker/thread detail view
- likely worker launch prompt / goal reconstruction
- context compaction events
- largest token jumps
- tool distribution and largest tool outputs
- guardian overhead
- prompt duplication breakdown
- raw tables for inspection

## Validate locally

Run the regression suite:

```bash
pytest -q
```

For UI-facing dashboard changes, browser-verify Streamlit against a database that contains at least one conversation, multiple threads, usage snapshots, tool calls, and prompt blocks. Click through these tabs at desktop and narrow/mobile widths and confirm there is no visible Streamlit exception: Overview, Agent detail, Timeline & jumps, Tools, Duplication, and Raw tables. Exercise the Agent detail thread selector during the check. Record the local URL, tested database source, viewport sizes, and screenshot filenames or equivalent visual evidence in the PR or issue.

