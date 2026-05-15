from dataclasses import dataclass
from enum import Enum


class SegmentType(str, Enum):
    FIRM_REQUEST = "firm_request"
    LATENT_REQUEST = "latent_request"
    DECISION = "decision"
    OPEN_QUESTION = "open_question"
    NOISE = "noise"


# Segment types that proceed to Layer 2 enrichment
L2_ELIGIBLE: frozenset[SegmentType] = frozenset({
    SegmentType.FIRM_REQUEST,
    SegmentType.LATENT_REQUEST,
})


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
