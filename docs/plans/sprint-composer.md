# Plan: Sprint Composer

> Reference SPEC: [`docs/specs/sprint-composer.md`](../specs/sprint-composer.md)
> This plan breaks the SPEC into **independent tasks**, each ready to become a dedicated Tech Spec.
> There is **no** stack, schema, architecture, or estimation here — only behavior and sequencing.

---

## Target Outcome

- **Anchor result** (from SPEC): the FDE can turn a meeting transcript into a 5-block proposal that the Lead approves in **≤10 minutes**, and the run on the synthetic transcript simultaneously satisfies the four demo criteria (correct typology, consistent confidence, allocation-by-phase, auditability via `explain`).
- **MVP of this plan:** all six tasks — T01 → T06. Each maps to at least one demo success criterion, so none can be cut without breaking the demo bar.
- **Later phases:** real (non-synthetic) reference bank, multi-meeting aggregation, Jira/ClickUp integrations, live audio ingestion, web/dashboard UI. All deliberately out of v0.

---

## Task Map

| #   | Task                                         | Covers (SPEC scenarios)                                                                                  | Depends on | Phase | Status  |
| --- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ---------- | ----- | ------- |
| T01 | Synthetic fixtures                           | Inputs for all behaviors; baseline for demo criteria 1–4                                                 | —          | MVP   | pending |
| T02 | Layer 1 — typology classification            | *Classify each transcript segment into the five Layer-1 types*                                           | T01        | MVP   | pending |
| T03 | Layer 2 — enrichment + missing-info detection| *Enrich a request with historical reference*; *Flag a request when no historical reference*; *Never invent an effort estimate* | T01, T02 | MVP | pending |
| T04 | Layer 3 — priority & allocation              | *Push an out-of-phase request out of the current sprint*; *Prioritize a blocking task above customer preference*; *Refuse to classify confidently when signals are insufficient* | T03 | MVP | pending |
| T05 | CLI `run` + 5-block proposal output          | *Produce the 5-block proposal output*; CLI states (empty / loading / success / error); header parsing   | T04        | MVP   | pending |
| T06 | CLI `explain <task-id>`                      | *Explain an individual task*; demo criterion 4 (auditability)                                            | T05        | MVP   | pending |

> Suggested order: **T01 → T02 → T03 → T04 → T05 → T06** (strictly sequential; each task unlocks the next).

---

## Task Details

### T01 — Synthetic fixtures

- **Behavior delivered:** the project ships with the input data required to run and demo the full pipeline — a plausible enterprise-client meeting transcript with the right typology mix, a documented "taxonomy template" that labels which segments are which Layer-1 type, and a synthetic reference bank of 4–5 fictitious past projects with recorded real effort and known blockers per task.
- **Stories/behaviors covered in SPEC:** baseline for every Given/When/Then in *Expected Behaviors*; demo criterion 1 ("correct typology" — requires the template to grade against); demo criterion 2 ("LOW confidence" — requires at least one request with no good reference match in the bank); demo criterion 3 ("out of sprint by phase" — requires at least one out-of-phase request in the transcript).
- **Acceptance criteria:**
  - Given the transcript file is opened, when the header is read, then `day`, `phase`, and `participants` are present and parseable.
  - Given the transcript body, when each segment is inspected, then at least one example of each of the five Layer-1 types is present (firm_request, latent_request, decision, open_question, noise), including one latent request (unresolved pain) and at least one scope decision.
  - Given the reference bank, when its entries are inspected, then 4–5 fictitious projects exist, each with at least one task carrying real effort and known typical blockers; at least one prospective transcript request has **no** close match in the bank (to force a *"estimate not available"* path downstream).
  - Given the taxonomy template, when it is compared to the transcript, then every transcript segment has a labelled expected Layer-1 type (so Layer 1 can be graded against ≥80% correct typology).
- **Depends on:** —
- **Pending assumptions:** none — all data is synthetic and owned in-repo.
- **Tech Spec:** pending

### T02 — Layer 1: typology classification

- **Behavior delivered:** given a transcript file, the system reads its segments and classifies each as exactly one of `firm_request | latent_request | decision | open_question | noise`, preserving the source excerpt for every classified item.
- **Stories/behaviors covered in SPEC:**
  - Scenario *"Classify each transcript segment into the five Layer-1 types"*.
  - Demo criterion 1 (correct typology in ≥80% of template items).
- **Acceptance criteria:**
  - Given the synthetic transcript from T01, when Layer 1 runs, then every segment is assigned exactly one of the five types.
  - Given the taxonomy template from T01, when Layer 1's output is compared against it, then ≥80% of segments match the expected type.
  - Given each classified item, when it is inspected, then it retains the verbatim source excerpt from the transcript (no paraphrasing of source).
  - Given items classified as `decision`, `open_question`, or `noise`, when downstream layers run, then they are **not** fed to Layer 2 (they route straight to their output blocks later).
- **Depends on:** T01
- **Pending assumptions:** none
- **Tech Spec:** pending

### T03 — Layer 2: enrichment + missing-info detection

- **Behavior delivered:** for every item classified as `firm_request` or `latent_request`, the system searches the reference bank for similar past tasks; if a close match exists, the item is enriched with that task's recorded real effort and known typical blockers; if no close match exists, the item is marked with effort `"estimate not available"` plus the concrete questions that would unlock an estimate. The system never fabricates an effort number.
- **Stories/behaviors covered in SPEC:**
  - Scenario *"Enrich a request with historical reference when one exists"*.
  - Scenario *"Flag a request when no historical reference is available"*.
  - Scenario *"Never invent an effort estimate"*.
- **Acceptance criteria:**
  - Given a request with a close match in the reference bank, when Layer 2 runs, then the enriched item carries: the matched reference task(s), the reference's recorded real effort, and any known typical blockers; the effort field is populated using that anchor; confidence reflects match closeness.
  - Given a request with **no** close match in the reference bank, when Layer 2 runs, then the effort field reads exactly `"estimate not available"`, the item lists the specific questions that would unlock estimation, and the item is tagged LOW confidence with the gap named in the justification.
  - Given any request, when Layer 2 completes, then the effort field is either drawn from a referenced anchor or is exactly `"estimate not available"` — never a heuristic or model-fabricated number.
- **Depends on:** T01, T02
- **Pending assumptions:** none
- **Tech Spec:** pending

### T04 — Layer 3: priority & allocation

- **Behavior delivered:** for every enriched request, the system decides (a) whether it belongs in the current sprint or in "out of sprint" based on Khal's 15-day-cycle phase, (b) its order relative to other tasks based on dependency detection (blockers win over customer-stated preference), and (c) its MoSCoW classification with a confidence level. Items the system cannot confidently classify are flagged as *"needs Lead decision"* rather than guessed.
- **Stories/behaviors covered in SPEC:**
  - Scenario *"Push an out-of-phase request out of the current sprint"*.
  - Scenario *"Prioritize a blocking task above customer-stated preference"*.
  - Scenario *"Refuse to classify confidently when signals are insufficient"*.
  - Demo criterion 3 (at least one item moved to "out of sprint" with a phase-cycle reason).
- **Acceptance criteria:**
  - Given a request introducing new scope incompatible with the current phase from the header, when Layer 3 runs, then the item lands in "out of sprint" with a reason that explicitly references Khal's 15-day cycle phase mismatch.
  - Given two requests where one blocks the other, when Layer 3 orders them, then the blocker is ordered first regardless of any customer-stated preference, and the justification names the dependency.
  - Given a request whose MoSCoW level cannot be set with confidence from available signals, when Layer 3 runs, then the item is included but flagged *"needs Lead decision"* with the reason recorded.
  - Given the synthetic transcript, when the full pipeline runs, then at least one item lands in "out of sprint" with a 15-day-cycle reason (demo criterion 3 satisfied).
- **Depends on:** T03
- **Pending assumptions:** none
- **Tech Spec:** pending

### T05 — CLI `run` + 5-block proposal output

- **Behavior delivered:** the FDE invokes a CLI with `run <transcript-path>`; the CLI parses the header, refuses to proceed with a clear error if the header is missing or malformed, runs Layers 1–3, prints a human-readable 5-block proposal to stdout, and writes a machine-readable JSON sibling next to the transcript. Each task in the proposal carries a stable id so it can be referenced by `explain` later. The CLI emits short per-layer progress lines so a multi-second run never looks frozen.
- **Stories/behaviors covered in SPEC:**
  - Scenario *"Produce the 5-block proposal output"*.
  - All four interface states (empty / loading / success / error) from *Experience Design*.
  - The "nothing is silently dropped" non-negotiable principle.
- **Acceptance criteria:**
  - Given a valid transcript file with a well-formed header, when `run` executes, then the stdout output contains, in order, five distinct blocks: (1) Proposed sprint tasks, (2) Out of sprint, (3) Pending customer answers, (4) Recorded decisions, (5) Discard appendix; and a JSON sibling is written alongside the transcript.
  - Given each task in block 1, when it is inspected, then it has: title, phase, MoSCoW, confidence, effort or `"estimate not available"`, justification, and source excerpt.
  - Given the full transcript, when `run` completes, then every transcript segment has landed in exactly one of the five blocks — nothing is silently dropped.
  - Given a transcript missing the header or with malformed header fields, when `run` is invoked, then the CLI refuses to run and prints a named, actionable error stating exactly which field is missing — never a raw stack trace.
  - Given no argument is passed, when the CLI is invoked, then a usage message with an example command is printed and no work runs.
  - Given a multi-second pipeline run, when each layer starts, then a short progress line (e.g. *"Layer 2: enriching…"*) is emitted so the run never looks frozen.
- **Depends on:** T04
- **Pending assumptions:** none
- **Tech Spec:** pending

### T06 — CLI `explain <task-id>`

- **Behavior delivered:** after a `run` has been performed, the FDE invokes `explain <task-id>` against any task surfaced in the proposal; the CLI prints the verbatim source excerpt(s) from the transcript, the Layer-1 classification applied, the Layer-2 enrichment used (matched reference task or *"no match found"*), the Layer-3 allocation reasoning (phase fit, dependencies), and the reason for the assigned confidence level.
- **Stories/behaviors covered in SPEC:**
  - Scenario *"Explain an individual task"*.
  - Demo criterion 4 (auditability — for any task, source + classification + confidence reasoning).
- **Acceptance criteria:**
  - Given a prior successful `run` produced a JSON sibling with stable task ids, when `explain <task-id>` is invoked, then the output prints the verbatim source excerpt(s), the Layer-1 type, the Layer-2 enrichment outcome (matched reference or "no match found"), the Layer-3 allocation reasoning, and the confidence reasoning.
  - Given an unknown or missing task-id, when `explain` is invoked, then a named, actionable error is printed (never a stack trace), and the CLI exits non-zero.
  - Given the demo run, when `explain` is run on at least one task that was tagged LOW confidence and at least one task moved to "out of sprint", then both outputs visibly satisfy demo criterion 4.
- **Depends on:** T05
- **Pending assumptions:** none
- **Tech Spec:** pending

---

## External Dependencies

No external dependencies block this plan. All inputs (transcript, taxonomy template, reference bank) are synthetic and owned in-repo. No third-party API contracts, no customer access, no legal/compliance gate.

- [ ] *(none)*

---

## Out of This Plan

Items from the SPEC's *Out of Scope* are not revisited here; in addition, the following SPEC-adjacent items are explicitly deferred:

- **Real, indexed reference bank from past Khal squads** — v1 path documented in SPEC; v0 uses 4–5 plausible synthetic projects (handled in T01).
- **Jira / ClickUp / Linear integrations** — out of v0 per SPEC.
- **Multi-meeting aggregation** — out of v0 per SPEC.
- **Live audio ingestion / on-the-fly transcription** — out of v0 per SPEC.
- **Web UI / dashboard** — CLI only in v0 per SPEC.
- **Blocker resolution** — agent only detects/logs blockers per SPEC.

---

## Ready for Tech Spec?

- [x] Every task cites at least one story/behavior from the SPEC
- [x] Every task fits in one Tech Spec (no mega-tasks — confirmed with user that bundling T01 fixtures and T05 CLI+output is the right granularity)
- [x] Dependencies are explicit and cycle-free (strict T01 → T02 → T03 → T04 → T05 → T06 chain)
- [x] MVP is identified and closes the anchor result (all six tasks are MVP; each maps to a demo success criterion)
- [x] Zero implementation details (no stack, schema, endpoint, infra)
- [x] SPEC out-of-scope is respected (Jira, multi-meeting, web UI, live transcription, blocker resolution, real reference bank all out)
- [x] External blocking dependencies are listed (none)
