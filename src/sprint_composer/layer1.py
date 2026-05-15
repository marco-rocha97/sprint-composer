import json
import os
import re
from typing import Any, Protocol

import google.generativeai as genai

from sprint_composer.models import ClassifiedSegment, Confidence, Layer1Result, SegmentType


class ClassificationError(Exception):
    """Raised when API response cannot be parsed or validated."""

    pass


class _GenerateResponse(Protocol):
    @property
    def text(self) -> str: ...


class _GeneratorProtocol(Protocol):
    def generate_content(self, prompt: str) -> _GenerateResponse: ...


def _extract_json(text: str) -> dict[str, Any]:
    """
    Extract and parse JSON from text, handling markdown wrapping.

    Strips markdown fences (```json ... ```) and uses regex to extract a JSON object,
    then parses it. Raises ClassificationError if no valid JSON found.
    """
    # Strip markdown code fence wrappers if present
    stripped = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    stripped = re.sub(r"\s*```$", "", stripped, flags=re.MULTILINE)

    # Extract JSON object using regex
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", stripped)
    if not match:
        raise ClassificationError(f"No JSON object found in response: {text[:100]}")

    json_str = match.group(0)
    try:
        result = json.loads(json_str)
        if not isinstance(result, dict):
            raise ClassificationError(f"Expected JSON object, got {type(result).__name__}")
        return result
    except json.JSONDecodeError as e:
        raise ClassificationError(f"Invalid JSON: {json_str} — {e}")


def _validate_classification(raw: dict[str, Any]) -> tuple[SegmentType, Confidence, str]:
    """
    Validate that raw dict has valid type, confidence, and reasoning values.

    Returns (type, confidence, reasoning) tuple or raises ClassificationError.
    """
    if "type" not in raw:
        raise ClassificationError("Missing 'type' field in response")
    if "confidence" not in raw:
        raise ClassificationError("Missing 'confidence' field in response")
    if "reasoning" not in raw:
        raise ClassificationError("Missing 'reasoning' field in response")

    type_str = raw["type"]
    confidence_str = raw["confidence"]
    reasoning_str = raw["reasoning"]

    # Validate type
    try:
        segment_type = SegmentType(type_str)
    except ValueError:
        raise ClassificationError(
            f"Invalid type value: '{type_str}'. Must be one of {[t.value for t in SegmentType]}"
        )

    # Validate confidence
    try:
        confidence = Confidence(confidence_str)
    except ValueError:
        raise ClassificationError(
            f"Invalid confidence value: '{confidence_str}'. Must be one of {[c.value for c in Confidence]}"
        )

    return segment_type, confidence, reasoning_str


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


def _build_prompt(segment: str) -> str:
    """Format the exact prompt template with the given segment."""
    return f"""You are a meeting-transcript analyst. Classify the following transcript segment into EXACTLY ONE of five categories.

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
{{"type": "<one of the five categories>", "confidence": "<HIGH|MEDIUM|LOW>", "reasoning": "<one sentence>"}}"""


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
    if client is None:
        client = _build_default_client()

    classified_segments: list[ClassifiedSegment] = []

    for i, segment in enumerate(segments):
        segment_id = f"S{i + 1:02d}"
        prompt = _build_prompt(segment)

        response = client.generate_content(prompt)
        raw_dict = _extract_json(response.text)
        segment_type, confidence, reasoning = _validate_classification(raw_dict)

        classified = ClassifiedSegment(
            segment_id=segment_id,
            excerpt=segment,
            type=segment_type,
            confidence=confidence,
            reasoning=reasoning,
        )
        classified_segments.append(classified)

    return Layer1Result(segments=classified_segments)
