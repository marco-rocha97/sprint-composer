# Tech Spec: CLI `run` + 5-Block Proposal Output — `T05`

> **SPEC:** [`docs/specs/sprint-composer.md`](../specs/sprint-composer.md)
> **Plan:** [`docs/plans/sprint-composer.md`](../plans/sprint-composer.md) — task `T05`
> **Conventions applied:** `CLAUDE.md` (project) · `rules/dependencies.md` · `rules/testing.md` · `rules/anti-patterns.md`
>
> This document details **how** to deliver T05. The **why** lives in the SPEC; **what** and **in what order**, in the Plan.

---

## Task Scope

- **Behavior delivered:** The FDE invokes `sprint-composer run <transcript-path>`. The CLI parses the transcript header, refuses with a named error if it is missing or malformed, runs Layers 1–3 (with per-layer progress lines to stderr), prints a human-readable 5-block proposal to stdout, and writes a machine-readable JSON sibling next to the transcript. Each sprint task in the proposal carries a stable id (`segment_id`) for `explain` (T06). All four interface states (empty, loading, success, error) are covered.
- **SPEC stories/criteria covered:**
  - Scenario *"Produce the 5-block proposal output"*
  - All four interface states (empty / loading / success / error) from *Experience Design*
  - The "nothing is silently dropped" non-negotiable principle
  - Demo criterion 1 (correct typology surfaced in correct output blocks)
- **Depends on:** T04 (`allocate_tasks` / `Layer3Result` / `AllocatedTask` contracts)
- **External dependencies:** None new — `google-generativeai>=0.7` (Layers 1–3 already consume it); `argparse` is stdlib

---

## Architecture

- **General approach:** T05 adds two new modules — `transcript.py` (transcript parsing, pure Python, no side effects beyond receiving the file text) and `cli.py` (CLI entry point, pipeline orchestration, 5-block formatting, JSON serialization). The `app()` callable in `cli.py` is the console script entry point already declared in `pyproject.toml`.
- **Why `transcript.py` is separate:** Header and body parsing is independently testable with no CLI dependency. One-responsibility rule from CLAUDE.md architecture.
- **Why formatting stays inline in `cli.py`:** T06 uses a different output format (single task detail). No shared formatter logic is proven yet. Extracting a `formatter.py` before T06 proves overlap would be a speculative abstraction (`rules/anti-patterns.md`).
- **CLI library: `argparse` (stdlib):** T05 + T06 require exactly two subcommands (`run`, `explain`). `argparse` handles this cleanly with `add_subparsers()`. No new dependency is justified for two subcommands.
- **Affected modules:** No existing modules modified.
- **New files:**
  - `src/sprint_composer/transcript.py` — header/body parsing
  - `src/sprint_composer/cli.py` — CLI entry point, pipeline orchestration, 5-block formatting, JSON serialization
  - `tests/test_transcript.py` — unit tests for parsing
  - `tests/test_cli.py` — unit + integration tests for CLI

> **Decision source:** CLAUDE.md (stack: Python/uv/argparse/pytest), `rules/dependencies.md`, `rules/anti-patterns.md`, user confirmation (Block 3 = open_questions + aggregated gap questions).

---

## Contracts

### `src/sprint_composer/transcript.py`

```python
from dataclasses import dataclass


@dataclass
class TranscriptHeader:
    day: int
    phase: str
    participants: list[str]


class HeaderParseError(Exception):
    """Raised when the transcript header is missing or malformed."""


def parse_header(text: str) -> tuple[TranscriptHeader, int]:
    """
    Parse the YAML-ish header block from a transcript string.

    Expected format:
        day: <int>
        phase: <str>
        participants: [Name1, Name2, ...]
        ---

    Returns (TranscriptHeader, body_start) where body_start is the character
    offset of the first character after the '---' line.

    Raises HeaderParseError with a named, actionable message if:
      - '---' separator is not found
      - 'day:' field is missing
      - 'day' value is not a valid integer
      - 'phase:' field is missing
      - 'participants:' field is missing
      - participants list is empty after parsing
    """


def parse_body(text: str, body_start: int) -> list[str]:
    """
    Split the transcript body into non-empty paragraph segments.

    Splits text[body_start:] on double newlines and strips each segment.
    Returns only segments with non-whitespace content.
    """
```

**Error messages** (each names the exact missing/malformed field):

| Condition | Message |
|---|---|
| No `---` separator | `"No header separator '---' found. Add the header block (day:/phase:/participants:) before the '---' line."` |
| Missing `day:` | `"Missing header field 'day'. Add 'day: <1-15>' to the header."` |
| Non-integer `day` value | `"Header field 'day' is not a valid integer: '<value>'. Example: 'day: 10'."` |
| Missing `phase:` | `"Missing header field 'phase'. Add 'phase: <Discovery|Setup|Simulation|Go-live>'."` |
| Missing `participants:` | `"Missing header field 'participants'. Add 'participants: [Name1, Name2]'."` |
| Empty participants | `"Header field 'participants' is empty. Add at least one participant name."` |

**Implementation approach for `parse_header`:** parse field-by-field (not a single all-or-nothing regex) so each failure names its field. Find the `---` separator first (regex `^---\s*$` multiline), then extract `day:`, `phase:`, `participants:` each with their own `re.search` within the header block. This diverges from `test_fixtures.py`'s single-regex approach, which was acceptable there (tests only run on valid fixtures) but cannot produce per-field error messages.

---

### `src/sprint_composer/cli.py`

```python
def app() -> None:
    """
    Entry point for the sprint-composer CLI.

    Subcommands:
      run <transcript_path>   — parse header, run L1→L2→L3, emit 5-block proposal
      (explain <task_id>      — T06 adds this subcommand here)

    With no subcommand: prints help + example command to stdout; exits 0.
    """


def _cmd_run(transcript_path: Path) -> None:
    """
    Orchestrate the full pipeline and emit the 5-block proposal.

    Reads transcript_path, parses header + body, runs classify_transcript →
    enrich_segments → allocate_tasks, prints formatted proposal to stdout,
    writes JSON sibling to transcript_path.with_suffix('.json').

    All user-facing errors print 'Error: <named message>' to stderr and exit 1.
    Progress lines print to stderr so stdout stays clean for the proposal.
    """


def _format_proposal(
    transcript_path: Path,
    header: TranscriptHeader,
    l3_result: Layer3Result,
    open_questions: list[ClassifiedSegment],
    gap_question_tasks: list[AllocatedTask],
    decisions: list[ClassifiedSegment],
    noise: list[ClassifiedSegment],
) -> str:
    """Build the full 5-block proposal as a human-readable string."""


def _build_json_artifact(
    transcript_path: Path,
    header: TranscriptHeader,
    l3_result: Layer3Result,
    open_questions: list[ClassifiedSegment],
    decisions: list[ClassifiedSegment],
    noise: list[ClassifiedSegment],
) -> dict[str, Any]:
    """Build the machine-readable JSON artifact dict."""


def _task_title(excerpt: str) -> str:
    """Return first sentence of excerpt, capped at 80 chars with ellipsis if truncated."""


def _progress(msg: str) -> None:
    """Print a progress line to stderr."""


def _die(msg: str) -> None:
    """Print 'Error: <msg>' to stderr and sys.exit(1)."""
```

**`_cmd_run` orchestration sequence:**

1. Check `transcript_path.exists()` → `_die("File not found: <path>")` if missing
2. `transcript_path.read_text()` → wrap `OSError` in `_die()`
3. `parse_header(text)` → wrap `HeaderParseError` in `_die()` (pass-through message)
4. `parse_body(text, body_start)` → `_die()` if result is empty
5. `_progress("Layer 1: classifying…")` → `classify_transcript(segments)` → wrap `ClassificationError`, `EnvironmentError` in `_die()`
6. `_progress("Layer 2: enriching…")` → `enrich_segments(l1_result)` → wrap `EnrichmentError`, `EnvironmentError` in `_die()`
7. `_progress("Layer 3: allocating…")` → `allocate_tasks(l2_result, phase=header.phase, day=header.day)` → wrap `AllocationError`, `EnvironmentError` in `_die()`
8. Partition non-task segments: `open_questions`, `decisions`, `noise` from `l1_result.segments`
9. Collect `gap_question_tasks` — all `AllocatedTask` instances (in_sprint + out_of_sprint) where `task.gap_questions` is non-empty
10. `print(_format_proposal(...))` to stdout
11. Build JSON → write to `transcript_path.with_suffix(".json")`
12. `print(f"\nJSON artifact written to: {json_path}")` to stdout

---

## Data Model

### Stdout format — 5-block proposal

```
=== Sprint Composer — Proposal ===
Transcript: /path/to/transcript.txt
Phase: Simulation (Day 10)
Participants: Dr. Sarah Chen, James Rodriguez, Maria Gonzalez, Mike Thompson
Generated: 2026-05-15T14:23:00+00:00

──────────────────────────────────────────────────
BLOCK 1: PROPOSED SPRINT TASKS
──────────────────────────────────────────────────

[S01] We need to implement Single Sign-On integration with our Active Directory...
  MoSCoW:     Must
  Confidence: HIGH
  Effort:     5 days
  Blockers:   Identity provider configuration; Network security group rules
  Reasoning:  SSO is a prerequisite for all authenticated workflows in Simulation.
  Excerpt:    "We need to implement Single Sign-On integration with our Active Directory
               to streamline provider access..."

[S04] The nursing team raised an interesting request during the UAT sessions
  MoSCoW:     Should
  Confidence: MEDIUM
  Effort:     estimate not available
  Questions to unlock estimate:
    • What is the technical scope for consolidating the three systems?
    • Are there vendor APIs or integration guides available for the scheduling system?
    • What are the acceptance criteria for this to be considered complete?
  ⚠ Needs Lead decision: MoSCoW level uncertain without effort estimate for scoping.
  Reasoning:  Workflow consolidation scope is unclear; needs Lead input on phasing.
  Excerpt:    "The nursing team raised an interesting request during the UAT sessions..."

──────────────────────────────────────────────────
BLOCK 2: OUT OF SPRINT
──────────────────────────────────────────────────

[S03] We should also consider building a brand new reporting dashboard...
  Reason: Brand-new reporting dashboard is new scope incompatible with Simulation phase.

──────────────────────────────────────────────────
BLOCK 3: PENDING CUSTOMER ANSWERS
──────────────────────────────────────────────────

[S07] Open question from meeting:
  "One open question we need to resolve before we proceed: who owns the responsibility
  for HIPAA compliance sign-off on the new integration layer?"

Estimation questions (task S04):
  • What is the technical scope for consolidating the three systems?
  • Are there vendor APIs or integration guides available for the scheduling system?
  • What are the acceptance criteria for this to be considered complete?

──────────────────────────────────────────────────
BLOCK 4: RECORDED DECISIONS
──────────────────────────────────────────────────

[S06] Decision:
  "We've made a firm decision: the staging environment will be used for all UAT
  moving forward."

──────────────────────────────────────────────────
BLOCK 5: DISCARD APPENDIX
──────────────────────────────────────────────────

[S08] Noise (off-topic):
  "By the way, did everyone have a good lunch in the cafeteria today?"

──────────────────────────────────────────────────

JSON artifact written to: /path/to/transcript.json
```

**`_task_title` rule:** `excerpt.split(".")[0].strip()`, capped at 80 chars (append `"..."` if truncated).

**Block 3 composition:** first all `open_question` segments (in `segment_id` order), then gap questions grouped by task (in `segment_id` order of the task). Gap questions also appear inline in Block 1 under their task — this duplication is intentional so the FDE sees them both in task context and in aggregated form.

---

### JSON sibling schema

Written to `transcript_path.with_suffix(".json")`. Overwrites on re-run (v0 always reflects the latest run).

```json
{
  "metadata": {
    "transcript_path": "<absolute resolved path>",
    "generated_at": "<ISO 8601 UTC — datetime.now(timezone.utc).isoformat()>",
    "header": {
      "day": 10,
      "phase": "Simulation",
      "participants": ["Dr. Sarah Chen", "James Rodriguez", "Maria Gonzalez", "Mike Thompson"]
    }
  },
  "sprint_tasks": [
    {
      "segment_id": "S01",
      "excerpt": "<verbatim — never modified>",
      "type": "firm_request",
      "l1_confidence": "HIGH",
      "l1_reasoning": "...",
      "reference_match": {
        "task_id": "sso-ldap-integration",
        "task_name": "Single Sign-On via LDAP/Active Directory",
        "project_id": "retail-loyalty-integration",
        "project_name": "Retail Loyalty Program Digital Integration",
        "effort_days": 5,
        "effort_confidence": "HIGH",
        "blockers": ["Identity provider configuration", "Network security group rules"],
        "notes": "..."
      },
      "effort": "5 days",
      "l2_confidence": "HIGH",
      "blockers": ["Identity provider configuration", "Network security group rules"],
      "gap_questions": [],
      "enrichment_reasoning": "...",
      "moscow": "Must",
      "sprint_allocation": "in_sprint",
      "allocation_confidence": "HIGH",
      "dependency_order": 1,
      "needs_lead_decision": false,
      "lead_decision_reason": "",
      "allocation_reasoning": "SSO is a prerequisite for all authenticated workflows."
    }
  ],
  "out_of_sprint": [
    {
      "segment_id": "S03",
      "excerpt": "<verbatim>",
      "type": "firm_request",
      "l1_confidence": "HIGH",
      "l1_reasoning": "...",
      "reference_match": null,
      "effort": "estimate not available",
      "l2_confidence": "LOW",
      "blockers": [],
      "gap_questions": ["...", "..."],
      "enrichment_reasoning": "...",
      "moscow": "Should",
      "sprint_allocation": "out_of_sprint",
      "allocation_confidence": "HIGH",
      "dependency_order": 0,
      "needs_lead_decision": false,
      "lead_decision_reason": "",
      "allocation_reasoning": "New scope incompatible with Simulation phase."
    }
  ],
  "pending_answers": {
    "open_questions": [
      {
        "segment_id": "S07",
        "excerpt": "<verbatim>",
        "l1_confidence": "HIGH",
        "l1_reasoning": "..."
      }
    ],
    "gap_questions": [
      {
        "task_segment_id": "S04",
        "task_title": "The nursing team raised an interesting request...",
        "questions": ["...", "...", "..."]
      }
    ]
  },
  "decisions": [
    {
      "segment_id": "S06",
      "excerpt": "<verbatim>",
      "l1_confidence": "HIGH",
      "l1_reasoning": "..."
    }
  ],
  "discard_appendix": [
    {
      "segment_id": "S08",
      "excerpt": "<verbatim>",
      "l1_confidence": "HIGH",
      "l1_reasoning": "..."
    }
  ]
}
```

**Serialization:** `dataclasses.asdict()` for `AllocatedTask` and `TranscriptHeader`. All enums (`MoSCoW`, `SprintAllocation`, `Confidence`) are `str` subclasses — `json.dumps()` serializes them as strings natively; no custom encoder needed. `reference_match: None` serializes to JSON `null`.

**T06 compatibility contract:** `sprint_tasks` and `out_of_sprint` each carry the full `AllocatedTask` field set (every L1, L2, L3 field). T06's `explain <task-id>` reads this JSON and uses `segment_id` as the lookup key.

---

### "Nothing is silently dropped" invariant

Every Layer-1 classified segment lands in exactly one JSON location:

| L1 type | JSON key | Stdout block |
|---|---|---|
| `firm_request` | `sprint_tasks` or `out_of_sprint` | Block 1 or Block 2 |
| `latent_request` | `sprint_tasks` or `out_of_sprint` | Block 1 or Block 2 |
| `open_question` | `pending_answers.open_questions` | Block 3 |
| `decision` | `decisions` | Block 4 |
| `noise` | `discard_appendix` | Block 5 |

**Verification:** `TestBuildJsonArtifact` asserts that the total count of entries across all five JSON locations equals `len(l1_result.segments)`.

---

## Error Handling Contract

All errors from `_cmd_run` follow the same pattern — no raw stack traces reach the user:

```python
_die("<named, actionable message>")
# → prints "Error: <message>" to stderr
# → sys.exit(1)
```

| Source | Error message pattern |
|---|---|
| File not found | `"File not found: <path>"` |
| File unreadable (`OSError`) | `"Cannot read file '<path>': <os error message>"` |
| `HeaderParseError` | Passed through verbatim (already field-named per table above) |
| Empty body after valid header | `"Transcript body is empty — no segments found after the header."` |
| `ClassificationError` | `"Layer 1 classification failed: <message>"` |
| `EnrichmentError` | `"Layer 2 enrichment failed: <message>"` |
| `AllocationError` | `"Layer 3 allocation failed: <message>"` |
| `EnvironmentError` (API key) | Passed through verbatim (already named: `"GEMINI_API_KEY is not set..."`) |

---

## Trade-offs and Rejected Alternatives

**Decision: `argparse` (stdlib) instead of `typer` / `click`**
- **Rejected:** typer or click — a new dependency for two subcommands (`run` + `explain`) with no existing CLI library to build on.
- **Reason:** `rules/dependencies.md` — "No new library without discussion; reuse over install." `argparse` handles `add_subparsers()` with help text and exit-on-error cleanly.

**Decision: `segment_id` as task-id (not a new `TASK-nn` scheme)**
- **Rejected:** new TASK-01 style IDs — adds a mapping layer (segment_id → task_id) with no user value. `segment_id` is already stable within a run and unique per classified segment.
- **Reason:** SPEC *"Every task is auditable"*; simplicity. `explain S01` is already meaningful and traceable.

**Decision: formatting inline in `cli.py` (not a separate `formatter.py`)**
- **Rejected:** `formatter.py` — T06 `explain` uses a different output format (single task detail), so no shared formatter logic is proven yet.
- **Reason:** `rules/anti-patterns.md` — "No speculative abstractions."

**Decision: progress lines to `stderr` (not `stdout`)**
- **Rejected:** stdout — progress lines would mix with the proposal, breaking `grep`, `tee`, or file redirect workflows.
- **Reason:** Unix pipeline convention; SPEC "printed to stdout" refers to the proposal specifically.

**Decision: `dataclasses.asdict()` for JSON serialization**
- **Rejected:** manual serialization — verbose for nested dataclasses (`AllocatedTask` → `ReferenceMatch`). Rejected pydantic — new dependency for one serialization call.
- **Reason:** `dataclasses.asdict()` recurses into nested dataclasses automatically. All enums are `str` subclasses so `json.dumps()` serializes them as strings with no custom encoder.

**Decision: field-by-field header parsing (not a single regex)**
- **Rejected:** single all-or-nothing regex (pattern from `test_fixtures.py`) — fails silently or with a generic message when any field is missing; can't name which field.
- **Reason:** SPEC *"named, actionable error stating exactly which field is missing"*. Field-by-field parsing names each failure independently. `test_fixtures.py`'s single regex is appropriate there (runs only on valid fixture data).

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Layer 1–3 raise exceptions not caught | Raw stack trace exposed to user | Each layer call wrapped in try/except for `ClassificationError`, `EnrichmentError`, `AllocationError`, `EnvironmentError`; all routed to `_die()` |
| JSON sibling overwrites existing file on re-run | Silent data loss of previous run | Acceptable in v0 — T06 always reads the latest sibling by design; documented scope decision |
| `dataclasses.asdict()` on str enum fields | `TypeError` during `json.dumps()` | All enums (`MoSCoW`, `SprintAllocation`, `Confidence`) inherit from `str` — `json.dumps` serializes them as strings natively. Verified in `TestBuildJsonArtifact` via `json.dumps(artifact)` call |
| `transcript_path.with_suffix(".json")` on a `.json` transcript | JSON written over input transcript | v0 only supports `.txt` transcripts (SPEC: "a plain-text file"); negligible risk without a guard |
| Empty body after valid header | `classify_transcript([])` called with empty list | Guarded: `_cmd_run` checks `if not segments:` and calls `_die()` before any layer call |
| `argparse` calls `sys.exit(2)` on unknown subcommand args | argparse raw error to stderr | argparse default error messages are readable; SPEC only requires custom messages for runtime errors, not argument parsing failures |

---

## Testing Plan

### `tests/test_transcript.py`

#### `TestParseHeader` — unit (pure Python, no I/O)

- Valid header from `fixtures/transcript.txt` text → returns correct `TranscriptHeader` (day=10, phase="Simulation", 4 participants) and non-zero `body_start`
- `body_start` points past `---\n` (regression: not before it) — verified by checking `text[body_start - 1]` is `\n`
- Missing `---` separator → `HeaderParseError` with "---" or "separator" in message
- Missing `day:` field → `HeaderParseError` with "day" in message
- Non-integer `day` value (`day: abc`) → `HeaderParseError` with "day" and "integer" in message
- Missing `phase:` field → `HeaderParseError` with "phase" in message
- Missing `participants:` field → `HeaderParseError` with "participants" in message
- Empty participants (`participants: []`) → `HeaderParseError` with "participants" and "empty" in message

#### `TestParseBody` — unit (pure Python, no I/O)

- Fixture body (8 segments split by `\n\n`) → list of 8 non-empty strings
- Body with no double-newlines → list with 1 element
- Body with leading/trailing blank lines → strips correctly; all returned segments are non-empty

---

### `tests/test_cli.py`

#### `TestTaskTitle` — unit (pure Python, no I/O)

- Excerpt ending with `.` at position ≤80 → returns first sentence
- Excerpt with first sentence > 80 chars → returns first 77 chars + `"..."`
- Excerpt with no `.` → returns up to 80 chars (no crash)

#### `TestFormatProposal` — unit (no I/O, no Gemini)

Uses minimal fixture `AllocatedTask` and `ClassifiedSegment` objects (same builder pattern as `test_layer3.py:create_sample_enriched_segment`).

- Output string contains all 5 block headers in order: `"BLOCK 1"`, `"BLOCK 2"`, `"BLOCK 3"`, `"BLOCK 4"`, `"BLOCK 5"`
- Block 1 contains `[S01]` for in-sprint task
- Block 2 contains `[S03]` for out-of-sprint task (with allocation_reasoning)
- Block 3 contains open_question segment excerpt
- Block 3 contains gap questions from unmatched task, annotated with `task_segment_id`
- Block 4 contains decision excerpt
- Block 5 contains noise excerpt
- `needs_lead_decision=True` task shows lead decision reason text in Block 1 output

#### `TestBuildJsonArtifact` — unit (no I/O, no Gemini)

- JSON dict has all top-level keys: `metadata`, `sprint_tasks`, `out_of_sprint`, `pending_answers`, `decisions`, `discard_appendix`
- `metadata.header` has `day`, `phase`, `participants`
- `sprint_tasks` list length equals `len(l3_result.in_sprint)`
- Each sprint task dict has `segment_id`, `excerpt`, `moscow`, `sprint_allocation`, `effort`, `gap_questions`, `reference_match`
- `reference_match` is `None` (serializes to `null`) for an `AllocatedTask` with no match
- `json.dumps(artifact)` completes without `TypeError` (enum serialization regression test)
- **Nothing-dropped invariant:** `len(sprint_tasks) + len(out_of_sprint) + len(open_questions) + len(decisions) + len(discard_appendix) == total_l1_segments`
- `pending_answers.open_questions` count equals number of `open_question` segments passed in
- `pending_answers.gap_questions` has one entry per task with non-empty `gap_questions`

#### `TestRunErrorHandling` — unit (no Gemini)

Uses `capsys` + `pytest.raises(SystemExit)`. All assertions check `exc.value.code == 1` and `"Error:" in captured.err`.

- File not found (`tmp_path / "nonexistent.txt"`) → stderr contains `"File not found"`, exit 1
- Malformed header (text with no `---`) → stderr contains `"Error:"`, exit 1
- Malformed header (non-integer day: `day: abc`) → stderr contains `"day"`, exit 1
- Empty body after valid header → stderr contains `"Error:"` and `"empty"`, exit 1

#### `TestRunHappyPath` — unit (monkeypatched layers, no real Gemini)

Uses `monkeypatch` to replace `sprint_composer.cli.classify_transcript`, `sprint_composer.cli.enrich_segments`, `sprint_composer.cli.allocate_tasks` with lambdas returning pre-built fixture results. Uses `capsys` and `tmp_path`.

```python
monkeypatch.setattr("sprint_composer.cli.classify_transcript", lambda *a, **kw: FAKE_L1)
monkeypatch.setattr("sprint_composer.cli.enrich_segments", lambda *a, **kw: FAKE_L2)
monkeypatch.setattr("sprint_composer.cli.allocate_tasks", lambda *a, **kw: FAKE_L3)
```

- Stdout contains all 5 block headers
- Stderr contains `"Layer 1"`, `"Layer 2"`, `"Layer 3"` progress lines
- JSON file written to `transcript_path.with_suffix(".json")`
- JSON file is valid JSON (parseable with `json.loads`)
- No `SystemExit` raised

#### `TestAppNoArgs` — unit (no Gemini)

```python
monkeypatch.setattr(sys, "argv", ["sprint-composer"])
with pytest.raises(SystemExit) as exc:
    app()
assert exc.value.code == 0
captured = capsys.readouterr()
assert "run" in captured.out or "run" in captured.err
```

#### `TestIntegration` — skipped unless `GEMINI_API_KEY` is set

```python
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
class TestIntegration:
```

Uses `tmp_path` + copies of `fixtures/transcript.txt` and `fixtures/reference_bank.json` so the JSON sibling is written to the temp directory, not the fixture directory.

- Full pipeline runs to completion without raising
- Stdout contains all 5 block headers
- `S03` (admin dashboard) appears in Block 2 stdout output (demo criterion 3 — out of sprint)
- `S07` (HIPAA question) appears in Block 3 stdout output (open question routing)
- `S06` (staging env decision) appears in Block 4 stdout output (decision routing)
- `S08` (cafeteria) appears in Block 5 stdout output (noise routing)
- JSON artifact is written and parseable
- JSON `sprint_tasks` is non-empty
- Nothing-dropped invariant holds: total segments across all JSON blocks equals total transcript segments

> **Framework/pattern:** pytest `capsys`, `monkeypatch`, `tmp_path` (all built-in). `MockGeminiClient` pattern not needed directly — layer functions are monkeypatched at the `cli` module level. Source: `tests/test_layer3.py` for fixture builder patterns.

---

## Implementation Sequence

Each step is one cohesive commit:

1. **`transcript.py` + `tests/test_transcript.py`** — `parse_header` (field-by-field, named errors), `parse_body`, `HeaderParseError`; all `TestParseHeader` and `TestParseBody` tests pass with no layer dependency
2. **`_format_proposal`, `_build_json_artifact`, `_task_title`, `_progress`, `_die` in `cli.py` + `TestFormatProposal`, `TestBuildJsonArtifact`, `TestTaskTitle`** — pure functions; no Gemini; `json.dumps()` enum regression verified in `TestBuildJsonArtifact`
3. **`_cmd_run` error-handling paths + `TestRunErrorHandling`** — file not found, malformed header (two variants), empty body; all testable without Gemini via `capsys` + `pytest.raises(SystemExit)`
4. **`app()` + `_cmd_run` happy path + `TestRunHappyPath` + `TestAppNoArgs`** — monkeypatched layer calls; full stdout format and JSON output verified; `sys.argv` monkeypatched for no-args test
5. **`TestIntegration`** (guarded by `GEMINI_API_KEY`) — run on copy of `fixtures/transcript.txt`; verify S03 → Block 2, S07 → Block 3, S06 → Block 4, S08 → Block 5; nothing-dropped count assertion

---

## Conventions Applied (from CLAUDE.md)

- Stack: Python with `uv`; `argparse` stdlib (no new dep); `dataclasses` + `json` stdlib for serialization
- Tests: `pytest`, `capsys` + `monkeypatch` + `tmp_path` built-ins; integration test guarded by `@pytest.mark.skipif`
- Naming: English, `snake_case` functions, `PascalCase` classes, `_`-prefixed private functions
- No comments explaining *what* — only *why* where non-obvious
- Confidence: always `HIGH | MEDIUM | LOW` word labels (SPEC accessibility requirement; color alone is forbidden)
- Error pattern: `_die()` for all user-facing errors — named message to stderr, exit 1 (consistent with SPEC named-error requirement)
- Progress to `stderr`, proposal to `stdout` (Unix pipeline convention)
- Datetime: `datetime.now(timezone.utc).isoformat()` for `generated_at` (UTC, ISO 8601, per `rules/datetime.md`)

---

## Ready to Code?

- [x] Architecture described with modules and new files named
- [x] Contracts (public functions, private functions, error message table) in final form
- [x] `_cmd_run` orchestration sequence spelled out step-by-step
- [x] Stdout 5-block format specified verbatim with concrete example output
- [x] JSON schema specified with field-level notes and T06 compatibility contract
- [x] "Nothing is silently dropped" invariant formalized as table + verification test case
- [x] T06 compatibility: `segment_id` as task-id, full `AllocatedTask` field set in JSON
- [x] Non-trivial trade-offs have rejected alternative documented (6 decisions)
- [x] Known risks listed with mitigations (6 risks)
- [x] Testing plan covers happy path + ≥2 error cases per class + integration test
- [x] Implementation sequence is executable without clarification questions (5 commits)
- [x] No new library introduced (`argparse`, `dataclasses`, `json` are all stdlib)
- [x] CLAUDE.md conventions cited and respected (datetime, progress/error streams, naming)
