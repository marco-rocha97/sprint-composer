# Tech Spec: Layer 2 — Enrichment + Missing-Info Detection — `T03`

> **SPEC:** [`docs/specs/sprint-composer.md`](../specs/sprint-composer.md)
> **Plan:** [`docs/plans/sprint-composer.md`](../plans/sprint-composer.md) — task `T03`
> **Conventions applied:** `CLAUDE.md` (project) · `rules/dependencies.md` · `rules/testing.md` · `rules/anti-patterns.md`
>
> This document details **how** to deliver T03. The **why** lives in the SPEC; **what** and **in what order**, in the Plan.

---

## Task Scope

- **Behavior delivered:** For every `firm_request` or `latent_request` from Layer 1, search the reference bank for a similar past task; if a close match exists, enrich the item with that task's recorded real effort and known blockers; if no close match exists, mark the item `"estimate not available"` and generate concrete gap questions via Gemini. The effort field is never fabricated.
- **SPEC stories/criteria covered:**
  - *"Enrich a request with historical reference when one exists"*
  - *"Flag a request when no historical reference is available"*
  - *"Never invent an effort estimate"*
  - Demo criterion 2 (at least one LOW-confidence item with a named gap — satisfied by S04 / IoT glucose monitor)
- **Depends on:** T01 (fixtures — reference bank at `fixtures/reference_bank.json`), T02 (Layer 1 — `Layer1Result` + `ClassifiedSegment` contracts)
- **External dependencies:** Gemini API (already in deps; used for gap-question generation only, not for matching)

---

## Architecture

- **General approach:** `layer2.py` is a pure enrichment pass — it consumes a `Layer1Result`, filters to L2-eligible segments via the existing `for_layer2()` method, scores each segment against the reference bank using keyword overlap, and returns a `Layer2Result`. Gemini is called only when keyword matching yields no result, to generate domain-specific gap questions. Everything else is deterministic Python.
- **Affected modules:**
  - `src/sprint_composer/models.py` — new dataclasses added (no existing classes touched)
  - `src/sprint_composer/layer2.py` — new module (analogous to `layer1.py`)
- **New files:**
  - `src/sprint_composer/layer2.py` — enrichment logic
  - `tests/test_layer2.py` — unit + integration tests
- **Reused patterns:**
  - `_GeneratorProtocol` + `_GenerateResponse` pattern from `layer1.py:17–23` (identical protocol, re-declared in `layer2.py` — no shared import to avoid coupling)
  - `_build_default_client()` pattern from `layer1.py:88–99`
  - `MockGeminiClient` pattern from `tests/test_layer1.py:12–22`
  - `Path(__file__).parent.parent / "fixtures"` fixture path resolution from `tests/test_layer1.py:26–28`

> **Decision source:** CLAUDE.md (stack: Python/uv/pytest/Gemini), existing patterns in `layer1.py` and `test_layer1.py`.

---

## Contracts

### Internal interfaces

#### New models (added to `src/sprint_composer/models.py`)

```python
@dataclass
class ReferenceMatch:
    task_id: str            # e.g. "sso-ldap-integration"
    task_name: str          # e.g. "Single Sign-On via LDAP/Active Directory"
    project_id: str         # e.g. "retail-loyalty-integration"
    project_name: str       # e.g. "Retail Loyalty Program Digital Integration"
    effort_days: int        # recorded real effort from the reference bank
    effort_confidence: Confidence  # HIGH/MEDIUM/LOW from the reference bank entry
    blockers: list[str]     # typical known blockers for this task type
    notes: str              # context from the reference bank entry


@dataclass
class EnrichedSegment:
    # Preserved verbatim from Layer 1 — never modified
    segment_id: str
    excerpt: str
    type: SegmentType           # firm_request or latent_request (only)
    l1_confidence: Confidence   # Layer 1 classification confidence
    l1_reasoning: str           # Layer 1 classification reasoning

    # Layer 2 enrichment output
    reference_match: ReferenceMatch | None  # None if no match found
    effort: str          # "<N> days" from reference, or exactly "estimate not available"
    confidence: Confidence  # reference's effort_confidence, or LOW when no match
    blockers: list[str]  # from reference entry, or [] when no match
    gap_questions: list[str]   # [] when match found; 3–4 Gemini questions when no match
    enrichment_reasoning: str  # one sentence — why this confidence and effort value


@dataclass
class Layer2Result:
    enriched: list[EnrichedSegment]
```

#### `enrich_segments` — public entry point

```python
# src/sprint_composer/layer2.py

def enrich_segments(
    layer1_result: Layer1Result,
    bank_path: Path | None = None,
    client: _GeneratorProtocol | None = None,
) -> Layer2Result:
    """
    Enrich each L2-eligible ClassifiedSegment against the reference bank.

    layer1_result  — output from Layer 1; only firm/latent segments are processed
    bank_path      — path to reference_bank.json; defaults to fixtures/reference_bank.json
    client         — injectable Gemini client (testing); built from env if None

    Returns Layer2Result with one EnrichedSegment per L2-eligible input segment.
    Raises EnrichmentError if the bank file is missing or structurally invalid.
    Raises EnvironmentError if GEMINI_API_KEY is not set and a no-match segment
    requires gap-question generation but no client is injected.
    """
```

### Private functions in `layer2.py`

```
_load_reference_bank(path: Path) -> dict
    Reads and parses reference_bank.json.
    Raises EnrichmentError with named message if file is missing or not valid JSON.

_score_task(excerpt: str, keywords: list[str]) -> int
    Case-insensitive substring count: how many keywords appear in the excerpt.
    Pure function, no I/O, no side effects.

_find_best_match(excerpt: str, bank: dict) -> ReferenceMatch | None
    Scores every task in every project; returns the ReferenceMatch with highest
    score if score > 0, else None. Tie-breaking: first project, first task wins
    (deterministic for demo fixtures).

_build_gap_questions_prompt(excerpt: str) -> str
    Returns the prompt string for Gemini gap-question generation.

_extract_gap_questions(response_text: str) -> list[str]
    Parses Gemini's JSON response {"questions": ["...", ...]}.
    On parse failure, returns a 3-item generic fallback list (never raises).

_enrich_segment(
    segment: ClassifiedSegment,
    bank: dict,
    client: _GeneratorProtocol,
) -> EnrichedSegment
    Orchestrates match + enrichment or no-match + gap-question generation for one segment.
```

### `EnrichmentError`

```python
class EnrichmentError(Exception):
    """Raised when the reference bank cannot be loaded or is structurally invalid."""
```

---

## Data Model

### `EnrichedSegment` field rules

| Field | Type | When match found | When no match |
|---|---|---|---|
| `reference_match` | `ReferenceMatch \| None` | populated | `None` |
| `effort` | `str` | `"<N> days"` (e.g. `"5 days"`) | exactly `"estimate not available"` |
| `confidence` | `Confidence` | reference's `effort_confidence` (HIGH or MEDIUM) | `LOW` |
| `blockers` | `list[str]` | from reference entry | `[]` |
| `gap_questions` | `list[str]` | `[]` | 3–4 Gemini-generated questions |
| `enrichment_reasoning` | `str` | `"Matched '<task_name>' from <project_name> (<N> keyword(s)); effort_confidence=<X> from reference."` | `"No reference match; gap questions generated to unlock estimation."` |

### Reference bank schema (per T01 fixture)

Each task in `reference_bank.json` must have:

| Field | Type | Notes |
|---|---|---|
| `id` | `str` | kebab-case, unique within project |
| `name` | `str` | human-readable |
| `keywords` | `list[str]` | lowercase terms matched against segment excerpts |
| `effort_days` | `int` | recorded real effort |
| `effort_confidence` | `str` | `"HIGH"` or `"MEDIUM"` (or `"LOW"`) |
| `blockers` | `list[str]` | typical known blockers |
| `notes` | `str` | optional context (may be empty string) |

---

## External Integrations

- **Partner:** Google Gemini (via `google-generativeai>=0.7`, already installed)
- **Used for:** gap-question generation **only** (one call per no-match segment; zero calls when every segment has a match)
- **Model:** `gemini-3.1-flash-lite` (same as Layer 1)
- **Authentication:** `GEMINI_API_KEY` env var (same as Layer 1; already in `.env.example`)
- **Rate limits / retry:** no retry in v0 (consistent with Layer 1); single call per no-match segment
- **Mock contract for tests:** `MockGeminiClient` — same interface as in `test_layer1.py`; returns a single pre-set JSON string per `generate_content()` call

### Prompt contract (gap questions)

**Prompt template:**
```
You are an estimation advisor for a software delivery team.

The following transcript request has no historical reference in our task bank:
"""
{excerpt}
"""

Generate 3 to 4 concrete questions that would need to be answered before
an effort estimate can be made for this request. Focus on technical and
delivery unknowns specific to this request.

Return ONLY a valid JSON object (no markdown, no explanation):
{"questions": ["<question 1>", "<question 2>", ...]}
```

**Expected response:**
```json
{"questions": ["What is the vendor API specification?", "..."]}
```

**Parse failure fallback** (no exception raised — pipeline must not fail for this):
```python
[
    "What is the technical specification or API documentation for this request?",
    "Are there vendor SDK or integration guides available?",
    "What are the acceptance criteria for this to be considered complete?",
]
```

---

## Trade-offs and Rejected Alternatives

**Decision: keyword overlap for matching (not Gemini-based matching)**
- **Rejected alternative:** Send segment + reference bank to Gemini and ask it to select the best-matching task.
- **Reason:** Non-deterministic, adds 1 API call per enrichable segment (5 calls for the demo), makes unit tests require mocks for the matching step itself. The demo transcript's segments are explicit and the reference bank keywords are well-chosen — keyword overlap correctly handles all 5 demo segments with zero false matches.
- **Source:** user decision, `rules/dependencies.md` (reuse over install), `rules/anti-patterns.md` (no speculative abstractions).

**Decision: Gemini for gap questions (not static template)**
- **Rejected alternative:** A fixed list of 4 generic questions applied to every no-match segment.
- **Reason:** Static questions feel templated in the demo and don't reflect the actual domain ("IoT glucose monitor API" warrants different questions than "blockchain integration"). The 1 extra Gemini call (for S04 in the demo) is well within free-tier limits. Demo criterion 2 requires a LOW-confidence item that feels compelling, not generic.
- **Source:** user decision.

**Decision: `EnrichedSegment` is a new dataclass (not a mutation of `ClassifiedSegment`)**
- **Rejected alternative:** Add enrichment fields directly to `ClassifiedSegment`.
- **Reason:** `ClassifiedSegment` is Layer 1's output contract; mutating it would couple Layer 1's type to Layer 2's concerns. Separate types preserve single-responsibility and make the pipeline boundary explicit.
- **Source:** `rules/architecture.md` (one file, one responsibility), existing pattern (Layer 1 returns its own result type).

**Decision: `confidence` inherits from reference `effort_confidence`**
- **Rejected alternative:** Compute confidence from keyword match count (e.g. ≥3 matches → HIGH, 1–2 → MEDIUM).
- **Reason:** The reference bank already carries calibrated confidence per task type (based on historical delivery data). Keyword count is a proxy for match quality, not for effort reliability. Inheriting the bank's own rating is more honest and auditable.
- **Source:** SPEC — *"the confidence level reflects how close the match is"* — interpreted as: the reference entry's own reliability rating is the right proxy for match confidence.

**Decision: gap-question parse failures fall back silently (no `EnrichmentError`)**
- **Rejected alternative:** Raise `EnrichmentError` if Gemini's gap-question response is unparseable.
- **Reason:** Gap-question generation is secondary — blocking the entire pipeline because a secondary Gemini call returned malformed JSON would violate *"nothing is silently dropped"* in a worse way. The fallback questions are explicit and labeled; the FDE is still better informed than with a crash.
- **Source:** SPEC Experience Design — *"Error: named, actionable errors … never raw stack traces."*

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Keyword overlap misses a synonym (`"auth"` vs `"authentication"`) | S01 could match at score 0 → false no-match | Reference bank keywords include synonyms (`"authentication"` and `"sso"`); if score=0 for a fixture segment, fix the keywords in T01 — not the matcher |
| Two tasks tie on keyword score | Non-deterministic match | Tie-breaking rule: first project, first task in bank file order; documented in `_find_best_match` |
| Gemini returns more than 4 gap questions | Verbose output | Truncate to first 4 in `_extract_gap_questions` |
| Gemini returns fewer than 3 gap questions | Gap list too sparse | Append from fallback list to reach 3 minimum |
| `reference_bank.json` missing at runtime | `EnrichmentError` raised before any enrichment | Named error with file path; no silent default |

---

## Testing Plan

File: `tests/test_layer2.py`

### `TestKeywordScoring` — unit (no I/O)

- `_score_task` returns 0 for empty keyword list
- `_score_task` returns 0 when no keyword appears in excerpt
- `_score_task` is case-insensitive (`"Single Sign-On"` vs `"sso"`)
- `_score_task` counts only distinct keyword hits (not frequency)

### `TestFindBestMatch` — unit (bank dict as fixture, no file I/O)

- S01 excerpt → matches `"sso-ldap-integration"` (keywords: `"sso"`, `"active directory"`)
- S04 excerpt (IoT glucose) → returns `None`
- Tie scenario (two tasks with equal score) → first task in file order wins (deterministic)

### `TestEnrichSegment` — unit (MockGeminiClient)

- **Match found:** segment → `EnrichedSegment` with `effort="5 days"`, `confidence=HIGH`, `blockers` populated, `gap_questions=[]`, `reference_match` set
- **No match:** segment → `EnrichedSegment` with `effort="estimate not available"`, `confidence=LOW`, `blockers=[]`, `gap_questions` has ≥3 items
- **Verbatim excerpt preserved:** `enriched.excerpt == segment.excerpt` (no modification)
- **L1 fields preserved:** `enriched.l1_confidence`, `enriched.l1_reasoning` copied from `ClassifiedSegment`
- **Markdown-wrapped gap questions JSON:** `MockGeminiClient` returns `` ```json\n{"questions": [...]} `` `` → correctly parsed
- **Unparseable gap questions:** `MockGeminiClient` returns `"oops"` → fallback list returned, no exception

### `TestEnrichSegments` — unit (MockGeminiClient, bank dict as fixture)

- `Layer1Result` with 3 segments (2 firm_request, 1 latent_request) → `Layer2Result` with 3 `EnrichedSegment`s
- Only `firm_request` / `latent_request` segments are processed (confirmed via `for_layer2()` contract)
- Missing bank file raises `EnrichmentError` with file path in message

### `TestIntegration` — skipped unless `GEMINI_API_KEY` is set

```python
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
class TestIntegration:
```

- Run `enrich_segments` on the real fixture transcript's Layer 1 output
- S01 → matched, `effort="5 days"`, `confidence=HIGH`
- S04 → no match, `effort="estimate not available"`, `confidence=LOW`, `gap_questions` has ≥3 items
- All enriched excerpts match verbatim excerpts from transcript fixture

> **Framework/pattern:** pytest, `MockGeminiClient` from `test_layer1.py`. Source: existing pattern in `tests/test_layer1.py:12–22`.

---

## Implementation Sequence

Each step is one cohesive commit:

1. **Add new dataclasses to `models.py`** — `ReferenceMatch`, `EnrichedSegment`, `Layer2Result`; run `mypy src/` to confirm no type errors
2. **Implement `_load_reference_bank`, `_score_task`, `_find_best_match`** in `layer2.py`; write `TestKeywordScoring` and `TestFindBestMatch` — all pass without any Gemini dependency
3. **Implement `_build_gap_questions_prompt`, `_extract_gap_questions`** (with fallback); write `TestEnrichSegment` happy-path (match) and edge cases (markdown wrapping, parse failure)
4. **Implement `_enrich_segment` and `enrich_segments`**; write `TestEnrichSegments` (no-match path, missing bank file); run `uv run pytest tests/test_layer2.py -v` — all pass
5. **Write `TestIntegration`** (guarded by `GEMINI_API_KEY`); run with real key to confirm S01 and S04 behavior

---

## Conventions Applied (from CLAUDE.md)

- Stack: Python with `uv`; `google-generativeai>=0.7` (no new dependency added)
- Tests: `pytest`, test files mirror `src/` structure under `tests/`; integration tests guarded by `@pytest.mark.skipif`
- LLM client: injectable `_GeneratorProtocol` for testability; `_build_default_client()` from env var
- Naming: English, snake_case for functions, PascalCase for classes
- No comments explaining *what* — only *why* where non-obvious
- Confidence: always `HIGH | MEDIUM | LOW` word labels (never color-only per SPEC)
- Error type: `EnrichmentError` for bank-loading failures (consistent with `ClassificationError` in Layer 1)

---

## Ready to Code?

- [x] Architecture described with modules and new files named
- [x] Contracts (internal interfaces, data model, Gemini prompt) in final form
- [x] Data model with types, required fields, and per-path rules (match vs. no-match)
- [x] Non-trivial trade-offs have a rejected alternative documented (4 decisions)
- [x] Known risks listed with mitigations (5 risks)
- [x] Testing plan covers happy path + at least 2 error cases per class (match, no-match, bad JSON, missing bank)
- [x] Implementation sequence is executable without clarification questions (5 commits)
- [x] No new library introduced (Gemini already in deps; keyword matching is pure Python)
- [x] CLAUDE.md conventions cited and respected
