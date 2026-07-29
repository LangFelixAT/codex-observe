# Tracking Snapshot

This file records the current issue-tracking state and the expected workflow for new work.

## Current GitHub issue state

Checked: 2026-07-29 with:

```powershell
gh issue list --limit 20 --state all --json number,title,state,labels,updatedAt,url
```

All current GitHub issues are closed:

| Issue | State | Title |
| --- | --- | --- |
| #14 | Closed | Order dashboard comparisons chronologically |
| #13 | Closed | Put next-run action and navigation before dashboard metrics |
| #12 | Closed | Make the default tour a concise user journey |
| #11 | Closed | Put the product answer first across start and resume flows |
| #10 | Closed | Align dashboard guidance scopes and recommendation source |
| #8 | Closed | Document supported log shapes and local validation workflow |
| #7 | Closed | Browser-verify the Streamlit dashboard against real data |
| #6 | Closed | Add dashboard helper tests for classification and derived metrics |
| #5 | Closed | Harden tool-call normalization across supported Codex payload shapes |
| #4 | Closed | Make duplicate and reimport behavior explicit and tested |
| #3 | Closed | Add representative JSONL ingestion regression coverage |
| #2 | Closed | Fix Streamlit host and port CLI flags |
| #1 | Closed | Track Codex Observe hardening pass |

There is no `.github/backlog` directory and no current publishable local issue draft.

## New work workflow

Use GitHub issues for new work only when the work is fresh, demoable, and not merely a human-input reminder.

1. Start from `docs/CURRENT.md`, `docs/NEXT_WAVE.md`, `docs/LIMITATIONS.md`, and `docs/PUBLIC_TOUR_FEEDBACK.md`.
2. Capture privacy-safe observations with `.github/ISSUE_TEMPLATE/public_tour_feedback.yml` before converting feedback into implementation work.
3. If a local draft is useful, scaffold it with `python scripts/backlog_publish_plan.py --new-draft "Short demoable title" --label "type: slice" --label "area: dashboard"` so it starts with acceptance criteria, tests, visual QA expectations, privacy review notes, and blocked-by notes.
4. Run `python scripts/backlog_publish_plan.py --json` to validate draft metadata and preview the approval-gated `gh issue create` command.
5. Publish with `gh issue create` only after explicit human approval for the external write.
6. Commit and push the implementation branch after a passing quality gate so the work remains traceable.

Completed local drafts should stay retired and must not be republished as stale issues.
