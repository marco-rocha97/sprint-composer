import json
import os
import warnings
from pathlib import Path
from typing import Any, Protocol

warnings.filterwarnings("ignore", category=FutureWarning)

import google.generativeai as genai  # noqa: E402

from sprint_composer.models import (  # noqa: E402
    ClassifiedSegment,
    Confidence,
    EnrichedSegment,
    Layer1Result,
    Layer2Result,
    ReferenceMatch,
)


class EnrichmentError(Exception):
    """Raised when the reference bank cannot be loaded or is structurally invalid."""

    pass


class _GenerateResponse(Protocol):
    @property
    def text(self) -> str: ...


class _GeneratorProtocol(Protocol):
    def generate_content(self, prompt: str) -> _GenerateResponse: ...


def _load_reference_bank(path: Path) -> dict[str, Any]:
    """
    Read and parse reference_bank.json.

    Raises EnrichmentError if the file is missing or not valid JSON.
    """
    if not path.exists():
        raise EnrichmentError(f"Reference bank file not found: {path}")

    try:
        with open(path) as f:
            data: Any = json.load(f)
        return data  # type: ignore[no-any-return]
    except json.JSONDecodeError as e:
        raise EnrichmentError(f"Invalid JSON in reference bank ({path}): {e}")


def _score_task(excerpt: str, keywords: list[str]) -> int:
    """
    Case-insensitive substring count: how many keywords appear in the excerpt.

    Pure function, no I/O, no side effects.
    """
    excerpt_lower = excerpt.lower()
    count = 0
    for keyword in keywords:
        if keyword.lower() in excerpt_lower:
            count += 1
    return count


def _find_best_match(excerpt: str, bank: dict[str, Any]) -> ReferenceMatch | None:
    """
    Score every task in every project; return the ReferenceMatch with highest score
    if score > 0, else None.

    Tie-breaking: first project, first task wins (deterministic for demo fixtures).
    """
    best_score = 0
    best_match = None

    projects = bank.get("projects", [])
    for project in projects:
        project_id = project.get("id", "")
        project_name = project.get("name", "")

        tasks = project.get("tasks", [])
        for task in tasks:
            task_id = task.get("id", "")
            task_name = task.get("name", "")
            keywords = task.get("keywords", [])
            effort_days = task.get("effort_days", 0)
            effort_confidence_str = task.get("effort_confidence", "LOW")
            blockers = task.get("blockers", [])
            notes = task.get("notes", "")

            score = _score_task(excerpt, keywords)

            # Only update if this is strictly better; tie goes to first seen
            if score > best_score:
                best_score = score
                try:
                    effort_confidence = Confidence(effort_confidence_str)
                except ValueError:
                    effort_confidence = Confidence.LOW

                best_match = ReferenceMatch(
                    task_id=task_id,
                    task_name=task_name,
                    project_id=project_id,
                    project_name=project_name,
                    effort_days=effort_days,
                    effort_confidence=effort_confidence,
                    blockers=blockers,
                    notes=notes,
                )

    return best_match if best_score > 0 else None


def _build_gap_questions_prompt(excerpt: str) -> str:
    """Return the prompt string for Gemini gap-question generation."""
    return f"""You are an estimation advisor for a software delivery team.

The following transcript request has no historical reference in our task bank:
\"\"\"
{excerpt}
\"\"\"

Generate 3 to 4 concrete questions that would need to be answered before
an effort estimate can be made for this request. Focus on technical and
delivery unknowns specific to this request.

Return ONLY a valid JSON object (no markdown, no explanation):
{{"questions": ["<question 1>", "<question 2>", ...]}}"""


def _extract_gap_questions(response_text: str) -> list[str]:
    """
    Parse Gemini's JSON response {"questions": ["...", ...]}.

    On parse failure, return a 3-item generic fallback list (never raise).
    """
    fallback = [
        "What is the technical specification or API documentation for this request?",
        "Are there vendor SDK or integration guides available?",
        "What are the acceptance criteria for this to be considered complete?",
    ]

    try:
        # Strip markdown if present
        import re

        stripped = re.sub(r"^```(?:json)?\s*", "", response_text, flags=re.MULTILINE)
        stripped = re.sub(r"\s*```$", "", stripped, flags=re.MULTILINE)

        # Find JSON object
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", stripped)
        if not match:
            return fallback

        json_str = match.group(0)
        data = json.loads(json_str)

        if not isinstance(data, dict) or "questions" not in data:
            return fallback

        questions = data.get("questions", [])
        if not isinstance(questions, list):
            return fallback

        # Ensure at least 3 questions
        result = [q for q in questions if isinstance(q, str)][:4]
        if len(result) < 3:
            result.extend(fallback[: 3 - len(result)])

        return result
    except Exception:
        return fallback


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


def _enrich_segment(
    segment: ClassifiedSegment,
    bank: dict[str, Any],
    client: _GeneratorProtocol,
) -> EnrichedSegment:
    """
    Orchestrate match + enrichment or no-match + gap-question generation for one segment.
    """
    best_match = _find_best_match(segment.excerpt, bank)

    if best_match:
        # Match found — use reference data
        effort = f"{best_match.effort_days} days"
        confidence = best_match.effort_confidence
        blockers = best_match.blockers
        gap_questions: list[str] = []
        enrichment_reasoning = (
            f"Matched '{best_match.task_name}' from {best_match.project_name} "
            f"({best_match.effort_days} days); effort_confidence={confidence.value} from reference."
        )
    else:
        # No match — generate gap questions
        prompt = _build_gap_questions_prompt(segment.excerpt)
        response = client.generate_content(prompt)
        gap_questions = _extract_gap_questions(response.text)

        effort = "estimate not available"
        confidence = Confidence.LOW
        blockers = []
        enrichment_reasoning = "No reference match; gap questions generated to unlock estimation."

    return EnrichedSegment(
        segment_id=segment.segment_id,
        excerpt=segment.excerpt,
        type=segment.type,
        l1_confidence=segment.confidence,
        l1_reasoning=segment.reasoning,
        reference_match=best_match,
        effort=effort,
        confidence=confidence,
        blockers=blockers,
        gap_questions=gap_questions,
        enrichment_reasoning=enrichment_reasoning,
    )


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
    if bank_path is None:
        bank_path = Path(__file__).parent.parent / "fixtures" / "reference_bank.json"

    bank = _load_reference_bank(bank_path)

    if client is None:
        client = _build_default_client()

    l2_eligible = layer1_result.for_layer2()
    enriched_segments: list[EnrichedSegment] = []

    for segment in l2_eligible:
        enriched = _enrich_segment(segment, bank, client)
        enriched_segments.append(enriched)

    return Layer2Result(enriched=enriched_segments)
