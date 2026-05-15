# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What this project is

**Sprint Composer** — CLI agent that turns a raw meeting transcript into a structured 5-block sprint-plan proposal the FDE Lead can approve in ≤10 minutes.

The agent runs three sequential judgment layers:
1. **Layer 1** — classifies every transcript segment into one of five types: `firm_request | latent_request | decision | open_question | noise`
2. **Layer 2** — enriches `firm_request` and `latent_request` items against a synthetic reference bank; flags missing-effort as `"estimate not available"` + concrete questions when no close match exists
3. **Layer 3** — determines MoSCoW priority, sprint allocation (phase fit vs. Khal's 15-day cycle), and dependency ordering; flags items as `"needs Lead decision"` instead of guessing

Output: a 5-block proposal (sprint tasks / out-of-sprint / pending answers / decisions / discard appendix) on stdout + a JSON sibling for `explain` auditability.

Live docs: [`docs/specs/sprint-composer.md`](docs/specs/sprint-composer.md) (SPEC) · [`docs/plans/sprint-composer.md`](docs/plans/sprint-composer.md) (Plan).

---

## Stack and commands

```bash
# Install dependencies (creates .venv/)
uv sync

# Run all tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/path/test_file.py -v

# Run a single test
uv run pytest tests/path/test_file.py::test_name -v

# Lint + type-check
uv run ruff check src/ tests/
uv run mypy src/

# Format
uv run ruff format src/ tests/
```

`src/` layout — main package at `src/sprint_composer/`. Tests mirror the src structure under `tests/`.

---

## Architecture

The pipeline is strictly sequential — each module corresponds to a Plan task (T01–T06) and depends on the previous one.

```
transcript file (text)
      │
  [T01] fixtures        — synthetic transcript + taxonomy template + reference bank
      │
  [T02] layer1          — classifies segments; preserves verbatim source excerpt per item
      │                    decisions/open_questions/noise exit here → own output blocks
  [T03] layer2          — enriches firm/latent requests against reference bank
      │                    match found → real effort + blockers; no match → "estimate not available" + gap questions
  [T04] layer3          — MoSCoW + sprint allocation + dependency ordering
      │                    out-of-phase → out-of-sprint block; uncertain → "needs Lead decision"
  [T05] cli run         — parses header, runs L1–L3, emits 5-block stdout, writes JSON sibling
      │
  [T06] cli explain     — reads JSON sibling; prints source excerpt + full classification path for a task-id
```

### Domain vocabulary

| Term | Meaning |
|---|---|
| **Segment** | A discrete utterance or paragraph in the transcript |
| **Layer-1 type** | One of `firm_request`, `latent_request`, `decision`, `open_question`, `noise` |
| **Reference bank** | Synthetic collection of 4–5 fictitious past projects with recorded real effort and known blockers per task |
| **Confidence** | `HIGH | MEDIUM | LOW` — always a word label, never color-only |
| **5-block proposal** | The ordered output: sprint tasks / out-of-sprint / pending answers / decisions / discard appendix |
| **Task-id** | Stable identifier per sprint-task in the JSON sibling, required for `explain` |

### Non-negotiable business rules

- **Never fabricate an effort estimate.** No reference match → effort is exactly `"estimate not available"` + the specific questions needed to unlock it.
- **Nothing is silently dropped.** Every transcript segment lands in exactly one of the five output blocks.
- **Declare ignorance.** When MoSCoW can't be set with confidence, flag `"needs Lead decision"` and record why — never guess.
- **Every task is auditable.** Source excerpt is preserved verbatim (no paraphrasing) from classification through to `explain` output.
- **Header is mandatory.** `day`, `phase`, `participants` must be present and parseable — missing fields produce a named, actionable error; the CLI never silently defaults.

### CLI interface

```
sprint-composer run <transcript-path>     # runs L1→L3, prints 5-block proposal, writes <transcript>.json
sprint-composer explain <task-id>         # prints source excerpt + L1 type + L2 enrichment + L3 reasoning + confidence reason
```

Progress lines emitted per layer during `run` so a multi-second pipeline never looks frozen.
