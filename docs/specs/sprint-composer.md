# SPEC: Sprint Composer

> Turn the raw output of a client meeting into a sprint-plan **proposal** — with stated confidence per item, separate destinations for decisions/questions/noise, and explicit gaps — that the FDE Lead can validate in under 10 minutes instead of reconstructing from scratch.

---

## Problem Definition

- **Concrete pain:** After a 60-minute client alignment meeting, the FDE returns to a blank canvas holding a transcript that mixes firm requests, latent pains, decisions, open questions, and side noise. Today they improvise: deciding what becomes a task, for which sprint, with what effort, and what blocks what is artisanal, individual, and prone to omissions. Each omission at the entry of the cycle becomes a deviation downstream during execution.
- **Affected persona(s):** Khal **FDE** fully allocated to an enterprise customer squad (healthcare / fintech / retail / BPO), operating inside Khal's 15-day cycle (Discovery → Setup → Simulation → Go-live). Secondary: **FDE Lead**, who is the one validating the proposal before it goes to the customer.
- **Current behavior:** The FDE manually re-reads the transcript, writes a to-do list by feel, guesses effort, and brings it to the Lead. The Lead either spends ~2h reworking it or rejects it and asks for a redo. Decisions, open questions, and side comments routinely get lost or collapsed into the task list.

---

## Success Metrics

- **Observable change in user behavior:** After running Sprint Composer on a meeting transcript, the FDE arrives at the Lead review with a structured 5-block proposal (tasks / out-of-sprint / pending answers / decisions / discarded) instead of an ad-hoc to-do list. The Lead reads it, adjusts a small number of items, and approves — they no longer redo the work from scratch.
- **Anchor metric:** **Time from transcript → Lead-approved proposal ≤ 10 minutes** (vs. ~3 hours today).
- **Informal acceptance gate:** If the Lead reads the proposal and says *"I'll adjust 3 things and send it to the customer"*, the MVP worked. If they say *"let me redo it from scratch"*, it didn't.

### Demo success criteria (interview deliverable)

A run on the synthetic transcript must simultaneously satisfy:

1. **Correct typology** — at least one item of each of the five Layer-1 types appears in its correct output destination (firm → task; latent → discovery task; decision → log; question → pending; noise → appendix).
2. **Consistent confidence** — at least one task is tagged **LOW** confidence with an explicit reason (e.g. *"missing X from the customer"*), demonstrating that the agent declares what it does not know.
3. **Allocation by phase** — at least one task is pushed to **out-of-sprint** with a justification tied to Khal's 15-day cycle.
4. **Auditability** — `explain <task-id>` shows: the source excerpt from the transcript, the classification applied, and the reason for the confidence level.

---

## User Stories

- As an **FDE**, I want to feed a meeting transcript (with header metadata) to a CLI and receive a structured sprint-plan proposal in seconds, so that I do not have to manually re-read and bucket every line.
- As an **FDE**, I want each proposed task to carry a confidence level, justification, and source excerpt, so that I can defend or revise it in front of the Lead without re-reading the whole transcript.
- As an **FDE**, I want items that are **not** tasks (decisions, open questions, noise) to land in distinct output blocks, so that nothing important gets silently dropped and nothing trivial pollutes the task list.
- As an **FDE**, I want the agent to tell me **what it doesn't know** — concrete questions to ask the customer or the Lead — instead of guessing, so that I can leave the meeting with a clear next step.
- As an **FDE Lead**, I want to read the proposal in ≤2 minutes and see for each task its phase, MoSCoW rating, confidence, and (if available) effort with reference, so that I can approve, reject, or adjust without reconstructing it from scratch.
- As an **FDE**, I want to run `explain <task-id>` on any single task and see exactly which transcript excerpt produced it, the classification path, and why the confidence is what it is, so that I can audit the agent's judgment when the Lead pushes back.
- As an **FDE**, when no historical reference exists for a task, I want the effort field to say *"estimate not available"* together with the specific questions that would need to be answered before estimation is possible, so that the gap becomes actionable rather than blank.

---

## Expected Behaviors

```gherkin
Scenario: Classify each transcript segment into the five Layer-1 types
  Given a meeting transcript with header metadata (day, phase, participants)
  When the FDE runs Sprint Composer on the file
  Then every transcript segment is classified as exactly one of:
    firm_request | latent_request | decision | open_question | noise
  And firm and latent requests proceed to Layer 2 (enrichment)
  And decisions, open questions, and noise are routed straight to their own output blocks
```

```gherkin
Scenario: Enrich a request with historical reference when one exists
  Given a request classified as firm_request or latent_request
  And the synthetic reference bank contains a similar past task
  When the agent enriches the request
  Then the proposed task carries: similar past task(s), recorded real effort, and known typical blockers
  And the effort field is populated using that anchor
  And the confidence level reflects how close the match is
```

```gherkin
Scenario: Flag a request when no historical reference is available
  Given a request that has no close match in the reference bank
  When the agent attempts to estimate effort
  Then the effort field is "estimate not available"
  And the task lists the specific questions that would unlock an estimate
  And the task is tagged with LOW confidence and the gap is named in the justification
```

```gherkin
Scenario: Push an out-of-phase request out of the current sprint
  Given the project is on day 10 (Simulation phase)
  And a request introduces new scope incompatible with the current phase
  When the agent runs Layer 3 allocation
  Then the item lands in the "Out of sprint" block, not the sprint proposal
  And the reason explicitly references Khal's 15-day cycle phase mismatch
```

```gherkin
Scenario: Prioritize a blocking task above customer-stated preference
  Given task A is required by task B (dependency detected)
  And the customer voiced preference for task B first
  When the agent orders the proposal
  Then task A appears before task B
  And the justification names the dependency relationship
```

```gherkin
Scenario: Refuse to classify confidently when signals are insufficient
  Given an item the agent cannot confidently assign a MoSCoW level
  When the proposal is produced
  Then the item is included but flagged "needs Lead decision"
  And the reason is recorded in the task justification
```

```gherkin
Scenario: Produce the 5-block proposal output
  Given Layers 1–3 have run on the transcript
  When the agent emits the final output
  Then the output contains, in this order, five distinct blocks:
    1. Proposed sprint tasks  (title, phase, MoSCoW, confidence, effort or "estimate not available", justification, source excerpt)
    2. Out of sprint           (item, reason)
    3. Pending customer answers (concrete questions)
    4. Recorded decisions      (decision log, no tasks)
    5. Discard appendix        (noise items, with reason for discarding)
  And no item from the transcript is silently dropped — everything lands in exactly one block
```

```gherkin
Scenario: Explain an individual task
  Given a proposal has been produced and each task has a stable id
  When the FDE runs `explain <task-id>`
  Then the output shows:
    - the verbatim source excerpt(s) from the transcript
    - the Layer-1 classification applied
    - the Layer-2 enrichment used (reference task or "no match found")
    - the Layer-3 allocation reasoning (phase fit, dependencies)
    - the reason for the assigned confidence level
```

```gherkin
Scenario: Never invent an effort estimate
  Given an enrichment search returns no close historical reference
  When the agent fills the task fields
  Then the effort field is never a heuristic guess or model-fabricated number
  And the field reads exactly "estimate not available"
```

---

## Experience Design

- **User journey:**
  1. FDE leaves the meeting with the transcript saved as a plain-text file.
  2. FDE prepends a small header block to the file: project day, current phase, participants.
  3. FDE runs the CLI: `sprint-composer run <transcript.txt>`.
  4. CLI prints (and writes to a file) the 5-block proposal.
  5. FDE skims the proposal; for any item whose framing surprises them, they run `sprint-composer explain <task-id>` to see the source and the reasoning.
  6. FDE walks the proposal into the Lead review.

- **Interface — CLI in v0:**
  - Primary command: `sprint-composer run <transcript-path>` → prints the structured 5-block proposal to stdout and writes a machine-readable JSON sibling alongside.
  - Audit command: `sprint-composer explain <task-id>` → prints the source excerpt, classification path, and confidence reasoning for a single task.
  - Intermediate artifacts (Layer-1 JSON, enrichment matches) are written to disk so the demo can step through them.

- **Input format:**
  - Single transcript file. Header block at the top in YAML-ish form (`day:`, `phase:`, `participants: [...]`), followed by the dialogue.
  - If the header is missing or malformed, the CLI refuses to run and tells the FDE exactly what's missing — it never silently defaults.

- **Interface states:**
  - **Empty / no input:** clear usage message with an example command, no run.
  - **Loading:** short progress line per layer (`Layer 1: classifying…`, `Layer 2: enriching…`, etc.) so a 30-second run does not look frozen.
  - **Success:** the 5-block proposal printed to stdout, with a footer line stating where the JSON artifact was written.
  - **Error:** named, actionable errors (missing header field, unreadable file, malformed reference bank), never raw stack traces.

- **Non-negotiable principles:**
  - **The output is a proposal, not a decision.** The framing of every block makes this explicit ("Proposed sprint tasks", confidence per item, "needs Lead decision" flag where applicable).
  - **Nothing is silently dropped.** Every transcript segment lands in exactly one of the five output destinations — including noise in the discard appendix.
  - **Declare ignorance.** When effort can't be anchored, when MoSCoW can't be set with confidence, when information is missing — the agent says so concretely instead of guessing.
  - **Auditable by default.** Every task in the output is traceable back to a transcript excerpt via `explain`.

- **Accessibility:** CLI output is plain text (Markdown-friendly), readable in any terminal, screen-reader friendly. No reliance on color alone for confidence (HIGH/MEDIUM/LOW are word labels, not just colored badges).

---

## Business Constraints

- **Stakeholders requiring alignment:** Marco (builder / FDE candidate) and the Khal interview panel (acting as FDE Lead during the demo). No external customer in v0.
- **Non-negotiable business rules:**
  - Effort is **never** estimated without a concrete historical reference. No fabricated numbers, no model-guessed point values.
  - The agent never asserts a decision; it always presents a proposal with stated confidence.
  - The reference bank in v0 is synthetic but documented as such — the path to a real, indexed bank in v1 is explicit in the SPEC's notes.
- **Critical timeline:** Demo-ready by **Sunday night** (interview deliverable). The success bar is the four demo criteria above, satisfied on the synthetic transcript.

> Stack, model choice, libraries, infra, prompt structure, and similarity-search mechanics live in the Tech Spec.

---

## Out of Scope

- **Integration with Jira / ClickUp / Linear / any task tracker** — v0 output is text + JSON only. Reason: every minute spent on integrations is a minute not spent on the judgment layers, which are what the demo is actually selling.
- **Replacing the FDE Lead's decision authority** — the agent proposes, the human decides. Reason: false authority on human decisions is a stated risk in the briefing.
- **Estimating effort without a historical anchor** — a fabricated estimate is worse than no estimate. Reason: the field "estimate not available" + missing-information questions is treated as a strength, not a weakness.
- **Solving blockers detected in the transcript** — the agent only detects and logs them. Reason: blocker resolution is human work and out of scope for an extraction agent.
- **Live audio ingestion / on-the-fly transcription** — v0 expects an already-transcribed text file. Reason: transcription is a separate pipeline.
- **Multi-meeting aggregation** — v0 processes one meeting at a time. Reason: scope.
- **A real, indexed reference bank from past Khal squads** — v0 uses 4–5 plausible synthetic projects (healthcare / retail / BPO / fintech). Reason: no access to real historical data; v1 path documented but not built.
- **Web UI / dashboard / collaborative editing** — CLI only in v0. Reason: shortest path to demonstrating the four judgment layers.

---

## Ready to Plan?

- [x] Problem has a concrete, observable user pain (artisanal sprint reconstruction post-meeting)
- [x] Specific personas identified (FDE primary, FDE Lead validator)
- [x] Success metric is measurable and anchored (≤10 min Lead review; 4 demo criteria)
- [x] User stories cover happy path (run → 5-block proposal) and failure cases (no historical anchor, low-confidence classification, out-of-phase scope)
- [x] Acceptance criteria are observable (Given/When/Then scenarios over CLI output and the 5 blocks)
- [x] Out-of-scope is explicit (no Jira, no auto-decision, no fabricated estimates, no blocker resolution, no live transcription)
- [x] No stack, schema, or technical decisions included
