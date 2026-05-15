import json
import os
from pathlib import Path

import pytest

from sprint_composer.layer1 import ClassificationError, classify_transcript
from sprint_composer.models import Confidence, SegmentType


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
FIXTURES_DIR = Path(__file__).parent.parent / "src" / "fixtures"
TRANSCRIPT_PATH = FIXTURES_DIR / "transcript.txt"
TAXONOMY_PATH = FIXTURES_DIR / "taxonomy_template.json"


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


# Unit tests
class TestHappyPath:
    def test_all_segments_get_a_classification(self) -> None:
        """Given 3 segments and mock responses, all receive classification."""
        segments = ["Segment A", "Segment B", "Segment C"]
        responses = [
            '{"type": "firm_request", "confidence": "HIGH", "reasoning": "Clear request."}',
            '{"type": "decision", "confidence": "MEDIUM", "reasoning": "Agreement reached."}',
            '{"type": "noise", "confidence": "LOW", "reasoning": "Off-topic remark."}',
        ]
        client = MockGeminiClient(responses)

        result = classify_transcript(segments, client=client)

        assert len(result.segments) == 3
        assert all(s.type is not None for s in result.segments)
        assert all(s.confidence is not None for s in result.segments)
        assert all(s.reasoning for s in result.segments)

    def test_excerpt_equals_input_segment(self) -> None:
        """Excerpt field is identical to input segment (no trimming)."""
        segments = ["  Padded segment  ", "Another segment"]
        responses = [
            '{"type": "firm_request", "confidence": "HIGH", "reasoning": "Request."}',
            '{"type": "latent_request", "confidence": "HIGH", "reasoning": "Implicit need."}',
        ]
        client = MockGeminiClient(responses)

        result = classify_transcript(segments, client=client)

        assert result.segments[0].excerpt == "  Padded segment  "
        assert result.segments[1].excerpt == "Another segment"

    def test_segment_ids_sequential(self) -> None:
        """Segment IDs are S01, S02, ..., S{N:02d} in order."""
        segments = ["A", "B", "C", "D", "E"]
        responses = [
            '{"type": "firm_request", "confidence": "HIGH", "reasoning": "X."}',
        ] * 5
        client = MockGeminiClient(responses)

        result = classify_transcript(segments, client=client)

        expected_ids = ["S01", "S02", "S03", "S04", "S05"]
        actual_ids = [s.segment_id for s in result.segments]
        assert actual_ids == expected_ids

    def test_types_are_valid_enum_values(self) -> None:
        """All type values in result are members of SegmentType."""
        segments = ["A", "B", "C"]
        responses = [
            '{"type": "firm_request", "confidence": "HIGH", "reasoning": "X."}',
            '{"type": "decision", "confidence": "HIGH", "reasoning": "Y."}',
            '{"type": "open_question", "confidence": "HIGH", "reasoning": "Z."}',
        ]
        client = MockGeminiClient(responses)

        result = classify_transcript(segments, client=client)

        for segment in result.segments:
            assert isinstance(segment.type, SegmentType)
            assert segment.type in SegmentType

    def test_for_layer2_includes_only_requests(self) -> None:
        """for_layer2() filters to only firm_request and latent_request."""
        segments = ["A", "B", "C", "D", "E"]
        responses = [
            '{"type": "firm_request", "confidence": "HIGH", "reasoning": "X."}',
            '{"type": "latent_request", "confidence": "HIGH", "reasoning": "Y."}',
            '{"type": "decision", "confidence": "HIGH", "reasoning": "Z."}',
            '{"type": "open_question", "confidence": "HIGH", "reasoning": "W."}',
            '{"type": "noise", "confidence": "HIGH", "reasoning": "V."}',
        ]
        client = MockGeminiClient(responses)

        result = classify_transcript(segments, client=client)
        layer2_items = result.for_layer2()

        assert len(layer2_items) == 2
        assert all(
            s.type in (SegmentType.FIRM_REQUEST, SegmentType.LATENT_REQUEST) for s in layer2_items
        )


class TestErrorCases:
    def test_garbage_response_raises_classification_error(self) -> None:
        """Invalid JSON response raises ClassificationError."""
        segments = ["A"]
        responses = ["this is not json"]
        client = MockGeminiClient(responses)

        with pytest.raises(ClassificationError):
            classify_transcript(segments, client=client)

    def test_unknown_type_in_response_raises_classification_error(self) -> None:
        """Unknown type value raises ClassificationError with type named."""
        segments = ["A"]
        responses = ['{"type": "wish_list", "confidence": "HIGH", "reasoning": "Invalid type."}']
        client = MockGeminiClient(responses)

        with pytest.raises(ClassificationError) as exc_info:
            classify_transcript(segments, client=client)

        assert "wish_list" in str(exc_info.value)


class TestEdgeCases:
    def test_markdown_wrapped_json_parsed(self) -> None:
        """Markdown-wrapped JSON (```json...```) is correctly parsed."""
        segments = ["A"]
        responses = [
            '```json\n{"type": "noise", "confidence": "HIGH", "reasoning": "Off-topic."}\n```'
        ]
        client = MockGeminiClient(responses)

        result = classify_transcript(segments, client=client)

        assert result.segments[0].type == SegmentType.NOISE
        assert result.segments[0].confidence == Confidence.HIGH


class TestConfidenceValues:
    """Verify all confidence levels are correctly parsed."""

    def test_high_confidence(self) -> None:
        """HIGH confidence is correctly parsed."""
        segments = ["A"]
        responses = ['{"type": "firm_request", "confidence": "HIGH", "reasoning": "Clear."}']
        client = MockGeminiClient(responses)

        result = classify_transcript(segments, client=client)

        assert result.segments[0].confidence == Confidence.HIGH

    def test_medium_confidence(self) -> None:
        """MEDIUM confidence is correctly parsed."""
        segments = ["A"]
        responses = ['{"type": "decision", "confidence": "MEDIUM", "reasoning": "Somewhat clear."}']
        client = MockGeminiClient(responses)

        result = classify_transcript(segments, client=client)

        assert result.segments[0].confidence == Confidence.MEDIUM

    def test_low_confidence(self) -> None:
        """LOW confidence is correctly parsed."""
        segments = ["A"]
        responses = ['{"type": "open_question", "confidence": "LOW", "reasoning": "Unclear."}']
        client = MockGeminiClient(responses)

        result = classify_transcript(segments, client=client)

        assert result.segments[0].confidence == Confidence.LOW


# Integration test
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
class TestAccuracyAgainstTaxonomy:
    def test_accuracy_against_taxonomy(self) -> None:
        """Classify fixture transcript and compare against taxonomy template."""
        segments = get_fixture_segments()

        # Call real Gemini API
        from sprint_composer.layer1 import classify_transcript

        result = classify_transcript(segments)

        # Load taxonomy
        with open(TAXONOMY_PATH) as f:
            taxonomy = json.load(f)

        # Compare classifications
        matches = 0
        for i, classified in enumerate(result.segments):
            if i < len(taxonomy["segments"]):
                expected_type = taxonomy["segments"][i]["expected_type"]
                if classified.type.value == expected_type:
                    matches += 1

        # Assert at least 80% match (7/8 for fixture)
        accuracy = matches / len(result.segments) if result.segments else 0
        assert accuracy >= 0.80, (
            f"Accuracy {accuracy:.1%} ({matches}/{len(result.segments)}) below 80% threshold"
        )
