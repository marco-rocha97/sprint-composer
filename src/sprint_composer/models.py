from dataclasses import dataclass
from enum import Enum


class SegmentType(str, Enum):
    FIRM_REQUEST = "firm_request"
    LATENT_REQUEST = "latent_request"
    DECISION = "decision"
    OPEN_QUESTION = "open_question"
    NOISE = "noise"


# Segment types that proceed to Layer 2 enrichment
L2_ELIGIBLE: frozenset[SegmentType] = frozenset(
    {
        SegmentType.FIRM_REQUEST,
        SegmentType.LATENT_REQUEST,
    }
)


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class ClassifiedSegment:
    segment_id: str  # "S01", "S02", ... (auto-assigned, 1-indexed, zero-padded to 2 digits)
    excerpt: str  # verbatim full segment text (copy of input string, never modified)
    type: SegmentType
    confidence: Confidence
    reasoning: str  # one sentence — why this type and confidence level


@dataclass
class Layer1Result:
    segments: list[ClassifiedSegment]

    def for_layer2(self) -> list[ClassifiedSegment]:
        """Items eligible for Layer 2 enrichment (firm_request and latent_request only)."""
        return [s for s in self.segments if s.type in L2_ELIGIBLE]


@dataclass
class ReferenceMatch:
    task_id: str  # e.g. "sso-ldap-integration"
    task_name: str  # e.g. "Single Sign-On via LDAP/Active Directory"
    project_id: str  # e.g. "retail-loyalty-integration"
    project_name: str  # e.g. "Retail Loyalty Program Digital Integration"
    effort_days: int  # recorded real effort from the reference bank
    effort_confidence: Confidence  # HIGH/MEDIUM/LOW from the reference bank entry
    blockers: list[str]  # typical known blockers for this task type
    notes: str  # context from the reference bank entry


@dataclass
class EnrichedSegment:
    # Preserved verbatim from Layer 1 — never modified
    segment_id: str
    excerpt: str
    type: SegmentType  # firm_request or latent_request (only)
    l1_confidence: Confidence  # Layer 1 classification confidence
    l1_reasoning: str  # Layer 1 classification reasoning

    # Layer 2 enrichment output
    reference_match: ReferenceMatch | None  # None if no match found
    effort: str  # "<N> days" from reference, or exactly "estimate not available"
    confidence: Confidence  # reference's effort_confidence, or LOW when no match
    blockers: list[str]  # from reference entry, or [] when no match
    gap_questions: list[str]  # [] when match found; 3–4 Gemini questions when no match
    enrichment_reasoning: str  # one sentence — why this confidence and effort value


@dataclass
class Layer2Result:
    enriched: list[EnrichedSegment]
