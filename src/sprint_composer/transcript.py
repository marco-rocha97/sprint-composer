import re
from dataclasses import dataclass


@dataclass
class TranscriptHeader:
    day: int
    phase: str
    participants: list[str]


class HeaderParseError(Exception):
    """Raised when the transcript header is missing or malformed."""


def parse_header(text: str) -> tuple[TranscriptHeader, int]:
    """
    Parse the YAML-ish header block from a transcript string.

    Expected format:
        day: <int>
        phase: <str>
        participants: [Name1, Name2, ...]
        ---

    Returns (TranscriptHeader, body_start) where body_start is the character
    offset of the first character after the '---' line.

    Raises HeaderParseError with a named, actionable message if:
      - '---' separator is not found
      - 'day:' field is missing
      - 'day' value is not a valid integer
      - 'phase:' field is missing
      - 'participants:' field is missing
      - participants list is empty after parsing
    """
    # Find the '---' separator
    sep_match = re.search(r"^---\s*$", text, re.MULTILINE)
    if not sep_match:
        raise HeaderParseError(
            "No header separator '---' found. Add the header block "
            "(day:/phase:/participants:) before the '---' line."
        )

    header_block = text[: sep_match.start()]
    body_start = sep_match.end()
    if body_start < len(text) and text[body_start] == "\n":
        body_start += 1

    # Parse day field
    day_match = re.search(r"^day:\s*(.+)$", header_block, re.MULTILINE)
    if not day_match:
        raise HeaderParseError("Missing header field 'day'. Add 'day: <1-15>' to the header.")

    day_str = day_match.group(1).strip()
    try:
        day = int(day_str)
    except ValueError:
        raise HeaderParseError(
            f"Header field 'day' is not a valid integer: '{day_str}'. Example: 'day: 10'."
        )

    # Parse phase field
    phase_match = re.search(r"^phase:\s*(.+)$", header_block, re.MULTILINE)
    if not phase_match:
        raise HeaderParseError(
            "Missing header field 'phase'. Add 'phase: <Discovery|Setup|Simulation|Go-live>'."
        )

    phase = phase_match.group(1).strip()

    # Parse participants field
    participants_match = re.search(
        r"^participants:\s*\[(.*)?\]", header_block, re.MULTILINE | re.DOTALL
    )
    if not participants_match:
        raise HeaderParseError(
            "Missing header field 'participants'. Add 'participants: [Name1, Name2]'."
        )

    participants_str = participants_match.group(1) or ""
    participants = [name.strip() for name in participants_str.split(",") if name.strip()]

    if not participants:
        raise HeaderParseError(
            "Header field 'participants' is empty. Add at least one participant name."
        )

    return TranscriptHeader(day=day, phase=phase, participants=participants), body_start


def parse_body(text: str, body_start: int) -> list[str]:
    """
    Split the transcript body into non-empty paragraph segments.

    Splits text[body_start:] on double newlines and strips each segment.
    Returns only segments with non-whitespace content.
    """
    body = text[body_start:]
    segments = body.split("\n\n")
    return [s.strip() for s in segments if s.strip()]
