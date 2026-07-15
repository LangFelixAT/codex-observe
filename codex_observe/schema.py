from __future__ import annotations

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS files (
  path TEXT PRIMARY KEY,
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  mtime REAL NOT NULL,
  imported_at TEXT NOT NULL,
  thread_id TEXT,
  is_duplicate INTEGER DEFAULT 0,
  duplicate_of TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
  session_id TEXT PRIMARY KEY,
  first_seen TEXT,
  last_seen TEXT,
  cwd TEXT,
  thread_count INTEGER DEFAULT 0,
  total_input_tokens INTEGER DEFAULT 0,
  total_cached_input_tokens INTEGER DEFAULT 0,
  total_uncached_input_tokens INTEGER DEFAULT 0,
  total_output_tokens INTEGER DEFAULT 0,
  total_reasoning_tokens INTEGER DEFAULT 0,
  total_tokens INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS threads (
  thread_id TEXT PRIMARY KEY,
  session_id TEXT,
  parent_thread_id TEXT,
  file_path TEXT,
  thread_source TEXT,
  source_kind TEXT,
  agent_role TEXT,
  agent_nickname TEXT,
  cwd TEXT,
  cli_version TEXT,
  model_provider TEXT,
  base_instruction_chars INTEGER DEFAULT 0,
  created_at TEXT,
  first_seen TEXT,
  last_seen TEXT,
  event_count INTEGER DEFAULT 0,
  turn_count INTEGER DEFAULT 0,
  tool_call_count INTEGER DEFAULT 0,
  final_input_tokens INTEGER DEFAULT 0,
  final_cached_input_tokens INTEGER DEFAULT 0,
  final_uncached_input_tokens INTEGER DEFAULT 0,
  final_output_tokens INTEGER DEFAULT 0,
  final_reasoning_tokens INTEGER DEFAULT 0,
  final_total_tokens INTEGER DEFAULT 0,
  FOREIGN KEY(session_id) REFERENCES conversations(session_id)
);

CREATE TABLE IF NOT EXISTS events (
  event_pk TEXT PRIMARY KEY,
  thread_id TEXT,
  idx INTEGER,
  timestamp TEXT,
  type TEXT,
  payload_type TEXT,
  turn_id TEXT,
  payload_json TEXT
);

CREATE TABLE IF NOT EXISTS usage_snapshots (
  event_pk TEXT PRIMARY KEY,
  thread_id TEXT,
  idx INTEGER,
  timestamp TEXT,
  turn_id TEXT,
  input_tokens INTEGER,
  cached_input_tokens INTEGER,
  uncached_input_tokens INTEGER,
  output_tokens INTEGER,
  reasoning_tokens INTEGER,
  total_tokens INTEGER,
  last_input_tokens INTEGER,
  last_cached_input_tokens INTEGER,
  last_uncached_input_tokens INTEGER,
  last_output_tokens INTEGER,
  last_reasoning_tokens INTEGER,
  last_total_tokens INTEGER,
  model_context_window INTEGER
);

CREATE TABLE IF NOT EXISTS tool_calls (
  call_id TEXT,
  thread_id TEXT,
  turn_id TEXT,
  timestamp TEXT,
  tool_name TEXT,
  arguments_json TEXT,
  command TEXT,
  workdir TEXT,
  timeout_ms INTEGER,
  output TEXT,
  success INTEGER,
  duration_ms INTEGER,
  output_chars INTEGER,
  PRIMARY KEY(call_id, thread_id)
);

CREATE TABLE IF NOT EXISTS messages (
  event_pk TEXT PRIMARY KEY,
  thread_id TEXT,
  timestamp TEXT,
  turn_id TEXT,
  role TEXT,
  source TEXT,
  text TEXT,
  char_count INTEGER,
  approx_tokens INTEGER
);

CREATE TABLE IF NOT EXISTS prompt_blocks (
  block_hash TEXT,
  thread_id TEXT,
  event_pk TEXT,
  timestamp TEXT,
  label TEXT,
  char_count INTEGER,
  approx_tokens INTEGER,
  preview TEXT,
  PRIMARY KEY(block_hash, thread_id, event_pk, label)
);
CREATE TABLE IF NOT EXISTS ingest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  imported_at TEXT NOT NULL,
  scan_mode TEXT NOT NULL,
  newest_files INTEGER,
  files_matched INTEGER DEFAULT 0,
  files_seen INTEGER DEFAULT 0,
  files_imported INTEGER DEFAULT 0,
  files_skipped_by_limit INTEGER DEFAULT 0,
  duplicate_files INTEGER DEFAULT 0,
  empty_files INTEGER DEFAULT 0,
  malformed_files INTEGER DEFAULT 0,
  malformed_lines INTEGER DEFAULT 0,
  missing_meta_files INTEGER DEFAULT 0,
  unreadable_files INTEGER DEFAULT 0,
  threads INTEGER DEFAULT 0,
  events INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_threads_session ON threads(session_id);
CREATE INDEX IF NOT EXISTS idx_threads_parent ON threads(parent_thread_id);
CREATE INDEX IF NOT EXISTS idx_events_thread ON events(thread_id);
CREATE INDEX IF NOT EXISTS idx_usage_thread ON usage_snapshots(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_blocks_hash ON prompt_blocks(block_hash);
"""
