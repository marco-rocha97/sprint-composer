import os
from pathlib import Path

import pytest

from sprint_composer.layer3 import (
    AllocationError,
    _build_allocation_prompt,
    _extract_allocation,
    allocate_tasks,
)
from sprint_composer.models import (
    Confidence,
    EnrichedSegment,
    Layer2Result,
    ReferenceMatch,
    SegmentType,
    SprintAllocation,
)


# Test fixtures and helpers
class MockResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class MockGeminiClient:
    def __init__(self, responses: list[str]) -> None:
        self._iter = iter(responses)

    def generate_content(self, prompt: str) -> MockResponse:
        return MockResponse(next(self._iter))


# Load fixture files for integration tests
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TRANSCRIPT_PATH = FIXTURES_DIR / "transcript.txt"
REFERENCE_BANK_PATH = FIXTURES_DIR / "reference_bank.json"


def get_fixture_segments() -> list[str]:
    """Parse transcript body segments from fixture."""
    transcript_text = TRANSCRIPT_PATH.read_text()
    lines = transcript_text.split("\n")
    header_end = 0
    for i, line in enumerate(lines):
        if line.startswith("---"):
            header_end = i + 1
            break

    body = "\n".join(lines[header_end:]).strip()
    segments = [s.strip() for s in body.split("\n\n") if s.strip()]
    return segments


def create_sample_enriched_segment(
    segment_id: str,
    excerpt: str,
    effort: str = "5 days",
    blockers: list[str] | None = None,
    gap_questions: list[str] | None = None,
) -> EnrichedSegment:
    """Helper to create an EnrichedSegment for testing."""
    if blockers is None:
        blockers = []
    if gap_questions is None:
        gap_questions = []

    return EnrichedSegment(
        segment_id=segment_id,
        excerpt=excerpt,
        type=SegmentType.FIRM_REQUEST,
        l1_confidence=Confidence.HIGH,
        l1_reasoning="Clear request.",
        reference_match=ReferenceMatch(
            task_id="test-task",
            task_name="Test Task",
            project_id="test-proj",
            project_name="Test Project",
            effort_days=5,
            effort_confidence=Confidence.HIGH,
            blockers=blockers,
            notes="Test note.",
        ),
        effort=effort,
        confidence=Confidence.HIGH,
        blockers=blockers,
        gap_questions=gap_questions,
        enrichment_reasoning="Test enrichment.",
    )


# Unit tests
class TestBuildAllocationPrompt:
    def test_phase_name_appears_in_prompt(self) -> None:
        """Phase name appears in the prompt string."""
        enriched = [
            create_sample_enriched_segment(
                "S01",
                "We need SSO",
            )
        ]
        prompt = _build_allocation_prompt(enriched, "Simulation", 10)

        assert "Simulation" in prompt
        assert "day 10" in prompt.lower() or "Day: 10" in prompt

    def test_phase_description_appears_in_prompt(self) -> None:
        """Phase description is included in the prompt."""
        enriched = [create_sample_enriched_segment("S01", "We need SSO")]
        prompt = _build_allocation_prompt(enriched, "Simulation", 10)

        assert "UAT testing" in prompt

    def test_all_segment_ids_appear_in_prompt(self) -> None:
        """All input segment_ids appear in the tasks JSON block."""
        enriched = [
            create_sample_enriched_segment("S01", "We need SSO"),
            create_sample_enriched_segment("S02", "We need reporting"),
            create_sample_enriched_segment("S03", "We need auth"),
        ]
        prompt = _build_allocation_prompt(enriched, "Setup", 5)

        assert "S01" in prompt
        assert "S02" in prompt
        assert "S03" in prompt

    def test_effort_blockers_gap_questions_appear(self) -> None:
        """Effort, blockers, and gap_questions appear in the prompt."""
        enriched = [
            create_sample_enriched_segment(
                "S01",
                "We need SSO",
                effort="7 days",
                blockers=["Network setup", "Vendor cert"],
                gap_questions=[],
            )
        ]
        prompt = _build_allocation_prompt(enriched, "Discovery", 2)

        assert "7 days" in prompt
        assert "Network setup" in prompt
        assert "Vendor cert" in prompt

    def test_unknown_phase_raises_error(self) -> None:
        """Unknown phase raises AllocationError with valid phases listed."""
        enriched = [create_sample_enriched_segment("S01", "We need SSO")]

        with pytest.raises(AllocationError) as exc_info:
            _build_allocation_prompt(enriched, "InvalidPhase", 10)

        assert "InvalidPhase" in str(exc_info.value)
        assert "Discovery" in str(exc_info.value)
        assert "Setup" in str(exc_info.value)


class TestExtractAllocation:
    def test_valid_json_parsed_successfully(self) -> None:
        """Valid JSON response is parsed into (allocations, dependency_order)."""
        response = """{
          "allocations": [
            {
              "segment_id": "S01",
              "sprint_allocation": "in_sprint",
              "moscow": "Must",
              "allocation_confidence": "HIGH",
              "needs_lead_decision": false,
              "lead_decision_reason": "",
              "allocation_reasoning": "Critical."
            }
          ],
          "dependency_order": []
        }"""
        expected_ids = ["S01"]

        allocations, dep_order = _extract_allocation(response, expected_ids)

        assert len(allocations) == 1
        assert allocations[0]["segment_id"] == "S01"
        assert allocations[0]["moscow"] == "Must"

    def test_markdown_wrapped_json_parsed(self) -> None:
        """Markdown-wrapped JSON (```json ... ```) is parsed correctly."""
        response = """```json
{
  "allocations": [
    {
      "segment_id": "S01",
      "sprint_allocation": "in_sprint",
      "moscow": "Should",
      "allocation_confidence": "MEDIUM",
      "needs_lead_decision": false,
      "lead_decision_reason": "",
      "allocation_reasoning": "Needed."
    }
  ],
  "dependency_order": []
}
```"""
        expected_ids = ["S01"]

        allocations, dep_order = _extract_allocation(response, expected_ids)

        assert len(allocations) == 1
        assert allocations[0]["moscow"] == "Should"

    def test_missing_allocations_key_raises_error(self) -> None:
        """Missing 'allocations' key raises AllocationError."""
        response = '{"dependency_order": []}'
        expected_ids = ["S01"]

        with pytest.raises(AllocationError) as exc_info:
            _extract_allocation(response, expected_ids)

        assert "allocations" in str(exc_info.value).lower()

    def test_segment_id_not_in_expected_ids_raises_error(self) -> None:
        """Unexpected segment_id in response raises AllocationError."""
        response = """{
          "allocations": [
            {
              "segment_id": "S99",
              "sprint_allocation": "in_sprint",
              "moscow": "Must",
              "allocation_confidence": "HIGH",
              "needs_lead_decision": false,
              "lead_decision_reason": "",
              "allocation_reasoning": "X."
            }
          ],
          "dependency_order": []
        }"""
        expected_ids = ["S01"]

        with pytest.raises(AllocationError) as exc_info:
            _extract_allocation(response, expected_ids)

        assert "S99" in str(exc_info.value) or "Unexpected" in str(exc_info.value)

    def test_missing_segment_id_in_response_raises_error(self) -> None:
        """Missing segment_id in response raises AllocationError."""
        response = """{
          "allocations": [
            {
              "segment_id": "S01",
              "sprint_allocation": "in_sprint",
              "moscow": "Must",
              "allocation_confidence": "HIGH",
              "needs_lead_decision": false,
              "lead_decision_reason": "",
              "allocation_reasoning": "X."
            }
          ],
          "dependency_order": []
        }"""
        expected_ids = ["S01", "S02"]

        with pytest.raises(AllocationError) as exc_info:
            _extract_allocation(response, expected_ids)

        assert "S02" in str(exc_info.value) or "Missing" in str(exc_info.value)

    def test_invalid_moscow_value_raises_error(self) -> None:
        """Invalid moscow value raises AllocationError."""
        response = """{
          "allocations": [
            {
              "segment_id": "S01",
              "sprint_allocation": "in_sprint",
              "moscow": "MUST",
              "allocation_confidence": "HIGH",
              "needs_lead_decision": false,
              "lead_decision_reason": "",
              "allocation_reasoning": "X."
            }
          ],
          "dependency_order": []
        }"""
        expected_ids = ["S01"]

        with pytest.raises(AllocationError) as exc_info:
            _extract_allocation(response, expected_ids)

        assert "moscow" in str(exc_info.value).lower()

    def test_invalid_sprint_allocation_value_raises_error(self) -> None:
        """Invalid sprint_allocation value raises AllocationError."""
        response = """{
          "allocations": [
            {
              "segment_id": "S01",
              "sprint_allocation": "maybe",
              "moscow": "Must",
              "allocation_confidence": "HIGH",
              "needs_lead_decision": false,
              "lead_decision_reason": "",
              "allocation_reasoning": "X."
            }
          ],
          "dependency_order": []
        }"""
        expected_ids = ["S01"]

        with pytest.raises(AllocationError) as exc_info:
            _extract_allocation(response, expected_ids)

        assert "sprint_allocation" in str(exc_info.value).lower()

    def test_invalid_confidence_value_raises_error(self) -> None:
        """Invalid allocation_confidence value raises AllocationError."""
        response = """{
          "allocations": [
            {
              "segment_id": "S01",
              "sprint_allocation": "in_sprint",
              "moscow": "Must",
              "allocation_confidence": "UNCERTAIN",
              "needs_lead_decision": false,
              "lead_decision_reason": "",
              "allocation_reasoning": "X."
            }
          ],
          "dependency_order": []
        }"""
        expected_ids = ["S01"]

        with pytest.raises(AllocationError) as exc_info:
            _extract_allocation(response, expected_ids)

        assert "confidence" in str(exc_info.value).lower()

    def test_absent_dependency_order_returns_empty_list(self) -> None:
        """Absent 'dependency_order' key returns empty list (no error)."""
        response = """{
          "allocations": [
            {
              "segment_id": "S01",
              "sprint_allocation": "in_sprint",
              "moscow": "Must",
              "allocation_confidence": "HIGH",
              "needs_lead_decision": false,
              "lead_decision_reason": "",
              "allocation_reasoning": "X."
            }
          ]
        }"""
        expected_ids = ["S01"]

        allocations, dep_order = _extract_allocation(response, expected_ids)

        assert len(allocations) == 1
        assert dep_order == []


class TestMergeResults:
    def test_out_of_sprint_tasks_have_zero_dependency_order(self) -> None:
        """Out-of-sprint tasks have dependency_order == 0."""
        enriched = [
            create_sample_enriched_segment("S01", "We need reporting"),
            create_sample_enriched_segment("S02", "We need SSO"),
        ]
        allocations = [
            {
                "segment_id": "S01",
                "sprint_allocation": "out_of_sprint",
                "moscow": "Should",
                "allocation_confidence": "HIGH",
                "needs_lead_decision": False,
                "lead_decision_reason": "",
                "allocation_reasoning": "Out of phase.",
            },
            {
                "segment_id": "S02",
                "sprint_allocation": "in_sprint",
                "moscow": "Must",
                "allocation_confidence": "HIGH",
                "needs_lead_decision": False,
                "lead_decision_reason": "",
                "allocation_reasoning": "Critical.",
            },
        ]
        dependency_order = [{"segment_id": "S02", "position": 1}]

        from sprint_composer.layer3 import _merge_results

        result = _merge_results(enriched, allocations, dependency_order)

        out_tasks = result.out_of_sprint
        assert len(out_tasks) == 1
        assert out_tasks[0].segment_id == "S01"
        assert out_tasks[0].dependency_order == 0

    def test_in_sprint_tasks_sorted_by_dependency_order(self) -> None:
        """In-sprint tasks are sorted ascending by dependency_order."""
        enriched = [
            create_sample_enriched_segment("S01", "Task 1"),
            create_sample_enriched_segment("S02", "Task 2"),
            create_sample_enriched_segment("S03", "Task 3"),
        ]
        allocations = [
            {
                "segment_id": "S01",
                "sprint_allocation": "in_sprint",
                "moscow": "Should",
                "allocation_confidence": "HIGH",
                "needs_lead_decision": False,
                "lead_decision_reason": "",
                "allocation_reasoning": "X.",
            },
            {
                "segment_id": "S02",
                "sprint_allocation": "in_sprint",
                "moscow": "Must",
                "allocation_confidence": "HIGH",
                "needs_lead_decision": False,
                "lead_decision_reason": "",
                "allocation_reasoning": "Y.",
            },
            {
                "segment_id": "S03",
                "sprint_allocation": "in_sprint",
                "moscow": "Could",
                "allocation_confidence": "HIGH",
                "needs_lead_decision": False,
                "lead_decision_reason": "",
                "allocation_reasoning": "Z.",
            },
        ]
        dependency_order = [
            {"segment_id": "S02", "position": 1},
            {"segment_id": "S03", "position": 2},
            {"segment_id": "S01", "position": 3},
        ]

        from sprint_composer.layer3 import _merge_results

        result = _merge_results(enriched, allocations, dependency_order)

        in_tasks = result.in_sprint
        assert [t.segment_id for t in in_tasks] == ["S02", "S03", "S01"]
        assert [t.dependency_order for t in in_tasks] == [1, 2, 3]

    def test_all_l1_l2_fields_preserved_verbatim(self) -> None:
        """All L1/L2 fields on AllocatedTask match source EnrichedSegment."""
        match = ReferenceMatch(
            task_id="sso-ldap",
            task_name="SSO via LDAP",
            project_id="proj-1",
            project_name="Project One",
            effort_days=5,
            effort_confidence=Confidence.HIGH,
            blockers=["Network setup"],
            notes="Test note",
        )
        enriched_seg = EnrichedSegment(
            segment_id="S01",
            excerpt="We need SSO",
            type=SegmentType.FIRM_REQUEST,
            l1_confidence=Confidence.HIGH,
            l1_reasoning="Clear request.",
            reference_match=match,
            effort="5 days",
            confidence=Confidence.HIGH,
            blockers=["Network setup"],
            gap_questions=[],
            enrichment_reasoning="Matched to reference.",
        )

        allocations = [
            {
                "segment_id": "S01",
                "sprint_allocation": "in_sprint",
                "moscow": "Must",
                "allocation_confidence": "HIGH",
                "needs_lead_decision": False,
                "lead_decision_reason": "",
                "allocation_reasoning": "Critical.",
            }
        ]
        dependency_order = [{"segment_id": "S01", "position": 1}]

        from sprint_composer.layer3 import _merge_results

        result = _merge_results([enriched_seg], allocations, dependency_order)

        task = result.in_sprint[0]
        assert task.segment_id == "S01"
        assert task.excerpt == "We need SSO"
        assert task.type == SegmentType.FIRM_REQUEST
        assert task.l1_confidence == Confidence.HIGH
        assert task.l1_reasoning == "Clear request."
        assert task.reference_match == match
        assert task.effort == "5 days"
        assert task.l2_confidence == Confidence.HIGH
        assert task.blockers == ["Network setup"]
        assert task.gap_questions == []
        assert task.enrichment_reasoning == "Matched to reference."

    def test_needs_lead_decision_true_implies_non_empty_reason(self) -> None:
        """needs_lead_decision=True implies lead_decision_reason is non-empty."""
        enriched = [create_sample_enriched_segment("S01", "Unclear request")]
        allocations = [
            {
                "segment_id": "S01",
                "sprint_allocation": "in_sprint",
                "moscow": "Should",
                "allocation_confidence": "LOW",
                "needs_lead_decision": True,
                "lead_decision_reason": "Unclear business value.",
                "allocation_reasoning": "Needs clarification.",
            }
        ]
        dependency_order = [{"segment_id": "S01", "position": 1}]

        from sprint_composer.layer3 import _merge_results

        result = _merge_results(enriched, allocations, dependency_order)

        task = result.in_sprint[0]
        assert task.needs_lead_decision is True
        assert len(task.lead_decision_reason) > 0

    def test_needs_lead_decision_false_implies_empty_reason(self) -> None:
        """needs_lead_decision=False implies lead_decision_reason is empty string."""
        enriched = [create_sample_enriched_segment("S01", "Clear request")]
        allocations = [
            {
                "segment_id": "S01",
                "sprint_allocation": "in_sprint",
                "moscow": "Must",
                "allocation_confidence": "HIGH",
                "needs_lead_decision": False,
                "lead_decision_reason": "",
                "allocation_reasoning": "Critical.",
            }
        ]
        dependency_order = [{"segment_id": "S01", "position": 1}]

        from sprint_composer.layer3 import _merge_results

        result = _merge_results(enriched, allocations, dependency_order)

        task = result.in_sprint[0]
        assert task.needs_lead_decision is False
        assert task.lead_decision_reason == ""


class TestAllocateTasks:
    def test_in_sprint_task_properties(self) -> None:
        """In-sprint task has correct sprint_allocation and dependency_order >= 1."""
        enriched = [create_sample_enriched_segment("S01", "We need SSO")]
        layer2_result = Layer2Result(enriched=enriched)

        response_json = """{
          "allocations": [
            {
              "segment_id": "S01",
              "sprint_allocation": "in_sprint",
              "moscow": "Must",
              "allocation_confidence": "HIGH",
              "needs_lead_decision": false,
              "lead_decision_reason": "",
              "allocation_reasoning": "Critical integration."
            }
          ],
          "dependency_order": [
            {"segment_id": "S01", "position": 1}
          ]
        }"""
        client = MockGeminiClient([response_json])

        result = allocate_tasks(layer2_result, "Simulation", 10, client=client)

        assert len(result.in_sprint) == 1
        task = result.in_sprint[0]
        assert task.sprint_allocation == SprintAllocation.IN_SPRINT
        assert task.dependency_order >= 1

    def test_out_of_sprint_task_properties(self) -> None:
        """Out-of-sprint task has correct allocation and dependency_order == 0."""
        enriched = [create_sample_enriched_segment("S01", "We need admin dashboard")]
        layer2_result = Layer2Result(enriched=enriched)

        response_json = """{
          "allocations": [
            {
              "segment_id": "S01",
              "sprint_allocation": "out_of_sprint",
              "moscow": "Should",
              "allocation_confidence": "HIGH",
              "needs_lead_decision": false,
              "lead_decision_reason": "",
              "allocation_reasoning": "New feature incompatible with Simulation phase."
            }
          ],
          "dependency_order": []
        }"""
        client = MockGeminiClient([response_json])

        result = allocate_tasks(layer2_result, "Simulation", 10, client=client)

        assert len(result.out_of_sprint) == 1
        task = result.out_of_sprint[0]
        assert task.sprint_allocation == SprintAllocation.OUT_OF_SPRINT
        assert task.dependency_order == 0

    def test_needs_lead_decision_non_empty_reason(self) -> None:
        """needs_lead_decision=True has non-empty lead_decision_reason."""
        enriched = [create_sample_enriched_segment("S01", "Unclear request")]
        layer2_result = Layer2Result(enriched=enriched)

        response_json = """{
          "allocations": [
            {
              "segment_id": "S01",
              "sprint_allocation": "in_sprint",
              "moscow": "Could",
              "allocation_confidence": "LOW",
              "needs_lead_decision": true,
              "lead_decision_reason": "Business value unclear without stakeholder input.",
              "allocation_reasoning": "Requires lead decision."
            }
          ],
          "dependency_order": [{"segment_id": "S01", "position": 1}]
        }"""
        client = MockGeminiClient([response_json])

        result = allocate_tasks(layer2_result, "Discovery", 1, client=client)

        task = result.in_sprint[0]
        assert task.needs_lead_decision is True
        assert len(task.lead_decision_reason) > 0

    def test_all_enriched_segment_fields_preserved(self) -> None:
        """All EnrichedSegment fields are preserved verbatim on AllocatedTask."""
        match = ReferenceMatch(
            task_id="sso-ldap",
            task_name="SSO via LDAP",
            project_id="proj-1",
            project_name="Project One",
            effort_days=5,
            effort_confidence=Confidence.HIGH,
            blockers=["Network setup"],
            notes="Historical data",
        )
        enriched = [
            EnrichedSegment(
                segment_id="S01",
                excerpt="We need SSO",
                type=SegmentType.FIRM_REQUEST,
                l1_confidence=Confidence.HIGH,
                l1_reasoning="Clear request.",
                reference_match=match,
                effort="5 days",
                confidence=Confidence.HIGH,
                blockers=["Network setup"],
                gap_questions=[],
                enrichment_reasoning="Matched to reference.",
            )
        ]
        layer2_result = Layer2Result(enriched=enriched)

        response_json = """{
          "allocations": [
            {
              "segment_id": "S01",
              "sprint_allocation": "in_sprint",
              "moscow": "Must",
              "allocation_confidence": "HIGH",
              "needs_lead_decision": false,
              "lead_decision_reason": "",
              "allocation_reasoning": "Critical."
            }
          ],
          "dependency_order": [{"segment_id": "S01", "position": 1}]
        }"""
        client = MockGeminiClient([response_json])

        result = allocate_tasks(layer2_result, "Setup", 5, client=client)

        task = result.in_sprint[0]
        assert task.effort == "5 days"
        assert task.blockers == ["Network setup"]
        assert task.reference_match == match


@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
class TestIntegration:
    def test_s03_routes_to_out_of_sprint_on_simulation_phase(self) -> None:
        """S03 (admin dashboard) in Simulation phase routes to out_of_sprint."""
        from sprint_composer.layer1 import classify_transcript
        from sprint_composer.layer2 import enrich_segments

        # Get fixture segments
        segments = get_fixture_segments()

        # Run L1 classification
        l1_result = classify_transcript(segments)

        # Run L2 enrichment
        l2_result = enrich_segments(l1_result)

        # Run L3 allocation (Simulation, day 10)
        l3_result = allocate_tasks(l2_result, "Simulation", 10)

        s03_tasks = [t for t in l3_result.out_of_sprint if t.segment_id == "S03"]
        if s03_tasks:
            assert len(s03_tasks) == 1
            task = s03_tasks[0]
            assert task.sprint_allocation == SprintAllocation.OUT_OF_SPRINT
            assert (
                "Simulation" in task.allocation_reasoning
                or "phase" in task.allocation_reasoning.lower()
            )

    def test_s01_routes_to_in_sprint_with_must_priority(self) -> None:
        """S01 (SSO) routes to in_sprint with Must priority."""
        from sprint_composer.layer1 import classify_transcript
        from sprint_composer.layer2 import enrich_segments

        segments = get_fixture_segments()
        l1_result = classify_transcript(segments)
        l2_result = enrich_segments(l1_result)
        l3_result = allocate_tasks(l2_result, "Simulation", 10)

        s01_tasks = [t for t in l3_result.in_sprint if t.segment_id == "S01"]
        if s01_tasks:
            assert len(s01_tasks) == 1
            task = s01_tasks[0]
            assert task.sprint_allocation == SprintAllocation.IN_SPRINT

    def test_at_least_one_needs_lead_decision_or_low_confidence(self) -> None:
        """At least one task has needs_lead_decision=True or LOW confidence."""
        from sprint_composer.layer1 import classify_transcript
        from sprint_composer.layer2 import enrich_segments

        segments = get_fixture_segments()
        l1_result = classify_transcript(segments)
        l2_result = enrich_segments(l1_result)
        l3_result = allocate_tasks(l2_result, "Simulation", 10)

        all_tasks = l3_result.in_sprint + l3_result.out_of_sprint
        decision_or_low = any(
            t.needs_lead_decision or t.allocation_confidence == Confidence.LOW for t in all_tasks
        )
        assert decision_or_low

    def test_in_sprint_sorted_by_dependency_order(self) -> None:
        """In-sprint tasks are sorted ascending by dependency_order."""
        from sprint_composer.layer1 import classify_transcript
        from sprint_composer.layer2 import enrich_segments

        segments = get_fixture_segments()
        l1_result = classify_transcript(segments)
        l2_result = enrich_segments(l1_result)
        l3_result = allocate_tasks(l2_result, "Simulation", 10)

        in_tasks = l3_result.in_sprint
        if len(in_tasks) > 1:
            orders = [t.dependency_order for t in in_tasks]
            assert orders == sorted(orders)

    def test_every_segment_in_one_output_list(self) -> None:
        """Every EnrichedSegment appears in exactly one of in_sprint or out_of_sprint."""
        from sprint_composer.layer1 import classify_transcript
        from sprint_composer.layer2 import enrich_segments

        segments = get_fixture_segments()
        l1_result = classify_transcript(segments)
        l2_result = enrich_segments(l1_result)
        l3_result = allocate_tasks(l2_result, "Simulation", 10)

        expected_ids = {seg.segment_id for seg in l2_result.enriched}
        result_ids = {t.segment_id for t in l3_result.in_sprint + l3_result.out_of_sprint}

        assert expected_ids == result_ids
