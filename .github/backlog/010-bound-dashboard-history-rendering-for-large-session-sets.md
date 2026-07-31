# Bound dashboard history rendering for large session sets

Labels: `enhancement`, `dashboard`

## What to build

Render a bounded page of matching sidebar conversations with compact range navigation so large local histories stay responsive without weakening Find session, Risk, or Focus discovery.

## Acceptance criteria

- [ ] The sidebar renders at most 50 conversation buttons per page and shows the current matching range and total.
- [ ] Previous and next controls move through stable pages, expose correct disabled states, and preserve the selected main report even when its conversation is not on the displayed history page.
- [ ] Changing Find session, Risk, or Focus resets the history page and keeps the selected session valid within the filtered scope.
- [ ] Selecting a conversation keeps it visible on its page; filter restoration returns to a valid page without losing the selected main report.
- [ ] Visual evidence records bounded rendering and page-state behavior at desktop and narrow widths for synthetic and ignored real-profile data.

## Tests and evidence

- [ ] `pytest -q tests/test_dashboard_helpers.py tests/test_visual_qa.py`
- [ ] `python scripts/visual_qa.py`

## Visual QA

Exercise the history range controls, selection validity, and restored page state at desktop and narrow widths; rerun the ignored real-profile browser pass against the approved local session database.

## Privacy review

Use aggregate matching and rendered counts only. Do not publish private session IDs, labels, paths, prompts, screenshots, or real-history counts.

## Blocked by

None
