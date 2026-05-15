# Tech Spec: Layer 3 — Priority & Allocation — `T04`

> **SPEC:** [`docs/specs/sprint-composer.md`](../specs/sprint-composer.md)
> **Plan:** [`docs/plans/sprint-composer.md`](../plans/sprint-composer.md) — task `T04`
> **Conventions applied:** `CLAUDE.md` (project) · `rules/dependencies.md` · `rules/testing.md` · `rules/anti-patterns.md`
>
> This document details **how** to deliver T04. The **why** lives in the SPEC; **what** and **in what order**, in the Plan.

---

## Task Scope

- **Behavior delivered:** For every enriched request from Layer 2, determine (a) whether it belongs in the current sprint or "out of sprint" based on Khal's 15-day-cycle phase, (b) its MoSCoW classification and confidence, (c) its ordering relative to other tasks via dependency detection, and (d) whether signals are sufficient to classify — if not, flag as `"needs Lead decision"` rather than guessing.
- **SPEC stories/criteria covered:**
  - *"Push an out-of-phase request out of the current sprint"*
  - *"Prioritize a blocking task above customer-stated preference"*
  - *"Refuse to classify confidently when signals are insufficient"*
  - Demo criterion 3 (at least one item in "out of sprint" with a 15-day-cycle reason — satisfied by S03 / admin reporting dashboard)
- **Depends on:** T03 (Layer 2 — `Layer2Result` + `EnrichedSegment` contracts)
- **External dependencies:** Gemini API (already in deps; used for a single batch allocation call)

---

## Architecture

- **General approach:** `layer3.py` is a single-pass allocation layer. It sends all enriched segments in one batch Gemini call (rather than N per-segment calls) so the model can reason about cross-task dependencies when ordering. The response is then parsed and post-processed in pure Python to build `Layer3Result`. Phase descriptions for Khal's 15-day cycle are hardcoded in `layer3.py` as a `KHAL_PHASES` constant — the same pattern used for inline constants in `layer2.py`.
- **Why batch instead of per-segment:** Cross-task dependency detection (e.g. "SSO must precede nursing-portal consolidation") requires seeing all tasks at once. A per-segment approach would either miss cross-task relationships or require a second ordering pass with its own Gemini call. The batch approach delivers both allocation and ordering in one round-trip.
- **Affected modules:**
  - `src/sprint_composer/models.py` — new dataclasses added (no existing classes touched)
  - `src/sprint_composer/layer3.py` — new module
- **New files:**
  - `src/sprint_composer/layer3.py` — allocation logic
  - `tests/test_layer3.py` — unit + integration tests
- **Reused patterns:**
  - `_GeneratorProtocol` + `_GenerateResponse` protocol from `layer1.py:17–23` (re-declared in `layer3.py` — no shared import to avoid coupling)
  - `_build_default_client()` pattern from `layer1.py:88–99`
  - `MockGeminiClient` pattern from `tests/test_layer1.py:12–22`
  - Markdown-wrapped JSON extraction (```` ```json ... ``` ````) from `layer2.py`

> **Decision source:** CLAUDE.md (stack: Python/uv/pytest/Gemini), existing patterns in `layer1.py` and `layer2.py`, user confirmation.

---

## Contracts

### Internal interfaces

#### New models (added to `src/sprint_composer/models.py`)

```python
class MoSCoW(str, Enum):
    MUST = "Must"
    SHOULD = "Should"
    COULD = "Could"
    WONT = "Won't"


class SprintAllocation(str, Enum):
    IN_SPRINT = "in_sprint"
    OUT_OF_SPRINT = "out_of_sprint"


@dataclass
class AllocatedTask:
    # Preserved verbatim from EnrichedSegment — never modified
    segment_id: str
    excerpt: str
    type: SegmentType               # firm_request or latent_request (only L2-eligible types)
    l1_confidence: Confidence       # Layer 1 classification confidence
    l1_reasoning: str               # Layer 1 classification reasoning
    reference_match: ReferenceMatch | None
    effort: str                     # "<N> days" or exactly "estimate not available"
    l2_confidence: Confidence       # Layer 2 enrichment confidence
    blockers: list[str]             # from reference entry, or [] when no match
    gap_questions: list[str]        # [] when matched; 3–4 questions when no match
    enrichment_reasoning: str       # Layer 2 enrichment reasoning

    # Layer 3 allocation results
    moscow: MoSCoW
    sprint_allocation: SprintAllocation
    allocation_confidence: Confidence
    dependency_order: int           # 1-indexed position for in-sprint tasks; 0 for out_of_sprint
    needs_lead_decision: bool
    lead_decision_reason: str       # "" when needs_lead_decision is False
    allocation_reasoning: str       # one sentence — why this MoSCoW and allocation


@dataclass
class Layer3Result:
    in_sprint: list[AllocatedTask]      # ordered by dependency_order ascending (1, 2, 3, ...)
    out_of_sprint: list[AllocatedTask]  # ordered by segment_id ascending
```

#### `allocate_tasks` — public entry point

```python
# src/sprint_composer/layer3.py

def allocate_tasks(
    layer2_result: Layer2Result,
    phase: str,
    day: int,
    client: _GeneratorProtocol | None = None,
) -> Layer3Result:
    """
    Allocate every enriched request to in-sprint or out-of-sprint.

    layer2_result  — output from Layer 2 (all L2-eligible enriched segments)
    phase          — current sprint phase, e.g. "Simulation" (from transcript header)
    day            — current sprint day, e.g. 10 (from transcript header)
    client         — injectable Gemini client (testing); built from env if None

    Returns Layer3Result with in_sprint ordered by dependency and out_of_sprint
    ordered by segment_id.
    Raises AllocationError if phase is unrecognized, Gemini response is unparseable,
    or the response omits or adds segment_ids not present in the input.
    Raises EnvironmentError if GEMINI_API_KEY is not set and no client is injected.
    """
```

### Private functions in `layer3.py`

```
KHAL_PHASES: dict[str, str]
    Maps phase name → description used in the Gemini prompt.
    Keys: "Discovery", "Setup", "Simulation", "Go-live".

_build_default_client() -> _GeneratorProtocol
    Builds genai.GenerativeModel("gemini-3.1-flash-lite") from GEMINI_API_KEY env var.
    Raises EnvironmentError if the var is unset.

_build_allocation_prompt(enriched: list[EnrichedSegment], phase: str, day: int) -> str
    Constructs the batch prompt with phase context + all enriched tasks as JSON.
    Raises AllocationError if phase not in KHAL_PHASES.

_extract_allocation(
    response_text: str,
    expected_ids: list[str],
) -> tuple[list[dict], list[dict]]
    Parses Gemini's JSON → (allocations_list, dependency_order_list).
    Strips markdown wrapper if present (same pattern as layer2.py).
    Raises AllocationError if:
      - JSON is unparseable
      - "allocations" key is missing
      - Any segment_id in the response is not in expected_ids
      - Any segment_id in expected_ids is absent from the response
      - Any "moscow", "sprint_allocation", or "allocation_confidence" value is invalid

_merge_results(
    enriched: list[EnrichedSegment],
    allocations: list[dict],
    dependency_order: list[dict],
) -> Layer3Result
    Constructs one AllocatedTask per EnrichedSegment.
    Sets dependency_order=0 for out_of_sprint tasks.
    For in_sprint tasks: uses position from dependency_order list if present;
    falls back to input order (segment_id order) for tasks not mentioned.
    Returns Layer3Result with in_sprint sorted ascending by dependency_order,
    out_of_sprint sorted ascending by segment_id.
```

### `AllocationError`

```python
class AllocationError(Exception):
    """Raised when Gemini response is unparseable or structurally invalid."""
```

---

## Data Model

### `AllocatedTask` field rules

| Field | Type | Notes |
|---|---|---|
| `segment_id` | `str` | Copied verbatim from `EnrichedSegment` |
| `excerpt` | `str` | Copied verbatim — never modified |
| `type` | `SegmentType` | `firm_request` or `latent_request` only |
| `l1_confidence` | `Confidence` | Copied from `EnrichedSegment.l1_confidence` |
| `l1_reasoning` | `str` | Copied from `EnrichedSegment.l1_reasoning` |
| `reference_match` | `ReferenceMatch \| None` | Copied from `EnrichedSegment.reference_match` |
| `effort` | `str` | Copied from `EnrichedSegment.effort` |
| `l2_confidence` | `Confidence` | Copied from `EnrichedSegment.confidence` |
| `blockers` | `list[str]` | Copied from `EnrichedSegment.blockers` |
| `gap_questions` | `list[str]` | Copied from `EnrichedSegment.gap_questions` |
| `enrichment_reasoning` | `str` | Copied from `EnrichedSegment.enrichment_reasoning` |
| `moscow` | `MoSCoW` | Gemini output: `"Must"`, `"Should"`, `"Could"`, or `"Won't"` |
| `sprint_allocation` | `SprintAllocation` | Gemini output: `"in_sprint"` or `"out_of_sprint"` |
| `allocation_confidence` | `Confidence` | Gemini output: `HIGH`, `MEDIUM`, or `LOW` |
| `dependency_order` | `int` | Gemini output (position); `0` for out_of_sprint tasks |
| `needs_lead_decision` | `bool` | `True` when MoSCoW cannot be confidently assigned |
| `lead_decision_reason` | `str` | Non-empty when `needs_lead_decision` is `True`; `""` otherwise |
| `allocation_reasoning` | `str` | Gemini output: one sentence |

### `Layer3Result` invariants

- `in_sprint` is sorted by `dependency_order` ascending; all values ≥ 1
- `out_of_sprint` is sorted by `segment_id` ascending; all `dependency_order` values are 0
- Every `EnrichedSegment` in `layer2_result.enriched` appears in exactly one of the two lists

---

## External Integrations

- **Partner:** Google Gemini (via `google-generativeai>=0.7`, already installed)
- **Used for:** one batch allocation call per `allocate_tasks` invocation
- **Model:** `gemini-3.1-flash-lite` (same as Layer 1 and Layer 2)
- **Authentication:** `GEMINI_API_KEY` env var (same as Layer 1 and Layer 2)
- **Rate limits / retry:** no retry in v0 (consistent with Layers 1 and 2)
- **Mock contract for tests:** `MockGeminiClient` — same interface as `test_layer1.py` and `test_layer2.py`; returns one pre-set JSON string per `generate_content()` call

### Prompt contract (batch allocation)

**`KHAL_PHASES` constant (hardcoded in `layer3.py`):**

```python
KHAL_PHASES: dict[str, str] = {
    "Discovery": (
        "Requirements gathering, scoping, architecture decisions, stakeholder alignment "
        "(days 1–3). New features, new integrations, and major scope items are all appropriate."
    ),
    "Setup": (
        "Environment setup, core integrations, initial builds, infrastructure "
        "(days 4–7). New feature development and integrations are appropriate."
    ),
    "Simulation": (
        "UAT testing, bug fixes, feature validation with real data, refinements to existing "
        "features (days 8–12). New scope or new feature development is INCOMPATIBLE with "
        "this phase — only work on features already in scope belongs here."
    ),
    "Go-live": (
        "Production deployment, training, cutover, go-live support (days 13–15). "
        "Only critical production fixes are appropriate; new features are out-of-scope."
    ),
}
```

**Prompt template:**

```
You are a sprint planner for a software delivery team operating on Khal's 15-day delivery cycle.

Current context:
- Day: {day}
- Phase: {phase}
- Phase description: {phase_description}

Phase compatibility rules:
- Discovery (days 1–3): new features, new integrations, and major scope items are appropriate
- Setup (days 4–7): new feature development and core integrations are appropriate
- Simulation (days 8–12): UAT testing and refinements to EXISTING features only — new scope is incompatible
- Go-live (days 13–15): only critical production fixes are appropriate; new features are out-of-scope

Tasks to allocate (each enriched with effort and blockers from historical data):
{tasks_json}

For each task, determine:
1. sprint_allocation: "in_sprint" if compatible with the current phase; "out_of_sprint" if it introduces new scope incompatible with {phase}
2. moscow: one of "Must", "Should", "Could", "Won't" — based on urgency, blockers, and phase fit
3. allocation_confidence: "HIGH", "MEDIUM", or "LOW" — how certain you are
4. needs_lead_decision: true if MoSCoW level cannot be confidently assigned from available signals; false otherwise
5. lead_decision_reason: the specific reason if needs_lead_decision is true; "" (empty string) otherwise
6. allocation_reasoning: one sentence — why this MoSCoW and allocation

Also identify cross-task dependencies: if Task X must be completed before Task Y, include this in dependency_order.

Return ONLY a valid JSON object (no markdown, no explanation):
{
  "allocations": [
    {
      "segment_id": "<id>",
      "sprint_allocation": "in_sprint" | "out_of_sprint",
      "moscow": "Must" | "Should" | "Could" | "Won't",
      "allocation_confidence": "HIGH" | "MEDIUM" | "LOW",
      "needs_lead_decision": true | false,
      "lead_decision_reason": "<reason or empty string>",
      "allocation_reasoning": "<one sentence>"
    }
  ],
  "dependency_order": [
    {"segment_id": "<id>", "position": <int>}
  ]
}
```

**`tasks_json` format** (constructed by `_build_allocation_prompt`):

```json
[
  {
    "segment_id": "S01",
    "type": "firm_request",
    "excerpt": "We need to implement Single Sign-On...",
    "effort": "5 days",
    "blockers": ["Identity provider configuration", "Network security group rules"],
    "gap_questions": []
  },
  ...
]
```

**Expected response:**

```json
{
  "allocations": [
    {
      "segment_id": "S01",
      "sprint_allocation": "in_sprint",
      "moscow": "Must",
      "allocation_confidence": "HIGH",
      "needs_lead_decision": false,
      "lead_decision_reason": "",
      "allocation_reasoning": "SSO is a prerequisite for all authenticated workflows in scope for Simulation."
    },
    {
      "segment_id": "S03",
      "sprint_allocation": "out_of_sprint",
      "moscow": "Should",
      "allocation_confidence": "HIGH",
      "needs_lead_decision": false,
      "lead_decision_reason": "",
      "allocation_reasoning": "Brand-new reporting dashboard is new scope incompatible with Simulation phase."
    }
  ],
  "dependency_order": [
    {"segment_id": "S01", "position": 1},
    {"segment_id": "S02", "position": 3}
  ]
}
```

**Validation rules applied in `_extract_allocation`:**

- Every `segment_id` in `"allocations"` must appear in `expected_ids` — raises `AllocationError` otherwise
- Every id in `expected_ids` must appear in `"allocations"` — raises `AllocationError` for missing tasks
- `"moscow"` must be one of `"Must"`, `"Should"`, `"Could"`, `"Won't"` — raises `AllocationError` otherwise
- `"sprint_allocation"` must be one of `"in_sprint"`, `"out_of_sprint"` — raises `AllocationError` otherwise
- `"allocation_confidence"` must be one of `"HIGH"`, `"MEDIUM"`, `"LOW"` — raises `AllocationError` otherwise
- `"dependency_order"` may be absent or empty — treated as empty list (graceful; in-sprint tasks fall back to segment_id order)

---

## Trade-offs and Rejected Alternatives

**Decision: single batch Gemini call (not N per-segment calls)**
- **Rejected alternative:** One Gemini call per `EnrichedSegment`, as in Layer 1.
- **Reason:** Cross-task dependency ordering (e.g. "SSO must precede nursing-portal consolidation") requires the model to see all tasks simultaneously. A per-segment approach either misses cross-task relationships or requires a second ordering pass — both are more complex than a single batch call.
- **Source:** user decision (confirmed); architectural requirement from SPEC scenario *"Prioritize a blocking task above customer-stated preference"*.

**Decision: `AllocationError` raised on parse failure (not graceful fallback)**
- **Rejected alternative:** Fall back silently to some default allocation (e.g. all tasks → in_sprint, MoSCoW → Should) when Gemini's response is unparseable.
- **Reason:** Unlike Layer 2's gap-question fallback (secondary output that degrades gracefully), allocation is the primary output of Layer 3. A silent fallback would produce a structurally valid but semantically empty proposal — worse than a named error the CLI can surface. The SPEC requires named, actionable errors.
- **Source:** SPEC Experience Design — *"Error: named, actionable errors … never raw stack traces."*; `rules/anti-patterns.md`.

**Decision: `AllocatedTask` embeds all L1/L2 fields (flat struct, not a reference to `EnrichedSegment`)**
- **Rejected alternative:** `AllocatedTask` holds a reference to `EnrichedSegment` and adds only the L3 fields.
- **Reason:** The `explain` command (T06) needs a single self-contained record per task — the full audit trail from excerpt through L1 classification, L2 enrichment, and L3 allocation. A flat struct avoids nested access patterns and is consistent with how `EnrichedSegment` embeds L1 fields.
- **Source:** `rules/architecture.md` (one file, one responsibility); SPEC auditability requirement; precedent set by `EnrichedSegment` embedding `ClassifiedSegment` fields.

**Decision: `dependency_order` missing from response is not an error — falls back to segment_id order**
- **Rejected alternative:** Raise `AllocationError` if `dependency_order` is absent from the Gemini response.
- **Reason:** `dependency_order` is advisory. If Gemini doesn't detect cross-task dependencies (e.g. no blocking relationship exists in the input), the absence is valid. Input-order is a safe default. Making it required would cause spurious errors on transcripts with no inter-task dependencies.
- **Source:** SPEC *"Declare ignorance"* principle — the agent should not fabricate ordering when there is no real dependency to declare.

**Decision: phase descriptions hardcoded in `KHAL_PHASES` (not read from a config file)**
- **Rejected alternative:** Store phase definitions in a JSON config file loaded at runtime.
- **Reason:** Phase definitions are stable domain knowledge for v0. Loading them from a file adds I/O, a `FileNotFoundError` path, and a dependency without benefit. If phase definitions change for v1, the constant can be extracted then.
- **Source:** `rules/anti-patterns.md` (no speculative abstractions); user confirmation that phase definitions are accurate.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Gemini returns a `segment_id` not in the input | `AllocationError` before any result is built | Validate all returned ids against `expected_ids` in `_extract_allocation`; raise with the offending id named |
| Gemini omits a task from `allocations` | Missing allocation for a segment | Validate all `expected_ids` appear in response; raise `AllocationError` with the missing id named |
| Gemini returns invalid enum value (e.g. `"MUST"` instead of `"Must"`) | `AllocationError` | Case-insensitive normalization attempted first; raise if still invalid after normalization |
| Gemini `dependency_order` positions conflict (two tasks claim position 1) | Ambiguous in-sprint ordering | Stable sort: first occurrence by position wins; second is shifted to position+1; no error raised |
| Unrecognized phase name passed to `allocate_tasks` | `AllocationError` before Gemini call | Check `phase in KHAL_PHASES` at the top of `_build_allocation_prompt`; raise with the unrecognized value and the valid keys |
| Prompt too long for Gemini context window | Gemini API error | v0 demo has 5 enriched segments; well within limits. Risk is real only for large transcripts (v1 concern). |

---

## Testing Plan

File: `tests/test_layer3.py`

### `TestBuildAllocationPrompt` — unit (pure Python, no I/O)

- Phase name and description appear in the prompt string
- All input `segment_id`s appear in the tasks JSON block
- `effort`, `blockers`, and `gap_questions` for each segment appear in the prompt
- Unknown phase raises `AllocationError` with the unrecognized value in the message

### `TestExtractAllocation` — unit (no I/O)

- Valid JSON response parsed into `(allocations_list, dependency_order_list)`
- Markdown-wrapped JSON (` ```json ... ``` `) parsed correctly (same as layer2.py)
- Missing `"allocations"` key → `AllocationError`
- `segment_id` in response not in `expected_ids` → `AllocationError` naming the offending id
- `segment_id` in `expected_ids` absent from response → `AllocationError` naming the missing id
- Invalid `"moscow"` value → `AllocationError` naming the invalid value
- Invalid `"sprint_allocation"` value → `AllocationError`
- Absent `"dependency_order"` key → returns empty list (no error)

### `TestMergeResults` — unit (pure Python, no I/O)

- `out_of_sprint` tasks have `dependency_order == 0`
- `in_sprint` tasks sorted ascending by `dependency_order`
- In-sprint tasks not in `dependency_order` list are appended after positioned tasks in segment_id order
- Duplicate `position` values in `dependency_order` → stable sort (first occurrence wins)
- All L1/L2 fields on `AllocatedTask` match corresponding fields on the source `EnrichedSegment`
- `needs_lead_decision=True` → `lead_decision_reason` is non-empty string
- `needs_lead_decision=False` → `lead_decision_reason == ""`

### `TestAllocateTasks` — unit (MockGeminiClient)

- In-sprint task: `AllocatedTask.sprint_allocation == SprintAllocation.IN_SPRINT`, `dependency_order >= 1`
- Out-of-sprint task: `AllocatedTask.sprint_allocation == SprintAllocation.OUT_OF_SPRINT`, `dependency_order == 0`
- `needs_lead_decision=True`: `lead_decision_reason` is non-empty
- `needs_lead_decision=False`: `lead_decision_reason == ""`
- All `EnrichedSegment` fields preserved verbatim on `AllocatedTask` (no modification)
- Markdown-wrapped JSON from `MockGeminiClient` parsed correctly

### `TestIntegration` — skipped unless `GEMINI_API_KEY` is set

```python
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
class TestIntegration:
```

- S03 (admin dashboard, day 10, Simulation) → `sprint_allocation == "out_of_sprint"`; `allocation_reasoning` references Khal's 15-day cycle or Simulation phase (demo criterion 3)
- S01 (SSO) → `sprint_allocation == "in_sprint"`, `moscow == "Must"` (critical integration; required before auth-dependent features)
- At least one task has `needs_lead_decision == True` or `allocation_confidence == "LOW"` (demonstrating refusal to guess)
- `Layer3Result.in_sprint` is non-empty and sorted with lowest `dependency_order` first
- Every `EnrichedSegment.segment_id` from the Layer 2 fixture output appears in exactly one of `in_sprint` or `out_of_sprint`

> **Framework/pattern:** pytest, `MockGeminiClient` from `test_layer1.py`. Source: existing pattern in `tests/test_layer1.py:12–22` and `tests/test_layer2.py`.

---

## Implementation Sequence

Each step is one cohesive commit:

1. **Add new dataclasses to `models.py`** — `MoSCoW`, `SprintAllocation`, `AllocatedTask`, `Layer3Result`; run `uv run mypy src/` to confirm no type errors
2. **Implement `KHAL_PHASES`, `_build_allocation_prompt`, and `_extract_allocation`** in `layer3.py`; write `TestBuildAllocationPrompt` and `TestExtractAllocation` — all pass without any Gemini dependency
3. **Implement `_merge_results`**; write `TestMergeResults` — all pass without any Gemini dependency
4. **Implement `allocate_tasks` and `_build_default_client`**; write `TestAllocateTasks` with `MockGeminiClient`; run `uv run pytest tests/test_layer3.py -v` — all pass
5. **Write `TestIntegration`** (guarded by `GEMINI_API_KEY`); run with real key to confirm S03 → `out_of_sprint`, S01 → `Must`, and at least one `needs_lead_decision == True`

---

## Conventions Applied (from CLAUDE.md)

- Stack: Python with `uv`; `google-generativeai>=0.7` (no new dependency added)
- Tests: `pytest`, test files mirror `src/` structure under `tests/`; integration tests guarded by `@pytest.mark.skipif`
- LLM client: injectable `_GeneratorProtocol` for testability; `_build_default_client()` from env var
- Naming: English, `snake_case` for functions, `PascalCase` for classes
- No comments explaining *what* — only *why* where non-obvious
- Confidence: always `HIGH | MEDIUM | LOW` word labels (never color-only per SPEC)
- Error type: `AllocationError` for prompt/response failures (consistent with `ClassificationError` in Layer 1 and `EnrichmentError` in Layer 2)

---

## Ready to Code?

- [x] Architecture described with modules and new files named
- [x] Contracts (internal interfaces, data model, Gemini prompt + response + validation) in final form
- [x] `AllocatedTask` field table with per-field rules (source, type, invariants)
- [x] `KHAL_PHASES` constant spelled out verbatim (drives the core allocation logic)
- [x] Non-trivial trade-offs have a rejected alternative documented (4 decisions)
- [x] Known risks listed with mitigations (5 risks)
- [x] Testing plan covers happy path + at least 2 error cases per class (invalid ids, missing tasks, bad enums, absent dependency_order)
- [x] Implementation sequence is executable without clarification questions (5 commits)
- [x] No new library introduced (Gemini already in deps; all post-processing is pure Python)
- [x] CLAUDE.md conventions cited and respected
