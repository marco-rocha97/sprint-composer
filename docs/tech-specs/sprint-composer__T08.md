# Tech Spec: Phase Reasoning Fix — Vocabulary + Discovery Planning Semantics · Order Display — `T08`

> **SPEC:** [`docs/specs/sprint-composer.md`](../specs/sprint-composer.md)
> **Plan:** [`docs/plans/sprint-composer.md`](../plans/sprint-composer.md)
> **Conventions applied:** `CLAUDE.md` (project) · `rules/testing.md` · `rules/anti-patterns.md`
>
> This document details **how** to deliver T08. The **why** lives in the diagnosis below; **what** and **in what order**, in the implementation sequence.

---

## Context and Motivation

Two related bugs visible in the live demo output that an interviewer will catch in seconds.

**Problem A — "Setup phase" is an invented name.**
`KHAL_PHASES` in `layer3.py` defines the four phases as `Discovery`, `Setup`, `Simulation`, `Go-live`. Khal's actual 15-day cycle uses `Configuration` (days 4–7), not `Setup`. The wrong name also appears in the phase compatibility rules embedded in the LLM prompt. Any allocation reasoning that references the second phase will say "Setup" — a name that does not appear in any Khal documentation. A 10-second objection from the interviewer ends the interview.

**Problem B — The Discovery phase has wrong execution semantics.**
Currently the LLM classifies tasks from a Discovery meeting as `"in_sprint"` with reasoning like "fits perfectly within the current Discovery phase for implementation in the Setup phase." This is internally inconsistent: the task is placed in Block 1 (proposed sprint tasks) but the reasoning acknowledges it will be implemented later. The root problem is that the prompt gives the LLM no guidance about what `"in_sprint"` means *during a planning phase*. Discovery (days 1–3) is pure assessment and planning — no feature is implemented during Discovery. The correct frame: the output of a Discovery meeting is the Configuration plan. A task classified as `"in_sprint"` from a Discovery meeting means "accepted into Configuration (days 4–7)", not "executing right now." The Block 1 header and the LLM's reasoning must reflect this.

**Problem C — `Order: 0` appears next to `MoSCoW: Could` for out-of-sprint tasks in `explain` output.**
`dependency_order` is set to `0` for all out-of-sprint tasks as a sentinel meaning "unordered." But `Order: 0` rendered in the explain output looks like "first priority" — the opposite of what `Could` communicates. The fix is to omit or replace `Order:` for out-of-sprint tasks in the explain view. Block 1 of the proposal already omits dependency order from display — this fix brings `explain` into alignment.

---

## Task Scope

- **Behavior delivered:** (A) "Configuration" replaces "Setup" everywhere it appears in `KHAL_PHASES` and the LLM prompt, making the vocabulary consistent with Khal's public schedule; (B) the Layer 3 prompt gains a Discovery-specific instruction stating that `"in_sprint"` during Discovery means "accepted into the Configuration plan" — so allocation reasoning and Block 1's header both reflect "proposed for Configuration (days 4–7)" rather than "executing now in Discovery"; (C) `explain` output for out-of-sprint tasks shows `Order: —` instead of `Order: 0`.
- **SPEC stories/criteria covered:**
  - Demo criterion 3 (out-of-sprint with 15-day-cycle justification — now uses correct phase names)
  - T04 acceptance criterion: "the item lands in 'out of sprint' with a reason that explicitly references Khal's 15-day cycle phase mismatch" — phase name must be correct to satisfy this literally
- **Depends on:** T01–T07 (all fully implemented; this task modifies existing code only)
- **External dependencies:** None — prompt text and CLI output are in-repo strings

---

## Architecture

Three sub-tasks; each touches different files. Sub-task A (vocabulary) is a prerequisite for sub-task B (Discovery semantics) because B adds Discovery-specific text that references "Configuration" by name.

### Sub-task A: Rename "Setup" → "Configuration"

**Files changed:** `src/sprint_composer/layer3.py`.

**Two locations in `layer3.py`:**

1. `KHAL_PHASES` dict — rename the key and update its description:

```python
# Before
"Setup": (
    "Environment setup, core integrations, initial builds, infrastructure "
    "(days 4–7). New feature development and integrations are appropriate."
),

# After
"Configuration": (
    "Environment setup, core integrations, initial builds, infrastructure "
    "(days 4–7). New feature development and integrations are appropriate."
),
```

2. The phase compatibility rules string embedded in `_build_allocation_prompt` — change the bullet:

```
# Before
- Setup (days 4–7): new feature development and core integrations are appropriate

# After
- Configuration (days 4–7): new feature development and core integrations are appropriate
```

**Downstream effect:** `_build_allocation_prompt` raises `AllocationError` if `phase not in KHAL_PHASES`. After the rename, a transcript with `phase: Setup` will fail with a clear named error. The demo fixture uses `phase: Discovery`, so no existing demo path is affected.

---

### Sub-task B: Discovery planning semantics

**Files changed:** `src/sprint_composer/layer3.py`, `src/sprint_composer/cli.py`.

#### `layer3.py` — Discovery-specific instruction in the prompt

In `_build_allocation_prompt`, after the static phase compatibility rules block and before the tasks JSON, add a conditional instruction that fires only when the current phase is `"Discovery"`:

```python
discovery_note = ""
if phase == "Discovery":
    discovery_note = (
        "\nIMPORTANT — PLANNING PHASE SEMANTICS: The current phase is Discovery (days 1–3). "
        "Discovery is a planning phase — no features are implemented during Discovery. "
        "Classify tasks as \"in_sprint\" to mean \"accepted into the Configuration plan (days 4–7)\" "
        "— they will be built during Configuration, not during this Discovery session. "
        "The allocation_reasoning for in-sprint items must say 'Proposed for Configuration (days 4–7)' "
        "rather than implying implementation during Discovery. "
        "A task is out_of_sprint only if it is inappropriate for Configuration (e.g., needs a phase "
        "beyond Configuration, has an unbounded information gap, or introduces scope beyond the "
        "15-day cycle).\n"
    )
```

Insert `{discovery_note}` into the prompt string immediately after the phase compatibility rules block and before `Tasks to allocate`.

The full prompt shape becomes:

```
You are a sprint planner…

Current context:
- Day: {day}
- Phase: {phase}
- Phase description: {phase_description}

Phase compatibility rules:
- Discovery (days 1–3): …
- Configuration (days 4–7): …
- Simulation (days 8–12): …
- Go-live (days 13–15): …
{discovery_note}
Tasks to allocate…
```

#### `cli.py` — Phase-aware Block 1 header in `_format_proposal`

`_format_proposal` already receives `header` (which carries `header.phase`). Update the Block 1 header section:

```python
# Before
lines.append("BLOCK 1: PROPOSED SPRINT TASKS")

# After
if header.phase == "Discovery":
    lines.append("BLOCK 1: PROPOSED FOR CONFIGURATION (Days 4–7)")
else:
    lines.append("BLOCK 1: PROPOSED SPRINT TASKS")
```

No other output blocks change. `_cmd_explain`'s block-name label (`"Proposed sprint tasks"`) is a lookup key, not display copy — leave it unchanged.

---

### Sub-task C: Order display fix for out-of-sprint tasks in `explain`

**File changed:** `src/sprint_composer/cli.py`.

In `_format_explain`, the `Order:` line currently renders unconditionally for all tasks. Replace with a sprint-allocation guard:

```python
# Before
lines.append(f"  Order:      {task_data['dependency_order']}")

# After
if task_data.get("sprint_allocation") == "in_sprint":
    lines.append(f"  Order:      {task_data['dependency_order']}")
else:
    lines.append(f"  Order:      —")
```

`dependency_order` is still serialized in the JSON artifact unchanged — this is a display-only fix.

---

## Contracts

### `KHAL_PHASES` — updated key set

```python
KHAL_PHASES: dict[str, str] = {
    "Discovery": "...",
    "Configuration": "...",   # ← renamed from "Setup"
    "Simulation": "...",
    "Go-live": "...",
}
```

`_build_allocation_prompt` raises `AllocationError("Unrecognized phase: 'X'. Valid phases: Discovery, Configuration, Simulation, Go-live")` for any phase not in this dict. Transcripts using `phase: Setup` will fail with a named error after this change.

### `_build_allocation_prompt` — updated return contract

Function signature unchanged. The returned prompt string:
- Always contains "Configuration (days 4–7)" (never "Setup")
- Contains the Discovery planning-semantics paragraph when and only when `phase == "Discovery"`

### `_format_proposal` output — Block 1 header

| `header.phase` | Block 1 header |
|---|---|
| `"Discovery"` | `BLOCK 1: PROPOSED FOR CONFIGURATION (Days 4–7)` |
| `"Configuration"`, `"Simulation"`, `"Go-live"` | `BLOCK 1: PROPOSED SPRINT TASKS` |

### `_format_explain` output — Order line

| `sprint_allocation` | Order line rendered |
|---|---|
| `"in_sprint"` | `  Order:      <integer>` |
| `"out_of_sprint"` | `  Order:      —` |

JSON artifact: `dependency_order` field unchanged (integer) for all tasks.

---

## Trade-offs and Rejected Alternatives

**Decision: `discovery_note` is a conditional string inserted into the prompt (not a separate prompt path)**
- **Rejected:** Two separate prompt-builder functions — one for Discovery, one for execution phases. Would require a router in `allocate_tasks` and double the prompt surface to maintain.
- **Reason:** The Discovery semantics note is a paragraph addition. A conditional string in one function is the minimum-surface change; the core JSON schema and extraction logic are unchanged.

**Decision: Block 1 header is phase-aware only for Discovery**
- **Rejected:** A general `_next_phase` mapping (Discovery→Configuration, Configuration→Simulation, …) that would make the header always name the "current execution phase." Would add complexity for phases that are already execution phases — in Configuration/Simulation/Go-live, "proposed sprint tasks" is accurate and needs no change.
- **Reason:** Discovery is the only planning phase in Khal's cycle. The special case is exactly one: `if phase == "Discovery"`. Three similar lines is better than a premature abstraction.

**Decision: Replace `Order: 0` with `Order: —` (not omit entirely)**
- **Rejected:** Omit the Order line for out-of-sprint tasks. Omission makes the explain output asymmetric — a reader compares two tasks and wonders why one has no Order field.
- **Reason:** `—` makes the absence intentional and readable without hiding the field. Consistent shape, clear meaning.

**Decision: Discovery note only affects the prompt, not `SprintAllocation` enum or `AllocatedTask` model**
- **Rejected:** Add a `"planning"` allocation type to `SprintAllocation`. Would require updating every consumer: `_merge_results`, JSON serialization, `_format_proposal`, `_format_explain`, `explain` block search, all tests.
- **Reason:** The semantic difference is in *how the human reads Block 1*, not in the underlying data structure. The JSON sibling correctly records `sprint_allocation: "in_sprint"` for tasks accepted into the Configuration plan — that is the accurate machine-readable state. Only the human-facing label changes.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| LLM ignores the Discovery planning note and still writes "implementing in Discovery" in reasoning | Misleading reasoning text in Block 1 | The note uses IMPORTANT and explicit wording; integration test checks that at least one in-sprint task's reasoning references "Configuration" when run on the Discovery fixture |
| LLM over-reads the Discovery note and classifies all tasks as `out_of_sprint` (reasoning: "nothing executes in Discovery") | Block 1 empty in demo | Note explicitly states "in_sprint means accepted into Configuration" and gives the out-of-sprint condition narrowly; risk is low but integration test verifies ≥1 in-sprint task |
| Transcript with `phase: Setup` now fails at Layer 3 instead of producing output | Existing scripts using old vocabulary break | Error message names the valid phases. "Setup" was never a valid phase per Khal's schedule — this is a correct rejection, not a regression |
| `Order: —` for out-of-sprint breaks `explain` output parsing in downstream tooling | Tooling breakage | `dependency_order` in the JSON artifact is unchanged (integer). `Order: —` is display-only in stdout. No current downstream tooling parses explain stdout. |

---

## Testing Plan

### Sub-task A: Vocabulary rename

**`tests/test_layer3.py`** — `TestKhalPhases` class (new):
- **`test_configuration_key_exists`** — assert `"Configuration" in KHAL_PHASES`
- **`test_setup_key_does_not_exist`** — assert `"Setup" not in KHAL_PHASES`
- **`test_configuration_description_mentions_days_4_to_7`** — assert `"4" in KHAL_PHASES["Configuration"]` and `"7" in KHAL_PHASES["Configuration"]`
- **`test_unknown_phase_raises_allocation_error`** — call `_build_allocation_prompt([], "Setup", 5)`; assert `AllocationError` raised and "Setup" appears in the error message

**`tests/test_layer3.py`** — `TestBuildAllocationPrompt` (extend existing):
- **`test_prompt_contains_configuration_not_setup`** — call `_build_allocation_prompt([], "Configuration", 5)`; assert `"Configuration"` in prompt and `"Setup"` not in prompt

### Sub-task B: Discovery planning semantics

**`tests/test_layer3.py`** — `TestBuildAllocationPrompt` (extend):
- **`test_discovery_prompt_includes_planning_semantics`** — call `_build_allocation_prompt([], "Discovery", 2)`; assert `"planning"` or `"Configuration plan"` in prompt and `"allocation_reasoning"` instructions mention "Configuration (days 4–7)"
- **`test_non_discovery_prompt_excludes_planning_note`** — call `_build_allocation_prompt([], "Configuration", 5)`; assert `"PLANNING PHASE SEMANTICS"` not in prompt

**`tests/test_cli.py`** — `TestFormatProposal` (extend existing or new class):
- **`test_block1_header_shows_configuration_when_phase_is_discovery`** — call `_format_proposal` with a mock header where `phase="Discovery"`; assert `"PROPOSED FOR CONFIGURATION (Days 4–7)"` in output and `"PROPOSED SPRINT TASKS"` not in output
- **`test_block1_header_shows_sprint_tasks_when_phase_is_configuration`** — mock header with `phase="Configuration"`; assert `"PROPOSED SPRINT TASKS"` in output

### Sub-task C: Order display fix

**`tests/test_cli.py`** — `TestFormatExplain` (extend existing):
- **`test_out_of_sprint_task_shows_order_dash`** — call `_format_explain` with `task_data` containing `"sprint_allocation": "out_of_sprint"` and `"dependency_order": 0`; assert `"Order:      —"` in output and `"Order:      0"` not in output
- **`test_in_sprint_task_shows_order_integer`** — call `_format_explain` with `task_data` containing `"sprint_allocation": "in_sprint"` and `"dependency_order": 1`; assert `"Order:      1"` in output and `"Order:      —"` not in output

---

## Implementation Sequence

Each step is one cohesive commit:

1. **Sub-task A — Vocabulary rename** (`layer3.py`): rename `"Setup"` → `"Configuration"` in `KHAL_PHASES` dict and in the phase compatibility rules string in `_build_allocation_prompt`; add 4 new tests to `TestKhalPhases` and 1 test to `TestBuildAllocationPrompt`; run `uv run pytest tests/test_layer3.py -v` and confirm all pass
2. **Sub-task B — Discovery planning semantics** (`layer3.py`, `cli.py`): add `discovery_note` conditional to `_build_allocation_prompt`; update Block 1 header in `_format_proposal` to be phase-aware; add 2 prompt tests to `test_layer3.py` and 2 header tests to `test_cli.py`; run `uv run pytest tests/ -v`
3. **Sub-task C — Order display fix** (`cli.py`): replace unconditional `Order:` line with sprint-allocation guard in `_format_explain`; add 2 tests to `TestFormatExplain`; run `uv run pytest tests/test_cli.py -v`; run full `uv run pytest tests/ -v` as final gate

---

## Conventions Applied (from CLAUDE.md)

- No new files — all changes are in-place modifications to existing modules
- No new dependencies — prompt text and display strings are in-repo
- No comments on what the code does; the `discovery_note` is a non-obvious domain constraint (Discovery is a planning phase, not execution), so a short inline comment is appropriate where it is conditionally constructed
- Tests: pytest; all new tests in existing test files (`test_layer3.py`, `test_cli.py`)
- Integration tests remain guarded by `@pytest.mark.skipif` — only unit tests are added here
- English throughout; Khal phase names match Khal's public schedule exactly

---

## Ready to Code?

- [x] Architecture described — no new files; 2 production files modified; 2 test files extended
- [x] Sub-task A: both locations of "Setup" in `layer3.py` identified (KHAL_PHASES key + prompt string); 5 new unit tests specified
- [x] Sub-task B: exact insertion point for `discovery_note` described; conditional logic spelled out; Block 1 header guard specified with before/after; 4 new unit tests specified
- [x] Sub-task C: exact line in `_format_explain` identified (unconditional `dependency_order` render); guard condition specified; JSON artifact unchanged; 2 new unit tests specified
- [x] Contracts: `KHAL_PHASES` key set, prompt return contract, Block 1 header table, Order line table — all documented
- [x] Error handling: `AllocationError` on unknown phase (including now-invalid "Setup") — existing mechanism, no change needed
- [x] Trade-offs documented: single prompt path vs. two builders; Discovery-only special case vs. general next-phase mapping; `—` vs. omit for Order
- [x] Risks documented: LLM ignoring Discovery note, LLM over-reading and emptying Block 1, legacy "Setup" transcripts, downstream tooling
- [x] Testing plan: 5 new layer3 unit tests + 4 new CLI unit tests — 9 new tests total
- [x] Implementation sequence: 3 commits, each independently verifiable
- [x] Backward compatibility: JSON `dependency_order` field unchanged; `explain` display is the only consumer of the Order line
