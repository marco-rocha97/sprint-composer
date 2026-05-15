from pathlib import Path

import pytest

from sprint_composer.transcript import (
    HeaderParseError,
    parse_body,
    parse_header,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TRANSCRIPT_PATH = FIXTURES_DIR / "transcript.txt"


class TestParseHeader:
    def test_valid_header_from_fixture(self) -> None:
        """Parse a valid header from the fixture transcript."""
        transcript_text = TRANSCRIPT_PATH.read_text()
        header, body_start = parse_header(transcript_text)

        assert header.day == 10
        assert header.phase == "Simulation"
        assert len(header.participants) == 4
        assert "Dr. Sarah Chen" in header.participants
        assert "James Rodriguez" in header.participants
        assert "Maria Gonzalez" in header.participants
        assert "Mike Thompson" in header.participants
        assert body_start > 0

    def test_body_start_points_past_separator(self) -> None:
        """body_start should point after the --- line."""
        transcript_text = TRANSCRIPT_PATH.read_text()
        header, body_start = parse_header(transcript_text)

        # The character before body_start should be \n (at the end of the --- line)
        assert transcript_text[body_start - 2] == "-"
        assert transcript_text[body_start - 1] == "\n"

    def test_missing_separator(self) -> None:
        """Missing --- separator raises HeaderParseError."""
        text = "day: 10\nphase: Simulation\nparticipants: [Alice, Bob]\n"
        with pytest.raises(HeaderParseError) as exc_info:
            parse_header(text)
        assert "---" in str(exc_info.value) or "separator" in str(exc_info.value)

    def test_missing_day_field(self) -> None:
        """Missing day field raises HeaderParseError."""
        text = "phase: Simulation\nparticipants: [Alice, Bob]\n---\n"
        with pytest.raises(HeaderParseError) as exc_info:
            parse_header(text)
        assert "day" in str(exc_info.value)

    def test_non_integer_day(self) -> None:
        """Non-integer day value raises HeaderParseError."""
        text = "day: abc\nphase: Simulation\nparticipants: [Alice, Bob]\n---\n"
        with pytest.raises(HeaderParseError) as exc_info:
            parse_header(text)
        assert "day" in str(exc_info.value)
        assert "integer" in str(exc_info.value)

    def test_missing_phase_field(self) -> None:
        """Missing phase field raises HeaderParseError."""
        text = "day: 10\nparticipants: [Alice, Bob]\n---\n"
        with pytest.raises(HeaderParseError) as exc_info:
            parse_header(text)
        assert "phase" in str(exc_info.value)

    def test_missing_participants_field(self) -> None:
        """Missing participants field raises HeaderParseError."""
        text = "day: 10\nphase: Simulation\n---\n"
        with pytest.raises(HeaderParseError) as exc_info:
            parse_header(text)
        assert "participants" in str(exc_info.value)

    def test_empty_participants_list(self) -> None:
        """Empty participants list raises HeaderParseError."""
        text = "day: 10\nphase: Simulation\nparticipants: []\n---\n"
        with pytest.raises(HeaderParseError) as exc_info:
            parse_header(text)
        assert "participants" in str(exc_info.value)
        assert "empty" in str(exc_info.value)


class TestParseBody:
    def test_fixture_body_segmentation(self) -> None:
        """Parse the fixture transcript body into 8 segments."""
        transcript_text = TRANSCRIPT_PATH.read_text()
        header, body_start = parse_header(transcript_text)
        segments = parse_body(transcript_text, body_start)

        assert len(segments) == 8
        assert all(isinstance(s, str) for s in segments)
        assert all(len(s) > 0 for s in segments)

    def test_no_double_newlines(self) -> None:
        """Body with no double newlines returns a single segment."""
        text = "day: 1\nphase: Discovery\nparticipants: [Alice]\n---\nSingle segment with no breaks"
        header, body_start = parse_header(text)
        segments = parse_body(text, body_start)

        assert len(segments) == 1
        assert segments[0] == "Single segment with no breaks"

    def test_leading_trailing_blank_lines(self) -> None:
        """Body with leading/trailing blanks is cleaned up."""
        text = (
            "day: 1\nphase: Discovery\nparticipants: [Alice]\n---\n"
            "\n\nFirst segment\n\n\nSecond segment\n\n\n"
        )
        header, body_start = parse_header(text)
        segments = parse_body(text, body_start)

        assert len(segments) == 2
        assert segments[0] == "First segment"
        assert segments[1] == "Second segment"

    def test_all_segments_non_empty(self) -> None:
        """All returned segments are non-empty."""
        text = (
            "day: 1\nphase: Discovery\nparticipants: [Alice]\n---\n\nSegment A\n\n\n\nSegment B\n\n"
        )
        header, body_start = parse_header(text)
        segments = parse_body(text, body_start)

        assert all(s.strip() for s in segments)
