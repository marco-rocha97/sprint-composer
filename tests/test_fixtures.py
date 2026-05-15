import json
from pathlib import Path
import re


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TRANSCRIPT_PATH = FIXTURES_DIR / "transcript.txt"
REFERENCE_BANK_PATH = FIXTURES_DIR / "reference_bank.json"
TAXONOMY_PATH = FIXTURES_DIR / "taxonomy_template.json"


def parse_transcript_header(text: str) -> dict:
    """Parse the transcript header into a dictionary."""
    header_match = re.match(
        r"day:\s*(\d+)\s*\nphase:\s*(.+)\s*\nparticipants:\s*\[(.*?)\]\s*\n---",
        text,
        re.MULTILINE,
    )
    if not header_match:
        raise ValueError("Header format invalid")

    day_str, phase_str, participants_str = header_match.groups()
    participants = [p.strip() for p in participants_str.split(",") if p.strip()]

    return {
        "day": int(day_str),
        "phase": phase_str.strip(),
        "participants": participants,
        "header_end": header_match.end(),
    }


def parse_transcript_body(text: str, header_end: int) -> list[str]:
    """Parse the transcript body into segments (non-empty paragraph blocks)."""
    body = text[header_end:].strip()
    segments = [s.strip() for s in body.split("\n\n") if s.strip()]
    return segments


class TestTranscriptHeader:
    def test_header_has_required_fields(self):
        """Header contains day, phase, participants."""
        text = TRANSCRIPT_PATH.read_text()
        header = parse_transcript_header(text)
        assert "day" in header
        assert "phase" in header
        assert "participants" in header

    def test_header_day_is_integer_in_range(self):
        """Day is an integer in [1, 15]."""
        text = TRANSCRIPT_PATH.read_text()
        header = parse_transcript_header(text)
        assert isinstance(header["day"], int)
        assert 1 <= header["day"] <= 15

    def test_header_phase_is_valid(self):
        """Phase is one of: Discovery, Setup, Simulation, Go-live."""
        text = TRANSCRIPT_PATH.read_text()
        header = parse_transcript_header(text)
        valid_phases = {"Discovery", "Setup", "Simulation", "Go-live"}
        assert header["phase"] in valid_phases

    def test_header_participants_non_empty(self):
        """Participants list is non-empty."""
        text = TRANSCRIPT_PATH.read_text()
        header = parse_transcript_header(text)
        assert len(header["participants"]) > 0


class TestTranscriptBody:
    def test_at_least_one_segment_per_type(self):
        """Taxonomy contains at least one entry for each of the 5 Layer-1 types."""
        with open(TAXONOMY_PATH) as f:
            taxonomy = json.load(f)

        types_found = set(entry["expected_type"] for entry in taxonomy["segments"])
        expected_types = {"firm_request", "latent_request", "decision", "open_question", "noise"}
        assert expected_types.issubset(types_found)

    def test_all_taxonomy_excerpts_in_transcript(self):
        """Every excerpt in the taxonomy is a verbatim substring of the transcript."""
        transcript_text = TRANSCRIPT_PATH.read_text()
        with open(TAXONOMY_PATH) as f:
            taxonomy = json.load(f)

        for entry in taxonomy["segments"]:
            excerpt = entry["excerpt"]
            assert (
                excerpt in transcript_text
            ), f"Excerpt '{excerpt}' not found in transcript"

    def test_segment_count_matches_taxonomy(self):
        """Count of body segments equals count of taxonomy entries."""
        text = TRANSCRIPT_PATH.read_text()
        header = parse_transcript_header(text)
        body_segments = parse_transcript_body(text, header["header_end"])

        with open(TAXONOMY_PATH) as f:
            taxonomy = json.load(f)

        assert len(body_segments) == len(
            taxonomy["segments"]
        ), f"Body has {len(body_segments)} segments but taxonomy has {len(taxonomy['segments'])} entries"


class TestReferenceBank:
    def test_reference_bank_has_min_projects(self):
        """Reference bank has at least 4 projects."""
        with open(REFERENCE_BANK_PATH) as f:
            bank = json.load(f)

        assert len(bank["projects"]) >= 4

    def test_each_project_has_at_least_one_task(self):
        """No project has an empty tasks list."""
        with open(REFERENCE_BANK_PATH) as f:
            bank = json.load(f)

        for project in bank["projects"]:
            assert len(project["tasks"]) > 0

    def test_required_task_fields_present(self):
        """Each task has id, name, keywords, effort_days, effort_confidence, blockers."""
        with open(REFERENCE_BANK_PATH) as f:
            bank = json.load(f)

        required_fields = {"id", "name", "keywords", "effort_days", "effort_confidence", "blockers"}
        for project in bank["projects"]:
            for task in project["tasks"]:
                assert required_fields.issubset(task.keys()), f"Task {task.get('id', 'unknown')} missing required fields"

    def test_effort_confidence_is_valid(self):
        """Effort confidence is one of HIGH, MEDIUM, LOW."""
        with open(REFERENCE_BANK_PATH) as f:
            bank = json.load(f)

        valid_confidence = {"HIGH", "MEDIUM", "LOW"}
        for project in bank["projects"]:
            for task in project["tasks"]:
                assert task["effort_confidence"] in valid_confidence


class TestGapAssertion:
    def test_no_reference_match_for_glucose_api(self):
        """No task has keyword overlap with glucose, iot, glucometer, or device api."""
        with open(REFERENCE_BANK_PATH) as f:
            bank = json.load(f)

        glucose_terms = {"glucose", "iot", "glucometer", "device api"}

        for project in bank["projects"]:
            for task in project["tasks"]:
                task_keywords_lower = {kw.lower() for kw in task["keywords"]}
                overlap = glucose_terms & task_keywords_lower
                assert not overlap, f"Task {task['id']} has forbidden keyword overlap: {overlap}"


class TestTaxonomyTemplate:
    def test_taxonomy_all_segment_ids_unique(self):
        """No duplicate segment_id."""
        with open(TAXONOMY_PATH) as f:
            taxonomy = json.load(f)

        segment_ids = [entry["segment_id"] for entry in taxonomy["segments"]]
        assert len(segment_ids) == len(set(segment_ids)), "Duplicate segment_ids found"

    def test_taxonomy_types_valid(self):
        """Each expected_type is one of the five Layer-1 type strings."""
        with open(TAXONOMY_PATH) as f:
            taxonomy = json.load(f)

        valid_types = {"firm_request", "latent_request", "decision", "open_question", "noise"}
        for entry in taxonomy["segments"]:
            assert entry["expected_type"] in valid_types
