import json
import os
import re
import warnings
from typing import Any, Protocol

warnings.filterwarnings("ignore", category=FutureWarning)

import google.generativeai as genai  # noqa: E402

from sprint_composer.models import (  # noqa: E402
    AllocatedTask,
    Confidence,
    EnrichedSegment,
    Layer2Result,
    Layer3Result,
    MoSCoW,
    SprintAllocation,
)


class AllocationError(Exception):
    """Raised when Gemini response is unparseable or structurally invalid."""

    pass


class _GenerateResponse(Protocol):
    @property
    def text(self) -> str: ...


class _GeneratorProtocol(Protocol):
    def generate_content(self, prompt: str) -> _GenerateResponse: ...


KHAL_PHASES: dict[str, str] = {
    "Discovery": (
        "Requirements gathering, scoping, architecture decisions, stakeholder alignment "
        "(days 1–3). New features, new integrations, and major scope items are all appropriate."
    ),
    "Configuration": (
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


def _build_default_client() -> _GeneratorProtocol:
    """
    Build and return a Gemini client from GEMINI_API_KEY env var.

    Raises EnvironmentError if GEMINI_API_KEY is not set.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set. Add it to your .env file.")

    genai.configure(api_key=api_key)  # type: ignore[attr-defined]
    return genai.GenerativeModel("gemini-3.1-flash-lite")  # type: ignore


def _build_allocation_prompt(enriched: list[EnrichedSegment], phase: str, day: int) -> str:
    """
    Construct the batch prompt with phase context + all enriched tasks as JSON.

    Raises AllocationError if phase not in KHAL_PHASES.
    """
    if phase not in KHAL_PHASES:
        valid_phases = ", ".join(KHAL_PHASES.keys())
        raise AllocationError(f"Unrecognized phase: '{phase}'. Valid phases: {valid_phases}")

    phase_description = KHAL_PHASES[phase]

    # Discovery is a planning phase — add planning semantics note
    discovery_note = ""
    if phase == "Discovery":
        discovery_note = (
            "\nIMPORTANT — PLANNING PHASE SEMANTICS: The current phase is Discovery (days 1–3). "
            "Discovery is a planning phase — no features are implemented during Discovery. "
            'Classify tasks as "in_sprint" to mean "accepted into the Configuration plan (days 4–7)" '
            "— they will be built during Configuration, not during this Discovery session. "
            "The allocation_reasoning for in-sprint items must say 'Proposed for Configuration (days 4–7)' "
            "rather than implying implementation during Discovery. "
            "A task is out_of_sprint only if it is inappropriate for Configuration (e.g., needs a phase "
            "beyond Configuration, has an unbounded information gap, or introduces scope beyond the "
            "15-day cycle).\n"
        )

    tasks_json_list = []
    for segment in enriched:
        task_dict = {
            "segment_id": segment.segment_id,
            "type": segment.type.value,
            "excerpt": segment.excerpt,
            "effort": segment.effort,
            "blockers": segment.blockers,
            "gap_questions": segment.gap_questions,
        }
        tasks_json_list.append(task_dict)

    tasks_json = json.dumps(tasks_json_list, indent=2)

    prompt = f"""You are a sprint planner for a software delivery team operating on Khal's 15-day delivery cycle.

Current context:
- Day: {day}
- Phase: {phase}
- Phase description: {phase_description}

Phase compatibility rules:
- Discovery (days 1–3): new features, new integrations, and major scope items are appropriate
- Configuration (days 4–7): new feature development and core integrations are appropriate
- Simulation (days 8–12): UAT testing and refinements to EXISTING features only — new scope is incompatible
- Go-live (days 13–15): only critical production fixes are appropriate; new features are out-of-scope
{discovery_note}
Tasks to allocate (each enriched with effort and blockers from historical data):
{tasks_json}

For each task, determine:
1. sprint_allocation: "in_sprint" if compatible with the current phase; "out_of_sprint" if it introduces new scope incompatible with {phase}
2. moscow: one of "Must", "Should", "Could", "Won't" — based on urgency, blockers, and phase fit
3. allocation_confidence: "HIGH", "MEDIUM", or "LOW" — how certain you are
4. needs_lead_decision: true if MoSCoW level cannot be confidently assigned from available signals; false otherwise
5. lead_decision_reason: the specific reason if needs_lead_decision is true; "" (empty string) otherwise
6. allocation_reasoning: one sentence — why this MoSCoW and allocation
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

Also identify cross-task dependencies: if Task X must be completed before Task Y, include this in dependency_order.

Return ONLY a valid JSON object (no markdown, no explanation):
{{
  "allocations": [
    {{
      "segment_id": "<id>",
      "sprint_allocation": "in_sprint" | "out_of_sprint",
      "moscow": "Must" | "Should" | "Could" | "Won't",
      "allocation_confidence": "HIGH" | "MEDIUM" | "LOW",
      "needs_lead_decision": true | false,
      "lead_decision_reason": "<reason or empty string>",
      "allocation_reasoning": "<one sentence>",
      "scope_creep_category": "<prerequisite_risk|deferred_v2|deferred_phase|information_gap|>",
      "scope_creep_impact": "<one sentence or empty string>"
    }}
  ],
  "dependency_order": [
    {{"segment_id": "<id>", "position": <int>}}
  ]
}}"""

    return prompt


def _extract_allocation(
    response_text: str,
    expected_ids: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Parse Gemini's JSON response → (allocations_list, dependency_order_list).

    Strips markdown wrapper if present.
    Raises AllocationError if:
      - JSON is unparseable
      - "allocations" key is missing
      - Any segment_id in the response is not in expected_ids
      - Any segment_id in expected_ids is absent from the response
      - Any "moscow", "sprint_allocation", or "allocation_confidence" value is invalid
    """
    # Strip markdown code fence wrappers if present
    stripped = re.sub(r"^```(?:json)?\s*", "", response_text, flags=re.MULTILINE)
    stripped = re.sub(r"\s*```$", "", stripped, flags=re.MULTILINE)

    # Extract JSON object using regex
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", stripped)
    if not match:
        raise AllocationError(f"No JSON object found in response: {response_text[:100]}")

    json_str = match.group(0)
    try:
        data = json.loads(json_str)
        if not isinstance(data, dict):
            raise AllocationError(f"Expected JSON object, got {type(data).__name__}")
    except json.JSONDecodeError as e:
        raise AllocationError(f"Invalid JSON: {json_str} — {e}")

    if "allocations" not in data:
        raise AllocationError("Missing 'allocations' key in response")

    allocations_raw = data.get("allocations", [])
    if not isinstance(allocations_raw, list):
        raise AllocationError(
            f"Expected 'allocations' to be a list, got {type(allocations_raw).__name__}"
        )

    dependency_order_raw = data.get("dependency_order", [])
    if not isinstance(dependency_order_raw, list):
        dependency_order_raw = []

    returned_ids = set()
    valid_moscow_values = {"Must", "Should", "Could", "Won't"}
    valid_sprint_alloc_values = {"in_sprint", "out_of_sprint"}
    valid_conf_values = {"HIGH", "MEDIUM", "LOW"}

    for alloc in allocations_raw:
        if not isinstance(alloc, dict):
            raise AllocationError(f"Expected allocation dict, got {type(alloc).__name__}")

        segment_id = alloc.get("segment_id")
        if segment_id not in expected_ids:
            raise AllocationError(
                f"Unexpected segment_id in response: '{segment_id}' not in expected ids"
            )
        returned_ids.add(segment_id)

        moscow_val = alloc.get("moscow")
        if moscow_val not in valid_moscow_values:
            raise AllocationError(
                f"Invalid moscow value for {segment_id}: '{moscow_val}'. "
                f"Must be one of {valid_moscow_values}"
            )

        sprint_alloc_val = alloc.get("sprint_allocation")
        if sprint_alloc_val not in valid_sprint_alloc_values:
            raise AllocationError(
                f"Invalid sprint_allocation value for {segment_id}: '{sprint_alloc_val}'. "
                f"Must be one of {valid_sprint_alloc_values}"
            )

        conf_val = alloc.get("allocation_confidence")
        if conf_val not in valid_conf_values:
            raise AllocationError(
                f"Invalid allocation_confidence value for {segment_id}: '{conf_val}'. "
                f"Must be one of {valid_conf_values}"
            )

        scope_creep_category = alloc.get("scope_creep_category", "")
        valid_scope_creep_categories = {
            "prerequisite_risk",
            "deferred_v2",
            "deferred_phase",
            "information_gap",
            "",
        }
        if scope_creep_category not in valid_scope_creep_categories:
            raise AllocationError(
                f"Invalid scope_creep_category for {segment_id}: '{scope_creep_category}'. "
                f"Must be one of {valid_scope_creep_categories}"
            )

    missing_ids = set(expected_ids) - returned_ids
    if missing_ids:
        raise AllocationError(f"Missing segment_ids in response: {', '.join(sorted(missing_ids))}")

    return allocations_raw, dependency_order_raw


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
    if client is None:
        client = _build_default_client()

    enriched = layer2_result.enriched
    expected_ids = [seg.segment_id for seg in enriched]

    prompt = _build_allocation_prompt(enriched, phase, day)
    response = client.generate_content(prompt)
    allocations, dependency_order = _extract_allocation(response.text, expected_ids)

    return _merge_results(enriched, allocations, dependency_order)


def _merge_results(
    enriched: list[EnrichedSegment],
    allocations: list[dict[str, Any]],
    dependency_order: list[dict[str, Any]],
) -> Layer3Result:
    """
    Construct one AllocatedTask per EnrichedSegment.

    Sets dependency_order=0 for out_of_sprint tasks.
    For in_sprint tasks: uses position from dependency_order list if present;
    falls back to input order (segment_id order) for tasks not mentioned.
    Returns Layer3Result with in_sprint sorted ascending by dependency_order,
    out_of_sprint sorted ascending by segment_id.
    """
    alloc_by_id = {a["segment_id"]: a for a in allocations}

    dep_order_by_id: dict[str, int] = {}
    for dep_entry in dependency_order:
        if isinstance(dep_entry, dict):
            seg_id = dep_entry.get("segment_id")
            pos = dep_entry.get("position")
            if seg_id and isinstance(pos, int):
                dep_order_by_id[seg_id] = pos

    allocated_tasks: list[AllocatedTask] = []

    for segment in enriched:
        alloc = alloc_by_id[segment.segment_id]

        moscow_str = alloc["moscow"]
        moscow = MoSCoW(moscow_str)

        sprint_alloc_str = alloc["sprint_allocation"]
        sprint_allocation = SprintAllocation(sprint_alloc_str)

        conf_str = alloc["allocation_confidence"]
        allocation_confidence = Confidence(conf_str)

        needs_lead = alloc.get("needs_lead_decision", False)
        lead_reason = alloc.get("lead_decision_reason", "")

        if needs_lead and not lead_reason:
            lead_reason = f"MoSCoW cannot be confidently assigned ({moscow_str})"

        if not needs_lead:
            lead_reason = ""

        allocation_reasoning = alloc.get("allocation_reasoning", "")
        scope_creep_category = alloc.get("scope_creep_category", "")
        scope_creep_impact = alloc.get("scope_creep_impact", "")

        if sprint_allocation == SprintAllocation.OUT_OF_SPRINT:
            dependency_pos = 0
        else:
            dependency_pos = dep_order_by_id.get(segment.segment_id, 0)

        task = AllocatedTask(
            segment_id=segment.segment_id,
            excerpt=segment.excerpt,
            type=segment.type,
            l1_confidence=segment.l1_confidence,
            l1_reasoning=segment.l1_reasoning,
            reference_match=segment.reference_match,
            effort=segment.effort,
            l2_confidence=segment.confidence,
            blockers=segment.blockers,
            gap_questions=segment.gap_questions,
            enrichment_reasoning=segment.enrichment_reasoning,
            moscow=moscow,
            sprint_allocation=sprint_allocation,
            allocation_confidence=allocation_confidence,
            dependency_order=dependency_pos,
            needs_lead_decision=needs_lead,
            lead_decision_reason=lead_reason,
            allocation_reasoning=allocation_reasoning,
            scope_creep_category=scope_creep_category,
            scope_creep_impact=scope_creep_impact,
        )
        allocated_tasks.append(task)

    in_sprint_tasks = [
        t for t in allocated_tasks if t.sprint_allocation == SprintAllocation.IN_SPRINT
    ]
    out_of_sprint_tasks = [
        t for t in allocated_tasks if t.sprint_allocation == SprintAllocation.OUT_OF_SPRINT
    ]

    in_sprint_tasks.sort(key=lambda t: t.dependency_order)
    out_of_sprint_tasks.sort(key=lambda t: t.segment_id)

    return Layer3Result(in_sprint=in_sprint_tasks, out_of_sprint=out_of_sprint_tasks)
