import os
from pathlib import Path

import pytest

from sprint_composer.layer2 import (
    EnrichmentError,
    _extract_gap_questions,
    _find_best_match,
    _load_reference_bank,
    _score_task,
    enrich_segments,
)
from sprint_composer.models import (
    ClassifiedSegment,
    Confidence,
    Layer1Result,
    SegmentType,
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
    # Skip header (day, phase, participants, ---)
    lines = transcript_text.split("\n")
    header_end = 0
    for i, line in enumerate(lines):
        if line.startswith("---"):
            header_end = i + 1
            break

    body = "\n".join(lines[header_end:]).strip()
    segments = [s.strip() for s in body.split("\n\n") if s.strip()]
    return segments


def load_reference_bank_fixture() -> dict:
    """Load the reference bank fixture."""
    return _load_reference_bank(REFERENCE_BANK_PATH)


# Unit tests
class TestKeywordScoring:
    def test_score_task_returns_zero_for_empty_keywords(self) -> None:
        """_score_task returns 0 for empty keyword list."""
        excerpt = "Single Sign-On integration with Active Directory"
        score = _score_task(excerpt, [])
        assert score == 0

    def test_score_task_returns_zero_when_no_keyword_matches(self) -> None:
        """_score_task returns 0 when no keyword appears in excerpt."""
        excerpt = "IoT glucose monitor integration"
        keywords = ["sso", "active directory", "ldap"]
        score = _score_task(excerpt, keywords)
        assert score == 0

    def test_score_task_is_case_insensitive(self) -> None:
        """_score_task is case-insensitive ('Active Directory' vs 'active directory')."""
        excerpt = "We need Single Sign-On integration with Active Directory"
        keywords = ["sign-on", "active directory"]
        score = _score_task(excerpt, keywords)
        assert score == 2

    def test_score_task_counts_distinct_hits(self) -> None:
        """_score_task counts only distinct keyword hits (not frequency)."""
        excerpt = "SSO SSO SSO authentication"
        keywords = ["sso", "authentication"]
        score = _score_task(excerpt, keywords)
        # sso appears 3 times but counts as 1 distinct hit; authentication is 1 hit
        assert score == 2


class TestFindBestMatch:
    def test_s01_excerpt_matches_sso_ldap_integration(self) -> None:
        """S01 excerpt (SSO + Active Directory) matches 'sso-ldap-integration'."""
        bank = load_reference_bank_fixture()
        excerpt = "Single Sign-On integration with our Active Directory"
        best_match = _find_best_match(excerpt, bank)

        assert best_match is not None
        assert best_match.task_id == "sso-ldap-integration"
        assert best_match.effort_days == 5
        assert best_match.effort_confidence == Confidence.HIGH

    def test_s04_excerpt_iot_glucose_returns_none(self) -> None:
        """S04 excerpt (IoT glucose monitor) returns None (no match in bank)."""
        bank = load_reference_bank_fixture()
        excerpt = "integrate with an IoT glucose monitor"
        best_match = _find_best_match(excerpt, bank)

        assert best_match is None

    def test_tie_scenario_first_project_first_task_wins(self) -> None:
        """Tie scenario: two tasks with equal score -> first project, first task wins."""
        bank = {
            "projects": [
                {
                    "id": "proj-a",
                    "name": "Project A",
                    "tasks": [
                        {
                            "id": "task-a1",
                            "name": "Task A1",
                            "keywords": ["dashboard", "reporting"],
                            "effort_days": 5,
                            "effort_confidence": "HIGH",
                            "blockers": [],
                            "notes": "",
                        }
                    ],
                },
                {
                    "id": "proj-b",
                    "name": "Project B",
                    "tasks": [
                        {
                            "id": "task-b1",
                            "name": "Task B1",
                            "keywords": ["dashboard", "analytics"],
                            "effort_days": 10,
                            "effort_confidence": "MEDIUM",
                            "blockers": [],
                            "notes": "",
                        }
                    ],
                },
            ]
        }
        # Both tasks match on "dashboard"; both have score 1
        excerpt = "We need a dashboard"
        best_match = _find_best_match(excerpt, bank)

        assert best_match is not None
        assert best_match.task_id == "task-a1"  # First project, first task


class TestExtractGapQuestions:
    def test_valid_json_response_extracted(self) -> None:
        """Valid JSON response is parsed correctly."""
        response_text = '{"questions": ["Question 1?", "Question 2?", "Question 3?"]}'
        questions = _extract_gap_questions(response_text)

        assert len(questions) >= 3
        assert "Question 1?" in questions
        assert "Question 2?" in questions
        assert "Question 3?" in questions

    def test_markdown_wrapped_json_parsed(self) -> None:
        """Markdown-wrapped JSON (```json...```) is correctly parsed."""
        response_text = """```json
{"questions": ["Q1?", "Q2?", "Q3?"]}
```"""
        questions = _extract_gap_questions(response_text)

        assert len(questions) >= 3
        assert "Q1?" in questions

    def test_fewer_than_3_questions_padded_with_fallback(self) -> None:
        """Fewer than 3 questions padded with fallback to reach 3."""
        response_text = '{"questions": ["Only one?"]}'
        questions = _extract_gap_questions(response_text)

        assert len(questions) >= 3
        assert "Only one?" in questions

    def test_more_than_4_questions_truncated_to_4(self) -> None:
        """More than 4 questions truncated to 4."""
        response_text = '{"questions": ["Q1?", "Q2?", "Q3?", "Q4?", "Q5?"]}'
        questions = _extract_gap_questions(response_text)

        assert len(questions) == 4

    def test_unparseable_response_returns_fallback(self) -> None:
        """Unparseable response returns fallback list, no exception."""
        response_text = "oops"
        questions = _extract_gap_questions(response_text)

        assert len(questions) >= 3
        assert all(isinstance(q, str) for q in questions)


class TestEnrichSegments:
    def test_only_firm_and_latent_segments_processed(self) -> None:
        """Only firm_request/latent_request segments are processed."""
        # Create a Layer1Result with mixed segment types
        segments = [
            ClassifiedSegment(
                segment_id="S01",
                excerpt="Single Sign-On with Active Directory",
                type=SegmentType.FIRM_REQUEST,
                confidence=Confidence.HIGH,
                reasoning="Clear.",
            ),
            ClassifiedSegment(
                segment_id="S02",
                excerpt="Decision made",
                type=SegmentType.DECISION,
                confidence=Confidence.HIGH,
                reasoning="Resolved.",
            ),
            ClassifiedSegment(
                segment_id="S03",
                excerpt="Dashboard reporting feature",
                type=SegmentType.LATENT_REQUEST,
                confidence=Confidence.MEDIUM,
                reasoning="Implicit.",
            ),
        ]
        layer1_result = Layer1Result(segments=segments)
        # Both segments have matches, so no gap questions needed
        client = MockGeminiClient([])

        result = enrich_segments(layer1_result, bank_path=REFERENCE_BANK_PATH, client=client)

        # Only 2 segments should be enriched (firm_request and latent_request)
        assert len(result.enriched) == 2

    def test_missing_bank_file_raises_enrichment_error(self) -> None:
        """Missing bank file raises EnrichmentError with file path in message."""
        segments = [
            ClassifiedSegment(
                segment_id="S01",
                excerpt="Test",
                type=SegmentType.FIRM_REQUEST,
                confidence=Confidence.HIGH,
                reasoning="Test.",
            ),
        ]
        layer1_result = Layer1Result(segments=segments)

        with pytest.raises(EnrichmentError) as exc_info:
            enrich_segments(
                layer1_result,
                bank_path=Path("/nonexistent/path/bank.json"),
                client=MockGeminiClient([]),
            )

        assert "/nonexistent/path/bank.json" in str(exc_info.value)

    def test_enriched_excerpt_matches_layer1_excerpt_verbatim(self) -> None:
        """Enriched segment excerpt matches Layer 1 excerpt (no modification)."""
        excerpt = "  Padded excerpt with SSO  "
        segments = [
            ClassifiedSegment(
                segment_id="S01",
                excerpt=excerpt,
                type=SegmentType.FIRM_REQUEST,
                confidence=Confidence.HIGH,
                reasoning="Clear.",
            ),
        ]
        layer1_result = Layer1Result(segments=segments)
        client = MockGeminiClient([])

        result = enrich_segments(layer1_result, bank_path=REFERENCE_BANK_PATH, client=client)

        assert result.enriched[0].excerpt == excerpt

    def test_enriched_l1_fields_preserved(self) -> None:
        """L1 fields (confidence, reasoning) are preserved in enriched segment."""
        segment = ClassifiedSegment(
            segment_id="S01",
            excerpt="Single Sign-On with Active Directory integration",
            type=SegmentType.FIRM_REQUEST,
            confidence=Confidence.MEDIUM,
            reasoning="Somewhat clear.",
        )
        layer1_result = Layer1Result(segments=[segment])
        # Segment has a match, so no gap questions needed
        client = MockGeminiClient([])

        result = enrich_segments(layer1_result, bank_path=REFERENCE_BANK_PATH, client=client)

        assert result.enriched[0].l1_confidence == Confidence.MEDIUM
        assert result.enriched[0].l1_reasoning == "Somewhat clear."

    def test_match_found_sets_effort_and_confidence_from_reference(self) -> None:
        """When match found, effort and confidence come from reference."""
        excerpt = "Single Sign-On integration with our Active Directory"
        segments = [
            ClassifiedSegment(
                segment_id="S01",
                excerpt=excerpt,
                type=SegmentType.FIRM_REQUEST,
                confidence=Confidence.HIGH,
                reasoning="Clear.",
            ),
        ]
        layer1_result = Layer1Result(segments=segments)
        client = MockGeminiClient([])

        result = enrich_segments(layer1_result, bank_path=REFERENCE_BANK_PATH, client=client)

        enriched = result.enriched[0]
        assert enriched.reference_match is not None
        assert enriched.effort == "5 days"
        assert enriched.confidence == Confidence.HIGH
        assert len(enriched.gap_questions) == 0
        assert enriched.blockers == enriched.reference_match.blockers

    def test_no_match_sets_estimate_not_available(self) -> None:
        """When no match, effort is exactly 'estimate not available'."""
        excerpt = "IoT glucose monitor API integration"
        segments = [
            ClassifiedSegment(
                segment_id="S04",
                excerpt=excerpt,
                type=SegmentType.LATENT_REQUEST,
                confidence=Confidence.LOW,
                reasoning="Unclear scope.",
            ),
        ]
        layer1_result = Layer1Result(segments=segments)
        gap_questions_response = '{"questions": ["Q1?", "Q2?", "Q3?"]}'
        client = MockGeminiClient([gap_questions_response])

        result = enrich_segments(layer1_result, bank_path=REFERENCE_BANK_PATH, client=client)

        enriched = result.enriched[0]
        assert enriched.reference_match is None
        assert enriched.effort == "estimate not available"
        assert enriched.confidence == Confidence.LOW
        assert len(enriched.gap_questions) >= 3
        assert enriched.blockers == []


# Integration test (skipped unless GEMINI_API_KEY is set)
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
class TestIntegration:
    def test_enrichment_with_real_fixture_transcript(self) -> None:
        """Run enrich_segments on real fixture transcript."""
        from sprint_composer.layer1 import classify_transcript

        segments = get_fixture_segments()
        layer1_result = classify_transcript(segments)

        result = enrich_segments(layer1_result, bank_path=REFERENCE_BANK_PATH)

        # S01 should be matched (SSO + Active Directory)
        s01_enriched = next((e for e in result.enriched if e.segment_id == "S01"), None)
        assert s01_enriched is not None
        assert s01_enriched.reference_match is not None
        assert s01_enriched.effort == "5 days"
        assert s01_enriched.confidence == Confidence.HIGH

        # S04 should not be matched (IoT glucose monitor)
        s04_enriched = next((e for e in result.enriched if e.segment_id == "S04"), None)
        assert s04_enriched is not None
        assert s04_enriched.reference_match is None
        assert s04_enriched.effort == "estimate not available"
        assert s04_enriched.confidence == Confidence.LOW
        assert len(s04_enriched.gap_questions) >= 3

        # All enriched excerpts should match original fixture segments
        for enriched in result.enriched:
            original_segment = next((s for s in segments if s == enriched.excerpt), None)
            assert original_segment is not None, (
                f"Excerpt not found in segments: {enriched.segment_id}"
            )
