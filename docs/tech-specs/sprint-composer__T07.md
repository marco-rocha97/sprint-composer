# Tech Spec: Demo Hardening — Discovery Fixture · Scope-Creep Classification · Gemini Warning Fix — `T07`

> **SPEC:** [`docs/specs/sprint-composer.md`](../specs/sprint-composer.md)
> **Plan:** [`docs/plans/sprint-composer.md`](../plans/sprint-composer.md)
> **Conventions applied:** `CLAUDE.md` (project) · `rules/testing.md` · `rules/anti-patterns.md`
>
> This document details **how** to deliver T07. The **why** lives in the diagnosis below; **what** and **in what order**, in the implementation sequence.

---

## Context and Motivation

Three coordinated pre-demo problems — bundled because they interact and because shipping them together avoids intermediate states where the warning is still visible or the fixture is mismatched against new tests.

**Problem A — Layer 3 reasoning is mechanically identical for all out-of-sprint items.**
When the transcript is on Day 10 / Simulation, SSO, push notifications, and the dashboard all receive the same one-line justification: "incompatible with the Simulation phase's focus on existing scope only." A technical interviewer reads three identical sentences and concludes the agent applied a rule without understanding the content. The three items are fundamentally different: SSO has a 5-day historical reference and could be a prerequisite for authenticated workflows; push notifications are a v2 deferral; the dashboard is a negotiable scope item. The missing output is not "out of sprint" (which disappears from the radar) but "proposed scope creep with stated impact" — e.g. "client requested 3 new features on Day 10; accepting SSO now carries prerequisite risk for go-live; recommendation: negotiate v2 or change scope."

**Problem B — Only one task lands in Block 1 (proposed sprint tasks) during the demo.**
The root cause is the fixture phase. In Simulation (days 8–12), new scope is incompatible by definition — so every firm_request goes to Block 2. A demo that ends with one task in Block 1 looks weak. The fix is to change the fixture to Day 2 / Discovery, where new features, integrations, and scoping discussions are all appropriate. In Discovery, SSO (Must, 5 days, HIGH), push notifications (Should, 8 days, HIGH), and nursing workflow consolidation (Should, 12 days, MEDIUM) all land in Block 1; the IoT glucose monitor lands in Block 2 as an information-gap scope item. This change is reversible and requires no content rewrite of the transcript.

**Problem C — A FutureWarning from `google.generativeai` appears twice in demo output.**
The deprecation warning is emitted by the library import and surfaces in test output and in the live demo terminal. It kills credibility in 5 seconds during a technical presentation. Suppressing it via `warnings.filterwarnings` is the v0 fix; switching to `google.genai` is the correct long-term fix but is out of scope for v0.

---

## Task Scope

- **Behavior delivered:** (A) the demo fixture is on Day 2 / Discovery so Block 1 shows ≥3 proposed sprint tasks with differentiated confidence levels; (B) every out-of-sprint item in Block 2 carries a scope-creep category (`prerequisite_risk | deferred_v2 | deferred_phase | information_gap`) and a one-sentence business impact statement, making each rejection specific rather than generic; (C) the FutureWarning from `google.generativeai` is silenced in all three layer modules so it never appears in test output or the demo terminal.
- **SPEC stories/criteria covered:**
  - Demo criterion 2 (LOW confidence with explicit reason — now visible with multiple confidence levels in Block 1)
  - Demo criterion 3 (out-of-sprint with justification tied to Khal's 15-day cycle — now carries specific category and impact)
  - "Nothing is silently dropped" — unaffected; all segments still land in exactly one block
- **Depends on:** T01–T06 (all fully implemented; this task modifies existing code only)
- **External dependencies:** None — fixture is synthetic, warning suppression is stdlib

---

## Architecture

Three independent sub-tasks; each touches different files. They share one commit boundary (see Implementation Sequence).

### Sub-task A: Fixture phase change

**Files changed:** `src/fixtures/transcript.txt` (2 lines), `src/fixtures/taxonomy_template.json` (notes fields only), `tests/test_layer3.py` (integration test args and one assertion).

**What changes in the transcript:** Only the header. The 8 body segments are untouched — their content drives typology, not phase.

```
day: 2          ← was: day: 10
phase: Discovery ← was: phase: Simulation
participants: [Dr. Sarah Chen, James Rodriguez, Maria Gonzalez, Mike Thompson]
```

**Expected routing in Discovery:** Based on the reference bank and phase rules coded in `KHAL_PHASES`:

| Segment | Type | Block | Reason |
|---|---|---|---|
| S01 SSO | firm_request | Block 1 | Must; 5-day reference match; HIGH confidence |
| S02 Push notifications | firm_request | Block 1 | Should; 8-day reference match; HIGH confidence |
| S03 Dashboard | firm_request | Block 1 or 2 | Could; 10-day reference; MEDIUM confidence; borderline |
| S04 IoT glucose | firm_request | Block 2 | information_gap; no reference match; LOW confidence |
| S05 Nursing workflow | latent_request | Block 1 | Should; 12-day reference; MEDIUM confidence |
| S06 Staging decision | decision | Block 4 | — |
| S07 HIPAA question | open_question | Block 3 | — |
| S08 Cafeteria | noise | Block 5 | — |

> **Why the dashboard is borderline:** In Discovery, analytics work is appropriate scope. Whether the LLM places it in sprint depends on effort (10 days against a 15-day cycle) and the presence of a reference match. Either routing is acceptable for the demo — the key is that SSO, push, and nursing are reliably in Block 1, giving ≥3 tasks with differentiated confidence levels.

**Taxonomy template update:** Change `notes` fields to reflect Discovery context. `expected_type` values are unchanged — the Layer-1 type is determined by the segment content, not the phase.

**Integration test update in `test_layer3.py`:** The five `TestIntegration` methods currently pass `"Simulation", 10`. They must change to `"Discovery", 2` to match the fixture. The assertion `test_s03_routes_to_out_of_sprint_on_simulation_phase` (which tested Simulation-specific routing) is replaced by `test_s01_routes_to_in_sprint_in_discovery_phase` (which verifies that SSO — a Must item with a reference — lands in Block 1 in Discovery).

---

### Sub-task B: Scope-creep categorization

**Files changed:** `src/sprint_composer/models.py`, `src/sprint_composer/layer3.py`, `src/sprint_composer/cli.py`, `tests/test_layer3.py`, `tests/test_cli.py`.

#### `models.py` — Two new fields on `AllocatedTask`

```python
@dataclass
class AllocatedTask:
    # ... existing fields unchanged ...
    allocation_reasoning: str

    # Scope-creep fields — non-empty only when sprint_allocation == OUT_OF_SPRINT
    scope_creep_category: str  # "prerequisite_risk" | "deferred_v2" | "deferred_phase" | "information_gap" | ""
    scope_creep_impact: str    # one sentence: business cost of accepting; "" for in-sprint items
```

Plain `str` (not a formal `Enum`) because the empty-string value for in-sprint tasks makes an enum with `NONE = ""` awkward. Validation of allowed values is enforced in `_extract_allocation`. Both fields go after `allocation_reasoning` (last existing field) — required, no defaults, consistent with the existing dataclass pattern.

**Valid values for `scope_creep_category`:**

| Value | Meaning |
|---|---|
| `"prerequisite_risk"` | Could be a prerequisite for in-sprint work; late acceptance creates dependency risk |
| `"deferred_v2"` | Future version feature; not related to current delivery scope |
| `"deferred_phase"` | Appropriate scope, but belongs to a later phase in the 15-day cycle |
| `"information_gap"` | Cannot scope or estimate without additional vendor/customer information |
| `""` | Item is in-sprint (no scope-creep category applies) |

---

#### `layer3.py` — Prompt and extraction changes

**`_build_allocation_prompt` additions:**

Add two new instructions to the numbered list (after item 6 `allocation_reasoning`):

```
7. scope_creep_category: if sprint_allocation is "out_of_sprint", choose one of:
   - "prerequisite_risk": this item could be a prerequisite for in-sprint work; late acceptance creates dependency risk
   - "deferred_v2": this is a future version feature not related to current delivery scope
   - "deferred_phase": this is appropriate scope but belongs to a later phase in the 15-day cycle
   - "information_gap": this cannot be scoped without additional vendor/customer information
   If sprint_allocation is "in_sprint", use "" (empty string).
8. scope_creep_impact: if sprint_allocation is "out_of_sprint", one sentence stating the concrete
   business cost of accepting this scope into the current sprint.
   Example: "Accepting would extend go-live by approximately 1 week and require additional QA cycles."
   If sprint_allocation is "in_sprint", use "" (empty string).
```

Add two new fields to the JSON schema in the prompt:

```json
"scope_creep_category": "<prerequisite_risk|deferred_v2|deferred_phase|information_gap|>",
"scope_creep_impact": "<one sentence or empty string>"
```

**`_extract_allocation` additions:**

After extracting the existing fields per allocation dict, also extract:

```python
VALID_SCOPE_CREEP_CATEGORIES = {
    "prerequisite_risk", "deferred_v2", "deferred_phase", "information_gap", ""
}

scope_creep_category = alloc.get("scope_creep_category", "")
scope_creep_impact = alloc.get("scope_creep_impact", "")

if scope_creep_category not in VALID_SCOPE_CREEP_CATEGORIES:
    raise AllocationError(
        f"Invalid scope_creep_category for {segment_id}: '{scope_creep_category}'. "
        f"Must be one of {VALID_SCOPE_CREEP_CATEGORIES}"
    )
```

Existing mock responses in unit tests don't include these fields — `.get(..., "")` ensures backward compatibility; no existing unit tests break.

**`_merge_results` additions:**

Pass the two new fields through to `AllocatedTask`:

```python
task = AllocatedTask(
    ...
    allocation_reasoning=allocation_reasoning,
    scope_creep_category=alloc.get("scope_creep_category", ""),
    scope_creep_impact=alloc.get("scope_creep_impact", ""),
)
```

---

#### `cli.py` — Output format changes

**`_format_proposal` — Block 2 (out-of-sprint):**

Add `Category:` and `Impact:` lines when fields are non-empty. Current:

```
[S04] We're exploring whether we can integrate
  Reason: No vendor API available; cannot scope without procurement.
```

After:

```
[S04] We're exploring whether we can integrate
  Category: information_gap
  Impact:   Accepting without vendor documentation risks hidden effort and scope inflation.
  Reason:   No vendor API available; cannot scope without procurement.
```

Implementation — replace the Block 2 loop body from:

```python
lines.append(f"[{task.segment_id}] {title}")
lines.append(f"  Reason: {task.allocation_reasoning}")
lines.append("")
```

to:

```python
lines.append(f"[{task.segment_id}] {title}")
if task.scope_creep_category:
    lines.append(f"  Category: {task.scope_creep_category}")
if task.scope_creep_impact:
    lines.append(f"  Impact:   {task.scope_creep_impact}")
lines.append(f"  Reason:   {task.allocation_reasoning}")
lines.append("")
```

**`_task_to_dict` — JSON artifact:**

Add the two new fields to the dict returned for both `sprint_tasks` and `out_of_sprint` entries:

```python
"scope_creep_category": task.scope_creep_category,
"scope_creep_impact": task.scope_creep_impact,
```

**`_format_explain` — Layer 3 section for out-of-sprint tasks:**

After the `Sprint:` line, add scope-creep lines when present:

```python
if task_data.get("scope_creep_category"):
    lines.append(f"  Scope creep: {task_data['scope_creep_category']}")
if task_data.get("scope_creep_impact"):
    lines.append(f"  Impact:      {task_data['scope_creep_impact']}")
```

Full Layer 3 section for an out-of-sprint task with scope-creep fields:

```
Layer 3 — Allocation
  MoSCoW:      Could
  Sprint:      Out of sprint
  Confidence:  LOW
  Order:       0
  Scope creep: information_gap
  Impact:      Accepting without vendor documentation risks hidden effort and scope inflation.
  Reasoning:   No vendor API available; vendor procurement must precede scoping.
```

---

### Sub-task C: Gemini FutureWarning suppression

**Files changed:** `src/sprint_composer/layer1.py`, `src/sprint_composer/layer2.py`, `src/sprint_composer/layer3.py`.

**Pattern (identical in all three files):**

```python
import json
import os
import re
import warnings          # ← add to stdlib block

warnings.filterwarnings("ignore", category=FutureWarning, module="google")  # ← add before third-party

import google.generativeai as genai
```

Use `module="google"` to scope the filter to the google package only — not a blanket FutureWarning suppression that could hide legitimate warnings from other sources.

The call must appear at module level, before the `import google.generativeai` line, so it takes effect when the library is first imported.

> **Why here rather than in `cli.py` or `__init__.py`:** The layers are the import site for `google.generativeai`. Putting the filter there ensures it applies regardless of how the layers are imported (CLI, tests, future API usage). A filter in `cli.py` would miss direct layer imports in tests.

---

## Contracts

### `AllocatedTask` — updated fields (models.py)

```python
@dataclass
class AllocatedTask:
    segment_id: str
    excerpt: str
    type: SegmentType
    l1_confidence: Confidence
    l1_reasoning: str
    reference_match: ReferenceMatch | None
    effort: str
    l2_confidence: Confidence
    blockers: list[str]
    gap_questions: list[str]
    enrichment_reasoning: str
    moscow: MoSCoW
    sprint_allocation: SprintAllocation
    allocation_confidence: Confidence
    dependency_order: int
    needs_lead_decision: bool
    lead_decision_reason: str
    allocation_reasoning: str
    scope_creep_category: str   # ← new
    scope_creep_impact: str     # ← new
```

### `_extract_allocation` — updated return contract

The function continues to return `(list[dict], list[dict])`. Each allocation dict now includes `scope_creep_category` and `scope_creep_impact` keys (defaulting to `""` when absent from the Gemini response). Invalid `scope_creep_category` values raise `AllocationError`.

### JSON artifact — updated `out_of_sprint` entry shape

```json
{
  "segment_id": "S04",
  "excerpt": "...",
  "type": "firm_request",
  "l1_confidence": "HIGH",
  "l1_reasoning": "...",
  "reference_match": null,
  "effort": "estimate not available",
  "l2_confidence": "LOW",
  "blockers": [],
  "gap_questions": ["...", "...", "..."],
  "enrichment_reasoning": "...",
  "moscow": "Could",
  "sprint_allocation": "out_of_sprint",
  "allocation_confidence": "LOW",
  "dependency_order": 0,
  "needs_lead_decision": false,
  "lead_decision_reason": "",
  "allocation_reasoning": "...",
  "scope_creep_category": "information_gap",   ← new
  "scope_creep_impact": "Accepting without vendor documentation risks hidden effort and scope inflation."  ← new
}
```

In-sprint entries also carry these fields, both as `""`.

---

## Trade-offs and Rejected Alternatives

**Decision: Change only the transcript header (not body content) for Problem B**
- **Rejected:** Add new body segments that explicitly fit Discovery scope. Would require rewriting the taxonomy_template and all integration test segment references — higher effort with no additional demo value.
- **Reason:** The 8 existing segments produce the right typology mix in Discovery. SSO, push, and nursing provide high-confidence in-sprint tasks; IoT provides the information-gap out-of-sprint item. Phase change alone achieves the demo goal.

**Decision: Plain `str` for `scope_creep_category` (not a formal `Enum`)**
- **Rejected:** `ScopeCreepCategory(str, Enum)` with `NONE = ""` value. An enum with an empty-string member is an unusual Python pattern and makes the `if task.scope_creep_category:` truthiness check non-obvious.
- **Reason:** The existing codebase uses `Enum` for values that always have a meaningful value (MoSCoW, SprintAllocation, Confidence). The scope-creep category is legitimately absent for in-sprint items. Validated-string is idiomatic for optional categorical fields with a well-defined allowed set.

**Decision: `module="google"` scoping in `warnings.filterwarnings`**
- **Rejected:** `warnings.filterwarnings("ignore", category=FutureWarning)` (blanket suppression). Would silence FutureWarnings from all libraries in the process.
- **Reason:** The `module` argument limits suppression to warnings whose origin module matches `"google"`. This is targeted and follows the principle of minimum necessary suppression.

**Decision: Filter placed in each layer module (not in `cli.py` or `__init__.py`)**
- **Rejected:** Single call in `cli.py` — would miss direct layer imports in tests; warning appears in pytest output.
- **Rejected:** Single call in `__init__.py` — would suppress the warning only when importing the package; direct module imports in tests bypass `__init__.py`.
- **Reason:** The warning originates at the `import google.generativeai` site in each layer. Suppressing at the same location ensures coverage regardless of import path.

**Decision: Scope-creep fields always serialized (even when empty for in-sprint tasks)**
- **Rejected:** Omit the fields from in-sprint JSON entries. Would require `explain` to handle both shapes — conditional key access vs. guaranteed key access.
- **Reason:** Uniform JSON shape simplifies `_format_explain` (no `"scope_creep_category" in task_data` guard needed) and makes the artifact schema self-consistent.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| LLM returns unexpected `scope_creep_category` value | `AllocationError` during run | `_extract_allocation` validates against `VALID_SCOPE_CREEP_CATEGORIES` and raises with a clear message naming the invalid value |
| LLM puts all items in-sprint in Discovery (Block 2 empty) | Demo shows empty Block 2 | IoT glucose has no reference match and `estimate not available`; the prompt's `information_gap` category is designed to handle this case; acceptable if Block 2 has ≥1 item |
| LLM returns `scope_creep_impact` for in-sprint items (non-empty when it should be empty) | Extra text shown in Block 1 proposal | `_format_proposal` Block 1 does not print scope-creep fields — they're only shown in Block 2; JSON serialization writes them but `explain` only shows them when `sprint_allocation == "out_of_sprint"` |
| Existing `test_layer3.py` integration tests hardcode `"Simulation", 10` | Integration tests fail against Discovery fixture | All 5 integration tests updated in sub-task A to use `"Discovery", 2` |
| FutureWarning filter doesn't suppress in some Python/pytest configurations | Warning still appears | Verified post-implementation by running `uv run pytest tests/ -v` and confirming 0 FutureWarning lines in output |

---

## Testing Plan

### Sub-task A: Fixture changes

**`tests/test_fixtures.py`** — all 14 existing tests pass without modification:
- `test_header_day_is_integer_in_range` → Day 2 is in [1, 15] ✓
- `test_header_phase_is_valid` → Discovery is in valid set ✓
- `test_segment_count_matches_taxonomy` → segment count unchanged at 8 ✓
- `test_no_reference_match_for_glucose_api` → reference bank unchanged ✓

One new test added to `TestTranscriptHeader`:
- **`test_fixture_is_discovery_phase_on_day_two`** — asserts `header["phase"] == "Discovery"` and `header["day"] == 2`; this is the fixture contract for T07 and the demo.

**`tests/test_layer3.py`** — integration tests updated (5 changes):
- All `allocate_tasks(..., "Simulation", 10)` calls → `allocate_tasks(..., "Discovery", 2)`
- `test_s03_routes_to_out_of_sprint_on_simulation_phase` → replaced by `test_s01_routes_to_in_sprint_in_discovery_phase`: runs full pipeline with Discovery fixture; asserts S01 (SSO) appears in `result.in_sprint` with `sprint_allocation == IN_SPRINT`
- `test_at_least_one_needs_lead_decision_or_low_confidence` → still valid in Discovery (IoT glucose has LOW confidence); no assertion change needed
- `test_in_sprint_sorted_by_dependency_order` → still valid; no change needed
- `test_every_segment_in_one_output_list` → still valid; no change needed

---

### Sub-task B: Scope-creep categorization

**`tests/test_layer3.py`** — new unit test cases:

`TestExtractAllocation`:
- **`test_scope_creep_fields_extracted_for_out_of_sprint`** — response includes `"scope_creep_category": "information_gap"` and `"scope_creep_impact": "Accepting risks scope inflation."`; assert both values in returned allocation dict
- **`test_scope_creep_category_defaults_to_empty_string_when_absent`** — response omits `scope_creep_category` and `scope_creep_impact`; assert both default to `""`
- **`test_invalid_scope_creep_category_raises_error`** — response has `"scope_creep_category": "totally_wrong"`; assert `AllocationError` raised with `"scope_creep_category"` in message

`TestMergeResults`:
- **`test_out_of_sprint_task_carries_scope_creep_fields`** — allocation dict has `scope_creep_category="deferred_phase"` and `scope_creep_impact="..."` for an out-of-sprint segment; assert `task.scope_creep_category == "deferred_phase"` and `task.scope_creep_impact == "..."`
- **`test_in_sprint_task_has_empty_scope_creep_fields`** — allocation dict has `scope_creep_category=""` for an in-sprint segment; assert `task.scope_creep_category == ""` and `task.scope_creep_impact == ""`

**`tests/test_cli.py`** — new unit test cases:

New `TestFormatProposal` class (pure, no I/O, uses hand-crafted `Layer3Result`):
- **`test_out_of_sprint_with_scope_creep_shows_category_and_impact`** — task with `scope_creep_category="information_gap"` and `scope_creep_impact="Accepting risks scope inflation."`; assert both appear in Block 2 output with `Category:` and `Impact:` labels
- **`test_out_of_sprint_without_scope_creep_omits_category_and_impact_lines`** — task with empty `scope_creep_category`; assert `"Category:"` and `"Impact:"` do not appear in Block 2 output
- **`test_in_sprint_task_never_shows_scope_creep_fields`** — in-sprint task with non-empty `scope_creep_category` (edge case); assert `"Category:"` does not appear in Block 1 output (Block 1 does not render scope-creep fields regardless)

`TestFormatExplain` (extends existing class):
- **`test_out_of_sprint_task_with_scope_creep_shows_scope_creep_lines`** — `task_data` dict with `"sprint_allocation": "out_of_sprint"`, `"scope_creep_category": "deferred_phase"`, `"scope_creep_impact": "..."`; assert `"Scope creep: deferred_phase"` and `"Impact:"` appear in Layer 3 section
- **`test_out_of_sprint_task_without_scope_creep_omits_scope_creep_lines`** — `task_data` dict with empty `scope_creep_category`; assert `"Scope creep:"` does not appear in output

`TestTaskToDict` (new, pure):
- **`test_task_to_dict_includes_scope_creep_fields`** — `AllocatedTask` with `scope_creep_category="prerequisite_risk"` and `scope_creep_impact="..."`; assert both keys present in returned dict with correct values

---

### Sub-task C: Warning suppression

No unit test. Verified by running `uv run pytest tests/ -v` after implementation and confirming zero `FutureWarning` lines in the output. The test run baseline currently shows exactly one `FutureWarning` from `layer1.py:6` — the fix should remove it entirely.

---

## Implementation Sequence

Each step is one cohesive commit:

1. **Sub-task C — Warning suppression** (layer1.py, layer2.py, layer3.py): add `import warnings` and `warnings.filterwarnings("ignore", category=FutureWarning, module="google")` to all three layer modules; run `uv run pytest tests/ -v` and verify zero FutureWarning lines
2. **Sub-task A — Fixture header change** (transcript.txt, taxonomy_template.json): change `day: 10` → `day: 2`, `phase: Simulation` → `phase: Discovery`; update taxonomy notes; run `uv run pytest tests/test_fixtures.py -v` and confirm all pass
3. **Sub-task A — Integration test updates** (test_layer3.py): update 5 integration test methods to use `"Discovery", 2`; replace `test_s03_routes_to_out_of_sprint_on_simulation_phase` with `test_s01_routes_to_in_sprint_in_discovery_phase`; add `test_fixture_is_discovery_phase_on_day_two` to test_fixtures.py; run `uv run pytest tests/ -v` (integration tests skip without API key — confirm unit tests all pass)
4. **Sub-task B — Model + Layer 3** (models.py, layer3.py): add `scope_creep_category` and `scope_creep_impact` to `AllocatedTask`; update prompt, extraction, and merge; add 5 new unit tests to test_layer3.py; run `uv run pytest tests/test_layer3.py -v` and confirm all pass
5. **Sub-task B — CLI output** (cli.py): update `_format_proposal` Block 2, `_task_to_dict`, and `_format_explain`; add 5 new unit tests to test_cli.py; run `uv run pytest tests/test_cli.py -v` and confirm all pass; run full `uv run pytest tests/ -v` as final gate

---

## Conventions Applied (from CLAUDE.md)

- Stack: Python with `uv`; stdlib only for warning suppression (`warnings`) — no new dependencies
- Tests: pytest; all new tests in existing test files (`test_layer3.py`, `test_cli.py`, `test_fixtures.py`); integration tests remain guarded by `@pytest.mark.skipif`
- Naming: `snake_case`; English throughout; `scope_creep_category` and `scope_creep_impact` match the field semantics
- No new files — all changes are in-place modifications to existing modules
- No comments on what the code does; `warnings.filterwarnings` is a non-obvious workaround for a specific external library behavior, so a short inline note is appropriate there
- Confidence labels remain `HIGH | MEDIUM | LOW` word labels throughout — scope-creep category adds qualitative type, not confidence

---

## Ready to Code?

- [x] Architecture described — no new files; 5 existing files modified in production code; 3 existing test files extended
- [x] Sub-task A: transcript header change specified (2 lines); taxonomy notes update described; 5 integration test changes enumerated; 1 new fixture test specified
- [x] Sub-task B: 2 new `AllocatedTask` fields specified with type and allowed values; prompt additions spelled out verbatim; extraction contract (`.get(..., "")` default + validation) specified; `_merge_results` pass-through specified; 3 CLI output changes specified with before/after examples; JSON artifact schema updated
- [x] Sub-task C: filter call specified exactly (`module="google"` scoped); placement rationale stated; verification approach stated
- [x] Error handling: `AllocationError` on invalid `scope_creep_category`; existing `_die` pattern unchanged
- [x] Trade-offs documented: plain `str` vs `Enum`, blanket vs scoped filter, body rewrite vs header-only change, filter placement options
- [x] Risks documented: LLM ignoring scope-creep instructions, empty Block 2 in Discovery, filter coverage
- [x] Testing plan: 1 new fixture test + 5 integration test updates (sub-task A); 5 new layer3 unit tests + 6 new CLI unit tests (sub-task B); manual verification (sub-task C) — 12 new tests total
- [x] Implementation sequence: 5 commits, each independently verifiable against tests
- [x] No new library introduced — stdlib `warnings` only
- [x] Backward compatibility: existing mock responses without scope-creep fields default to `""` via `.get(..., "")` — no existing unit test breaks
