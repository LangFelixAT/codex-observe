# Codex Observe

Offline observability dashboard for Codex `.jsonl` session logs.

## Install locally

```bash
cd codex_observe
python -m pip install -e .
```

## Run

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

## Notes

The JSONL schema is not guaranteed stable, so the parser is defensive and stores unknown payloads as raw JSON in the `events` table. Re-run ingestion after upgrading if you want refreshed derived data.
