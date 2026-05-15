# Tech Spec: CLI `explain <task-id>` — `T06`

> **SPEC:** [`docs/specs/sprint-composer.md`](../specs/sprint-composer.md)
> **Plan:** [`docs/plans/sprint-composer.md`](../plans/sprint-composer.md) — task `T06`
> **Conventions applied:** `CLAUDE.md` (project) · `rules/testing.md` · `rules/anti-patterns.md`
>
> This document details **how** to deliver T06. The **why** lives in the SPEC; **what** and **in what order**, in the Plan.

---

## Task Scope

- **Behavior delivered:** After a `run` has produced a JSON sibling, the FDE invokes `sprint-composer explain <transcript-path> <task-id>` to audit any segment surfaced in the proposal. The CLI derives the JSON path from the transcript path, looks up the segment by `segment_id`, and prints: the verbatim source excerpt, the Layer-1 classification (type, confidence, reasoning), the Layer-2 enrichment outcome (matched reference or "no match found" with gap questions), and the Layer-3 allocation reasoning (MoSCoW, sprint allocation, dependencies, confidence). Non-task segments (decisions, open questions, noise) show only Layer-1 data. Unknown task IDs produce a named, actionable error. This satisfies demo criterion 4 (auditability).
- **SPEC stories/criteria covered:**
  - Scenario *"Explain an individual task"*
  - Demo criterion 4 (auditability — for any task, source + classification + confidence reasoning)
- **Depends on:** T05 — JSON artifact schema, `segment_id` as stable task key, `_die()` / `_progress()` patterns, test infrastructure
- **External dependencies:** None — reads a JSON file written by T05; stdlib only (`argparse`, `json`, `pathlib`)

---

## Architecture

- **General approach:** T06 extends `cli.py` exclusively — no new files. It wires a new `explain` subcommand into `app()` (the placeholder comment is already there), adds `_cmd_explain(transcript_path, task_id)` for pipeline orchestration, and adds `_format_explain(task_id, task_data, block)` as a pure formatting function. Tests extend `tests/test_cli.py` with new classes.
- **Why no new file:** `_cmd_explain` and `_format_explain` follow the same shape as `_cmd_run` and `_format_proposal` — same error pattern (`_die`), same import scope, same test file. A separate `explain.py` would split tightly coupled code without gaining testability. No speculative abstraction (`rules/anti-patterns.md`).
- **JSON lookup:** Iterate all five block locations (`sprint_tasks`, `out_of_sprint`, `pending_answers.open_questions`, `decisions`, `discard_appendix`) and match on `segment_id`. Return the first match along with its block name. Non-task blocks carry only L1 fields — the formatter handles the conditional.
- **Affected modules:** `src/sprint_composer/cli.py` (only) + `tests/test_cli.py` (only)
- **New files:** None
- **Reused patterns:**
  - `_die(msg)` — exact pattern from `cli.py:_die`
  - `capsys` + `pytest.raises(SystemExit)` — exact pattern from `TestRunErrorHandling`
  - `tmp_path` fixture + JSON artifact written and read — exact pattern from `TestRunHappyPath`

> **Decision source:** CLAUDE.md (no speculative abstractions, reuse over install), `rules/anti-patterns.md`, user confirmation (transcript-path interface + all-segments scope).

---

## Contracts

### CLI interface

```
sprint-composer explain <transcript-path> <task-id>
```

- `<transcript-path>`: path to the transcript file previously passed to `run`
- `<task-id>`: the `segment_id` value printed in the proposal (e.g. `S01`, `S03`)
- The JSON artifact is derived: `Path(transcript_path).with_suffix(".json")`

**Registered in `app()` via `add_subparsers()`:**

```python
explain_parser = subparsers.add_parser("explain", help="Explain a task from the last run")
explain_parser.add_argument("transcript_path", type=Path, help="Path to the transcript file")
explain_parser.add_argument("task_id", help="Segment ID to explain (e.g. S01)")
```

---

### `_cmd_explain(transcript_path: Path, task_id: str) -> None`

```python
def _cmd_explain(transcript_path: Path, task_id: str) -> None:
    """
    Load the JSON sibling of transcript_path and print the explain output for task_id.

    Derives json_path = transcript_path.with_suffix(".json").
    Searches all five JSON blocks for a segment with segment_id == task_id.
    Prints formatted explain output to stdout.

    All user-facing errors print 'Error: <named message>' to stderr and exit 1.
    """
```

**Orchestration sequence:**

1. Derive `json_path = transcript_path.with_suffix(".json")`
2. Check `json_path.exists()` → if missing, `_die(f"No JSON artifact found at '{json_path}'. Run 'sprint-composer run {transcript_path}' first.")`
3. `json_path.read_text()` → wrap `OSError` in `_die(f"Cannot read artifact '{json_path}': {e}")`
4. `json.loads(text)` → wrap `json.JSONDecodeError` in `_die(f"Cannot parse artifact '{json_path}': {e}")`
5. Search blocks in order — first match wins:

   | Block key | Display name |
   |---|---|
   | `artifact["sprint_tasks"]` | `"Proposed sprint tasks"` |
   | `artifact["out_of_sprint"]` | `"Out of sprint"` |
   | `artifact["pending_answers"]["open_questions"]` | `"Pending customer answers"` |
   | `artifact["decisions"]` | `"Recorded decisions"` |
   | `artifact["discard_appendix"]` | `"Discard appendix"` |

6. If no match found → `_die(f"Task '{task_id}' not found in '{json_path}'. Check the proposal output for valid task IDs (e.g. S01, S02).")`
7. `print(_format_explain(task_id, task_data, block_name))`

---

### `_format_explain(task_id: str, task_data: dict[str, Any], block: str) -> str`

```python
def _format_explain(task_id: str, task_data: dict[str, Any], block: str) -> str:
    """
    Format the explain output for a single segment.

    For sprint_tasks and out_of_sprint: includes L1, L2, and L3 sections.
    For other blocks (decisions, open_questions, discard_appendix): includes L1 section only,
    with a note that L2/L3 were not applied.
    """
```

The function is **pure** — no I/O, no side effects. Determines whether the entry is a "task" entry (has `"moscow"` key) or a non-task entry (no `"moscow"` key) and branches accordingly.

---

## Data Model

### Stdout format — `explain` output

#### Task entry (from `sprint_tasks` or `out_of_sprint`)

```
=== Explain: S01 ===
Block: Proposed sprint tasks

Source excerpt:
  "We need to implement Single Sign-On integration with our Active Directory
  to streamline provider access."

Layer 1 — Classification
  Type:       firm_request
  Confidence: HIGH
  Reasoning:  Clear, explicit request for SSO with a named technical system.

Layer 2 — Enrichment
  Reference:  Single Sign-On via LDAP/Active Directory (Retail Loyalty Program Digital Integration)
  Effort:     5 days
  Confidence: HIGH
  Blockers:   Identity provider configuration; Network security group rules
  Reasoning:  Close match found: same technology (LDAP/AD SSO), similar integration scope.

Layer 3 — Allocation
  MoSCoW:     Must
  Sprint:     In sprint
  Confidence: HIGH
  Order:      1
  Reasoning:  SSO is a prerequisite for all authenticated workflows in Simulation.
```

#### Task entry — no reference match

```
=== Explain: S04 ===
Block: Proposed sprint tasks

Source excerpt:
  "The nursing team raised an interesting request during the UAT sessions about
  consolidating the three scheduling systems into one interface."

Layer 1 — Classification
  Type:       latent_request
  Confidence: MEDIUM
  Reasoning:  Latent pain around workflow fragmentation; not an explicit deliverable request.

Layer 2 — Enrichment
  Reference:  no match found
  Effort:     estimate not available
  Confidence: LOW
  Blockers:   (none)
  Questions to unlock estimate:
    • What is the technical scope for consolidating the three systems?
    • Are there vendor APIs or integration guides available for the scheduling system?
    • What are the acceptance criteria for this to be considered complete?
  Reasoning:  No close reference match; estimation requires scoping inputs from customer.

Layer 3 — Allocation
  MoSCoW:     Should
  Sprint:     In sprint
  Confidence: HIGH
  Order:      3
  Needs Lead decision: MoSCoW level uncertain without effort estimate for scoping.
  Reasoning:  Workflow consolidation scope is unclear; needs Lead input on phasing.
```

#### Non-task entry (from `decisions`, `pending_answers.open_questions`, `discard_appendix`)

```
=== Explain: S06 ===
Block: Recorded decisions

Source excerpt:
  "We've made a firm decision: the staging environment will be used for all UAT
  moving forward."

Layer 1 — Classification
  Type:       decision
  Confidence: HIGH
  Reasoning:  Firm scope decision recorded by the team.

(No Layer 2 or Layer 3 — segment was not enriched or allocated)
```

---

### Formatting rules

**Excerpt formatting:** Print the full excerpt verbatim, indented with two spaces, one line per line. No truncation — this is an audit command, not a summary.

**L2 — Reference field:**
- Match found: `"<task_name> (<project_name>)"`
- No match: `"no match found"`

**L2 — Blockers field:**
- Non-empty list: joined with `"; "`
- Empty list: `"(none)"`

**L2 — Gap questions:** Print only when `gap_questions` is non-empty, prefixed with `• `.

**L3 — Sprint field:** `"In sprint"` when `sprint_allocation == "in_sprint"`, `"Out of sprint"` otherwise.

**L3 — Needs Lead decision:** Print only when `needs_lead_decision == True`.

**Non-task detection:** `"moscow"` key present → task entry; absent → non-task entry.

---

## Error Handling Contract

All errors follow the existing `_die()` pattern — named message to stderr, `sys.exit(1)`:

| Condition | Message |
|---|---|
| JSON sibling not found | `"No JSON artifact found at '<json_path>'. Run 'sprint-composer run <transcript_path>' first."` |
| JSON file unreadable (`OSError`) | `"Cannot read artifact '<json_path>': <os error message>"` |
| JSON invalid (`JSONDecodeError`) | `"Cannot parse artifact '<json_path>': <json error message>"` |
| `task_id` not found in any block | `"Task '<task_id>' not found in '<json_path>'. Check the proposal output for valid task IDs (e.g. S01, S02)."` |

---

## Trade-offs and Rejected Alternatives

**Decision: `explain <transcript-path> <task-id>` (not `explain <json-path> <task-id>`)**
- **Rejected:** `explain <json-path> <task-id>` — requires the user to remember two paths (transcript for `run`, JSON for `explain`), where the JSON path is a derived artifact.
- **Reason:** The user already knows the transcript path from the `run` invocation. Deriving JSON via `.with_suffix(".json")` is the same convention T05 uses internally and is documented in the `run` output message. Symmetry reduces cognitive load.

**Decision: all segment types are explainable (not tasks only)**
- **Rejected:** tasks-only — decisions, open questions, and noise all have `segment_id` values printed in the proposal (Blocks 3–5). If `explain S06` fails on a decision the user read in Block 4, the error is confusing and breaks the "auditability" promise.
- **Reason:** SPEC "auditable by default" and "nothing is silently dropped" — both principles imply every surfaced ID should be explainable. Non-task entries simply show L1 data with a clear note.

**Decision: `_format_explain` as a pure function in `cli.py` (not a new module)**
- **Rejected:** separate `explain.py` — the function is one formatting concern that mirrors `_format_proposal`. Splitting into a new file before a second caller exists is a speculative abstraction.
- **Reason:** `rules/anti-patterns.md` — "Three similar lines is better than a premature abstraction."

**Decision: non-task detection via key presence (`"moscow" in task_data`)**
- **Rejected:** explicit block-name check — the block name is a display string, not a stable key; key presence is structural and won't break if display names change.
- **Reason:** Structural check on the data is more robust than string matching on a display label.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| JSON sibling missing (user runs `explain` without prior `run`) | Confusing error | Named error message explicitly tells user to run `sprint-composer run <transcript_path>` first |
| task_id typo (e.g. `s01` instead of `S01`) | "not found" error | Error message includes example valid IDs; segment IDs are uppercase by convention |
| JSON artifact from a different transcript passed | Wrong data displayed silently | `metadata.transcript_path` field is present but not validated in v0 (FDE responsible for pairing args correctly; acceptable scope for demo) |
| Very long excerpts (multi-paragraph segments) | Verbose but correct output | No truncation in `explain` by design — this is an audit command; full verbatim excerpt is the value proposition |
| `pending_answers.open_questions` is nested under `pending_answers` | Lookup misses the block | Lookup explicitly indexes `artifact["pending_answers"]["open_questions"]` |

---

## Testing Plan

All tests in `tests/test_cli.py`. No new test file.

### `TestFormatExplain` — unit (pure, no I/O)

- **Task with reference match:** Output contains `"Layer 1"`, `"Layer 2"`, `"Layer 3"` section headers; reference name present; effort `"5 days"`; no gap questions section
- **Task with no reference match:** `"no match found"` in Layer 2; `"estimate not available"` in Layer 2; gap questions listed with `•` prefix; `"LOW"` in Layer 2 confidence
- **Task with `needs_lead_decision=True`:** `"Needs Lead decision:"` line present in Layer 3 section
- **Non-task entry (decision):** Output contains `"Layer 1"` and `"(No Layer 2 or Layer 3"` note; no `"Layer 2"` header; no `"Layer 3"` header
- **Excerpt is verbatim (not truncated):** A 300-character excerpt appears in full in the output (contrast with `_task_title` truncation in `_format_proposal`)

### `TestCmdExplain` — unit (no Gemini, uses `tmp_path` + `capsys`)

All error tests use `pytest.raises(SystemExit)` and assert `exc.value.code == 1` and `"Error:" in captured.err`.

- **JSON not found:** `tmp_path / "transcript.txt"` exists, no `.json` sibling → exit 1, `"No JSON artifact found"` in stderr
- **JSON invalid (malformed):** JSON sibling exists but contains `"not valid json"` → exit 1, `"Cannot parse artifact"` in stderr
- **Unknown task_id:** Valid JSON artifact, task_id `"S99"` → exit 1, `"S99"` and `"not found"` in stderr
- **Happy path — sprint task:** JSON sibling with `sprint_tasks` entry for `"S01"` → stdout contains `"=== Explain: S01 ==="`, `"Layer 1"`, `"Layer 2"`, `"Layer 3"`, exit 0
- **Happy path — decision (non-task):** JSON sibling with `decisions` entry for `"S06"` → stdout contains `"=== Explain: S06 ==="`, `"Layer 1"`, `"(No Layer 2 or Layer 3"`, exit 0

### `TestAppExplainSubcommand` — unit

```python
monkeypatch.setattr(sys, "argv", ["sprint-composer", "explain", "transcript.txt", "S01"])
```

- `explain` subcommand is registered in `app()` and dispatches to `_cmd_explain` — verified by monkeypatching `_cmd_explain` and asserting it is called with correct args

### `TestIntegration` (extends existing class, guarded by `GEMINI_API_KEY`)

- Full pipeline: `run` transcript → `explain S03` (out-of-sprint) → stdout contains `"Out of sprint"`, `"Layer 3"`, and phase-mismatch reasoning (demo criterion 4)
- Full pipeline: `run` transcript → `explain S04` (LOW confidence, no match) → stdout contains `"no match found"`, `"estimate not available"`, `"LOW"` (demo criterion 4 on LOW task)
- `explain` with unknown ID after valid `run` → exit 1

> **Framework/pattern:** pytest `capsys`, `monkeypatch`, `tmp_path` (built-in). JSON artifact is constructed inline as a dict and written to `tmp_path` with `json.dumps` — no need to monkeypatch layers for `_cmd_explain` tests.

---

## Implementation Sequence

Each step is one cohesive commit:

1. **`_format_explain` + `TestFormatExplain`** — pure function, no I/O, all five test cases pass; confirm non-task detection via `"moscow"` key works for both branches
2. **`_cmd_explain` error paths + `TestCmdExplain` error cases** — JSON not found, invalid JSON, unknown task_id; all testable with `tmp_path` + hand-crafted JSON dicts; no Gemini
3. **`_cmd_explain` happy paths + remaining `TestCmdExplain` cases** — sprint task and non-task (decision) lookups pass; stdout format verified
4. **`app()` wiring + `TestAppExplainSubcommand`** — add `explain` subparser to `app()`; dispatch to `_cmd_explain`; verify via monkeypatch
5. **`TestIntegration` explain cases** (guarded by `GEMINI_API_KEY`) — run full pipeline then explain S03 and S04; assert demo criterion 4 output

---

## Conventions Applied (from CLAUDE.md)

- Stack: Python with `uv`; `argparse` stdlib; `json` + `pathlib` stdlib — no new dependencies
- Tests: pytest `capsys`, `monkeypatch`, `tmp_path`; integration test guarded by `@pytest.mark.skipif`
- Naming: `snake_case` functions, `_`-prefixed private; English throughout
- Error pattern: `_die()` for all user-facing errors — named message to stderr, exit 1 (consistent with T05)
- No progress lines in `explain` — operation is instantaneous (JSON read, no pipeline)
- Confidence: always `HIGH | MEDIUM | LOW` word labels (SPEC accessibility requirement)
- No comments explaining *what* — only *why* where non-obvious

---

## Ready to Code?

- [x] Architecture described — no new files; two new functions in `cli.py`; tests in `tests/test_cli.py`
- [x] CLI interface finalized: `explain <transcript-path> <task-id>`; JSON derived via `.with_suffix(".json")`
- [x] `_cmd_explain` orchestration sequence spelled out step-by-step (7 steps)
- [x] `_format_explain` output format specified verbatim with three concrete examples (task with match, task without match, non-task)
- [x] Non-task detection via `"moscow"` key presence — structural, not string-based
- [x] Error message table covers all four failure modes
- [x] Non-trivial trade-offs have rejected alternative documented (4 decisions)
- [x] Known risks listed with mitigations (5 risks)
- [x] Testing plan: 5 `TestFormatExplain` + 5 `TestCmdExplain` + 1 `TestAppExplainSubcommand` + 3 integration cases
- [x] Testing covers happy path + ≥2 error cases per class
- [x] Implementation sequence is 5 commits, each independently executable
- [x] No new library introduced — stdlib only (`json`, `pathlib`, `argparse`)
- [x] CLAUDE.md conventions cited and respected (naming, errors, no comments, confidence labels)
