# Tech Spec: Layer 1 — Typology Classification — `T02`

> **SPEC:** [`docs/specs/sprint-composer.md`](../specs/sprint-composer.md)
> **Plan:** [`docs/plans/sprint-composer.md`](../plans/sprint-composer.md) — task `T02`
> **Conventions applied:** `CLAUDE.md` (project) · `rules/git.md` · `rules/secrets.md` · `rules/dependencies.md` · `rules/testing.md`
>
> This document details **how** to deliver T02. The **why** lives in the SPEC; **what** and **in what order**, in the Plan.

---

## Task Scope

- **Behavior delivered:** Given a parsed transcript body (list of string segments), classify each segment as exactly one of `firm_request | latent_request | decision | open_question | noise`, preserving the full verbatim text as the source excerpt and recording a `HIGH | MEDIUM | LOW` confidence label with a one-sentence reasoning per item.
- **SPEC stories/criteria covered:**
  - Scenario *"Classify each transcript segment into the five Layer-1 types"*
  - Demo criterion 1 (correct typology — ≥80% match against taxonomy template)
- **Depends on:** T01 (fixtures — transcript, taxonomy template, reference bank)
- **External dependencies:** Gemini API (`GEMINI_API_KEY` in `.env`); free tier (15 RPM) is sufficient for all fixture segments and demo runs.

---

## Architecture

T02 introduces the first real Python modules in `src/sprint_composer/`. Two files are created:

1. **`models.py`** — shared domain types used by T02, T03, T04, and T05. Defines enums and dataclasses; no external imports beyond stdlib. Every subsequent task imports from here.
2. **`layer1.py`** — single public function `classify_transcript(segments, client)` that classifies a list of string segments. Uses Gemini to classify each segment individually via a structured prompt that demands a JSON-only response. Returns a `Layer1Result` containing `ClassifiedSegment` items; also exposes a `.for_layer2()` helper that filters to only `firm_request` and `latent_request` items for downstream use.

The intermediate Layer 1 JSON artifact (for demo step-through) is **written by T05's CLI**, not by `layer1.py`. Layers are pure functions — no file I/O side effects.

**New files:**

```
src/sprint_composer/models.py      — SegmentType, Confidence, ClassifiedSegment, Layer1Result
src/sprint_composer/layer1.py      — classify_transcript(), ClassificationError
tests/test_layer1.py               — 9 tests (8 unit, 1 integration)
```

**Modified files:**

```
pyproject.toml          — add google-generativeai>=0.7 to [project.dependencies]
.env.example            — add GEMINI_API_KEY= entry
```

**Reused patterns:** `json`, `re`, `os`, `dataclasses`, `enum` from stdlib — same philosophy as T01 (no new deps beyond the one LLM client).

---

## Contracts

### Public function

```python
# src/sprint_composer/layer1.py

def classify_transcript(
    segments: list[str],
    client: _GeneratorProtocol | None = None,
) -> Layer1Result:
    """
    Classify each segment into one of the five Layer-1 types.

    segments  — non-empty list of verbatim transcript body segments (paragraph strings)
    client    — optional injected Gemini client (for testing); if None, built from GEMINI_API_KEY env var

    Returns a Layer1Result with one ClassifiedSegment per input segment.
    Raises ClassificationError if the API returns unparseable output.
    Raises EnvironmentError if GEMINI_API_KEY is not set and no client is injected.
    """
```

### Domain types (`models.py`)

```python
# src/sprint_composer/models.py

from dataclasses import dataclass
from enum import Enum


class SegmentType(str, Enum):
    FIRM_REQUEST   = "firm_request"
    LATENT_REQUEST = "latent_request"
    DECISION       = "decision"
    OPEN_QUESTION  = "open_question"
    NOISE          = "noise"


# Segment types that proceed to Layer 2 enrichment
L2_ELIGIBLE: frozenset[SegmentType] = frozenset({
    SegmentType.FIRM_REQUEST,
    SegmentType.LATENT_REQUEST,
})


class Confidence(str, Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


@dataclass
class ClassifiedSegment:
    segment_id: str        # "S01", "S02", ... (auto-assigned, 1-indexed, zero-padded to 2 digits)
    excerpt:    str        # verbatim full segment text (copy of input string, never modified)
    type:       SegmentType
    confidence: Confidence
    reasoning:  str        # one sentence — why this type and confidence level


@dataclass
class Layer1Result:
    segments: list[ClassifiedSegment]

    def for_layer2(self) -> list[ClassifiedSegment]:
        """Items eligible for Layer 2 enrichment (firm_request and latent_request only)."""
        return [s for s in self.segments if s.type in L2_ELIGIBLE]
```

### Internal protocol (for dependency injection)

```python
# src/sprint_composer/layer1.py  (module-private)

from typing import Protocol

class _GenerateResponse(Protocol):
    @property
    def text(self) -> str: ...

class _GeneratorProtocol(Protocol):
    def generate_content(self, prompt: str) -> _GenerateResponse: ...
```

`genai.GenerativeModel` satisfies `_GeneratorProtocol` at runtime. Tests inject a simple mock that also satisfies it.

### Layer 1 JSON intermediate artifact format

Written by T05 CLI after calling `classify_transcript`. Documented here so T05 implements the exact format.

```json
{
  "source_transcript": "<path/to/transcript.txt>",
  "segments": [
    {
      "segment_id": "S01",
      "excerpt": "<full verbatim segment text>",
      "type": "firm_request",
      "confidence": "HIGH",
      "reasoning": "Explicit SSO/Active Directory integration request with clear scope."
    }
  ]
}
```

Serialization: `SegmentType` and `Confidence` are `str` enums — `value` is their JSON string. `ClassifiedSegment` serializes to `{"segment_id": ..., "excerpt": ..., "type": ..., "confidence": ..., "reasoning": ...}`.

---

## Data Model

| Field | Type | Notes |
|---|---|---|
| `segment_id` | `str` | `f"S{i+1:02d}"` — index from 0, zero-padded to 2 digits. Stable for same ordered input. |
| `excerpt` | `str` | Identical to the input segment string. No trimming, no paraphrasing. |
| `type` | `SegmentType` | One of the five values. Never null. |
| `confidence` | `Confidence` | `HIGH \| MEDIUM \| LOW`. Reflects how unambiguous the classification signal is. |
| `reasoning` | `str` | One sentence. Must name the classification signal (e.g. "Explicit request verb + stated scope"). |

**Segment ID generation rule:**

```python
for i, segment_text in enumerate(segments):
    segment_id = f"S{i + 1:02d}"
```

Same transcript → same IDs (deterministic order). Matches `segment_id` format in `taxonomy_template.json` (`S01`–`S08`).

---

## External Integrations

- **Partner:** Google Gemini API
- **SDK:** `google-generativeai>=0.7` (runtime dependency)
- **Model:** `gemini-3.1-flash-lite` (free tier; fastest; sufficient for single-segment classification)
- **Authentication:** `GEMINI_API_KEY` env var; loaded via `os.environ`. If absent and no `client` injected, `classify_transcript` raises `EnvironmentError` with a named, actionable message.
- **Rate limits:** Free tier is 15 RPM / 1M tokens per minute. With 8 segments, each call takes <1 second — no batching or throttling needed for the demo. Production note (future): add `time.sleep(4)` between calls if processing transcripts with >14 segments.
- **Prompt contract:** One API call per segment. Response must be a JSON object containing `type`, `confidence`, and `reasoning`. Response parsing handled by `_extract_json()` (see Trade-offs).
- **Mock contract for tests:** `MockGeminiClient` (in `tests/test_layer1.py`) implements `_GeneratorProtocol`; returns pre-scripted `MockResponse(text=...)` objects. No network call in unit tests.

**Prompt template** (verbatim — code agent must use exactly this):

```
You are a meeting-transcript analyst. Classify the following transcript segment into EXACTLY ONE of five categories.

Categories:
- firm_request: An explicit, direct request or stated requirement from a stakeholder.
- latent_request: An implicit pain point, frustration, or unmet need — not framed as a direct request.
- decision: A conclusion, agreement, or resolved matter reached in this meeting.
- open_question: An unresolved question that requires further information or action.
- noise: Off-topic remarks, social conversation, or content with no bearing on the project.

Transcript segment:
\"\"\"
{segment}
\"\"\"

Return ONLY a valid JSON object (no markdown, no explanation, no surrounding text):
{{"type": "<one of the five categories>", "confidence": "<HIGH|MEDIUM|LOW>", "reasoning": "<one sentence>"}}
```

---

## Trade-offs and Rejected Alternatives

**Decision: Gemini free tier via `google-generativeai` (not rule-based keyword matching)**
- **Rejected alternative:** Keyword/pattern matching against signals like "we need to", "we've decided", "by the way"
- **Reason:** Keyword matching is brittle — it classifies the fixture deterministically but fails on transcript phrasing variation. For a demo at an AI company, a real LLM classification layer demonstrates actual capability. Rule-based would achieve ≥80% on the 8-segment fixture by construction but proves nothing.
- **Source:** User decision; `rules/dependencies.md` ("reuse over install" — Gemini is the one LLM dep added here; justified by the task's core purpose).

**Decision: One API call per segment (not batch)**
- **Rejected alternative:** Single call with all segments concatenated
- **Reason:** Batching requires the model to track segment boundaries across a long prompt, increasing error probability and making JSON extraction fragile. Per-segment calls are simpler, independently retryable, and produce cleaner output. With 8 segments, latency is acceptable.
- **Source:** Simplicity + robustness; no stated performance constraint in SPEC for this demo.

**Decision: Protocol-based dependency injection (not `unittest.mock.patch`)**
- **Rejected alternative:** Patching `google.generativeai.GenerativeModel` in tests
- **Reason:** Patching a third-party module path is brittle — any internal rename breaks the test. A `Protocol`-typed `client` parameter makes the seam explicit, type-safe under mypy strict, and obvious to future maintainers.
- **Source:** `rules/testing.md` (test the contract, not the implementation); mypy strict mode requirement in `pyproject.toml`.

**Decision: `_extract_json()` with regex fallback (not `json.loads(response.text)` directly)**
- **Rejected alternative:** Direct `json.loads(response.text)`
- **Reason:** LLMs reliably return markdown-wrapped JSON (` ```json ... ``` `) even when explicitly told not to. A regex strip prevents `JSONDecodeError` on valid-but-wrapped responses, which would fail the demo non-deterministically.
- **Source:** Observed LLM behavior across multiple providers; defensive parsing at system boundary.

**Decision: Excerpt = full verbatim segment text (not a short opening phrase)**
- **Rejected alternative:** Store only the first 20+ characters (as taxonomy template uses for identification)
- **Reason:** The `explain` command (T06) shows "the verbatim source excerpt(s) from the transcript" — a 20-character snippet is insufficient for the FDE to understand context. The taxonomy template uses short phrases only as identifiers for fixture grading, not as the display excerpt.
- **Source:** SPEC *"Explain an individual task"* scenario; CLAUDE.md "Every task is auditable — source excerpt is preserved verbatim".

**Decision: File I/O left to T05 CLI (layers are pure functions)**
- **Rejected alternative:** `layer1.py` writes the `.layer1.json` intermediate artifact itself
- **Reason:** Side effects in layer functions make unit testing require temporary files or monkeypatching. Keeping layers as pure functions (input → output) allows tests to call them without touching the filesystem. T05 orchestrates all I/O.
- **Source:** Separation of concerns; CLAUDE.md architecture diagram shows T05 as the I/O orchestrator.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Gemini returns non-JSON or partial JSON | `ClassificationError` breaks the pipeline | `_extract_json()` regex handles markdown wrapping; explicit error type with message quotes the raw response |
| Gemini returns a `type` value not in enum | Silent misclassification propagates to T03 | After `json.loads`, validate `type` value against `SegmentType` values; raise `ClassificationError` with the invalid value named |
| `GEMINI_API_KEY` not in environment | `EnvironmentError` with unhelpful message | `_build_default_client()` checks `os.environ.get("GEMINI_API_KEY")`; raises `EnvironmentError("GEMINI_API_KEY is not set. Add it to your .env file.")` if absent |
| Segment ordering changes between calls | `segment_id` mismatches taxonomy template | IDs are assigned from the input list index — the same transcript file always produces the same segment order via the `\n\n` split |
| `google-generativeai` API breaking change | Compilation or runtime failure | Version pinned to `>=0.7` (stable `GenerativeModel` API surface); Protocol-based injection isolates the dependency surface |

---

## Testing Plan

**File:** `tests/test_layer1.py`

All unit tests use `MockGeminiClient` (defined in the same test file) to avoid network calls. The one integration test is skipped when `GEMINI_API_KEY` is absent.

### MockGeminiClient (test helper)

```python
class MockResponse:
    def __init__(self, text: str) -> None:
        self.text = text

class MockGeminiClient:
    def __init__(self, responses: list[str]) -> None:
        self._iter = iter(responses)

    def generate_content(self, prompt: str) -> MockResponse:
        return MockResponse(next(self._iter))
```

### Unit tests (8 tests, no network)

**Happy path:**

- `test_all_segments_get_a_classification` — given 3 segments and a mock client returning valid JSON for each, every segment in `result.segments` has a non-null `type`, `confidence`, and `reasoning`.
- `test_excerpt_equals_input_segment` — the `excerpt` field on each `ClassifiedSegment` is identical to the original input string (byte-for-byte, no strip/trim).
- `test_segment_ids_sequential` — given N segments, IDs are `S01`, `S02`, ..., `S{N:02d}` in order.
- `test_types_are_valid_enum_values` — all `type` values in the result are members of `SegmentType`.
- `test_for_layer2_includes_only_requests` — given one segment of each type (5 total), `result.for_layer2()` returns exactly the 2 items with `firm_request` and `latent_request`.

**Error cases:**

- `test_garbage_response_raises_classification_error` — mock returns `"this is not json"`; `classify_transcript` raises `ClassificationError`.
- `test_unknown_type_in_response_raises_classification_error` — mock returns `{"type": "wish_list", "confidence": "HIGH", "reasoning": "..."}` (invalid type); raises `ClassificationError` naming `"wish_list"` in the message.

**Edge case:**

- `test_markdown_wrapped_json_parsed` — mock returns ` ```json\n{"type": "noise", "confidence": "HIGH", "reasoning": "off-topic"}\n``` `; result is correctly parsed (no error raised, type is `SegmentType.NOISE`).

### Integration test (1 test, skipped without key)

- `test_accuracy_against_taxonomy` — calls real Gemini API with the 8-segment fixture transcript; compares each classified type against `fixtures/taxonomy_template.json`; asserts ≥80% match (≥7/8 segments correct). Decorated with `@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")`.

**Total: 9 tests.** Framework: pytest (no plugins beyond what T01 established). Source: CLAUDE.md, `rules/testing.md`.

---

## Implementation Sequence

Each step is one cohesive commit:

1. **Add runtime dep** — add `dependencies = ["google-generativeai>=0.7"]` to `[project]` in `pyproject.toml`; add `GEMINI_API_KEY=` to `.env.example`; run `uv sync` to update `uv.lock`; confirm `uv run pytest` still passes all 14 T01 tests.

2. **Write `src/sprint_composer/models.py`** — `SegmentType`, `Confidence`, `L2_ELIGIBLE`, `ClassifiedSegment`, `Layer1Result` (with `for_layer2()` method). No external imports. Run `uv run mypy src/` to confirm clean.

3. **Write `src/sprint_composer/layer1.py`** — in this order:
   - `ClassificationError(Exception)` — custom exception
   - `_GenerateResponse` and `_GeneratorProtocol` Protocols
   - `_extract_json(text: str) -> dict[str, str]` — strips markdown fences, regex-extracts `{...}`, calls `json.loads`, returns dict or raises `ClassificationError`
   - `_validate_classification(raw: dict[str, str]) -> tuple[SegmentType, Confidence, str]` — validates `type` is in `SegmentType`, `confidence` is in `Confidence`, returns typed tuple or raises `ClassificationError`
   - `_build_default_client() -> _GeneratorProtocol` — reads `GEMINI_API_KEY` from env, configures `genai`, returns `genai.GenerativeModel("gemini-3.1-flash-lite")`; raises `EnvironmentError` if key absent
   - `_build_prompt(segment: str) -> str` — formats the prompt template with `segment`
   - `classify_transcript(segments, client=None) -> Layer1Result` — assigns IDs, loops over segments, calls `client.generate_content(_build_prompt(seg))`, calls `_extract_json`, calls `_validate_classification`, assembles `ClassifiedSegment` list

4. **Write `tests/test_layer1.py`** — `MockResponse`, `MockGeminiClient`, all 8 unit tests, 1 integration test. Run `uv run pytest tests/test_layer1.py -v -k "not accuracy"` — all 8 unit tests pass.

5. **Verify full suite** — `uv run pytest tests/ -v` — all 23 tests pass (14 T01 + 9 T02, integration skipped if no key). Run `uv run ruff check src/ tests/` — clean. Run `uv run mypy src/` — clean.

---

## Conventions Applied (from CLAUDE.md)

- **Stack:** Python ≥ 3.11, uv, pytest, ruff, mypy strict
- **Layout:** `src/sprint_composer/` (main package), `tests/` (mirrors src)
- **Runtime deps:** one new dep (`google-generativeai>=0.7`) explicitly justified — see Trade-offs section
- **Secrets:** `GEMINI_API_KEY` in `.env` (gitignored); `.env.example` updated with blank entry — per `rules/secrets.md`
- **Testing:** pytest, no plugins; dependency injection via Protocol, not `unittest.mock.patch`; integration test skipped when key absent
- **Language:** English for all code, identifiers, filenames, prompt text
- **Confidence:** always a `HIGH | MEDIUM | LOW` word label — per CLAUDE.md "never color-only"
- **Excerpt:** verbatim, never paraphrased — per CLAUDE.md "Every task is auditable"

---

## Ready to Code?

- [x] Architecture described — two new modules (`models.py`, `layer1.py`), two modified files (`pyproject.toml`, `.env.example`), one test file; all purposes stated
- [x] Contracts in final form — public function signature with types, Protocol definitions, Layer 1 JSON intermediate format with example
- [x] Data model with all fields, types, and the `segment_id` generation formula
- [x] External integration fully specified — SDK, model name, auth, rate limits, exact prompt template, mock contract
- [x] Five non-trivial trade-offs documented with rejected alternatives and sources
- [x] Known risks listed with named mitigations
- [x] Testing plan names all 9 tests; `MockGeminiClient` structure specified; integration test skip condition stated
- [x] Implementation sequence executable step-by-step; each step is one commit; verify command included
- [x] One new runtime library introduced (`google-generativeai`) with explicit justification
- [x] CLAUDE.md conventions cited and respected
