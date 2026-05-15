import json
import os
import sys
from pathlib import Path

import pytest

from sprint_composer.cli import (
    _build_json_artifact,
    _format_proposal,
    _task_title,
    app,
)
from sprint_composer.models import (
    AllocatedTask,
    ClassifiedSegment,
    Confidence,
    Layer3Result,
    MoSCoW,
    ReferenceMatch,
    SegmentType,
    SprintAllocation,
)
from sprint_composer.transcript import TranscriptHeader


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TRANSCRIPT_PATH = FIXTURES_DIR / "transcript.txt"
REFERENCE_BANK_PATH = FIXTURES_DIR / "reference_bank.json"


def create_sample_allocated_task(
    segment_id: str,
    excerpt: str,
    moscow: MoSCoW = MoSCoW.MUST,
    sprint_allocation: SprintAllocation = SprintAllocation.IN_SPRINT,
    effort: str = "5 days",
    blockers: list[str] | None = None,
    gap_questions: list[str] | None = None,
    needs_lead_decision: bool = False,
    lead_decision_reason: str = "",
) -> AllocatedTask:
    """Helper to create an AllocatedTask for testing."""
    if blockers is None:
        blockers = []
    if gap_questions is None:
        gap_questions = []

    return AllocatedTask(
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
        l2_confidence=Confidence.HIGH,
        blockers=blockers,
        gap_questions=gap_questions,
        enrichment_reasoning="Test enrichment.",
        moscow=moscow,
        sprint_allocation=sprint_allocation,
        allocation_confidence=Confidence.HIGH,
        dependency_order=1,
        needs_lead_decision=needs_lead_decision,
        lead_decision_reason=lead_decision_reason,
        allocation_reasoning="Test allocation reasoning.",
    )


class TestTaskTitle:
    def test_first_sentence_extracted(self) -> None:
        """Extract the first sentence from an excerpt."""
        excerpt = "First sentence. Second sentence."
        result = _task_title(excerpt)
        assert result == "First sentence"

    def test_long_first_sentence_capped(self) -> None:
        """Long first sentence is capped at 80 chars with ellipsis."""
        excerpt = "This is a very long first sentence that exceeds eighty characters when you count all the words. Second sentence."
        result = _task_title(excerpt)
        assert len(result) <= 80
        assert result.endswith("...")

    def test_no_period_handles_gracefully(self) -> None:
        """Excerpt with no period returns up to 80 chars."""
        excerpt = "No period in this sentence"
        result = _task_title(excerpt)
        assert result == "No period in this sentence"


class TestFormatProposal:
    def test_all_five_blocks_present(self) -> None:
        """Output contains all 5 block headers in order."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        task_in = create_sample_allocated_task("S01", "We need to implement SSO...")
        task_out = create_sample_allocated_task(
            "S03",
            "We should build a dashboard...",
            sprint_allocation=SprintAllocation.OUT_OF_SPRINT,
        )
        l3_result = Layer3Result(in_sprint=[task_in], out_of_sprint=[task_out])
        open_q = ClassifiedSegment(
            segment_id="S07",
            excerpt="Who owns HIPAA?",
            type=SegmentType.OPEN_QUESTION,
            confidence=Confidence.HIGH,
            reasoning="Clear question.",
        )
        decision = ClassifiedSegment(
            segment_id="S06",
            excerpt="Staging for UAT.",
            type=SegmentType.DECISION,
            confidence=Confidence.HIGH,
            reasoning="Firm decision.",
        )
        noise = ClassifiedSegment(
            segment_id="S08",
            excerpt="Lunch was good.",
            type=SegmentType.NOISE,
            confidence=Confidence.HIGH,
            reasoning="Off-topic.",
        )

        result = _format_proposal(
            TRANSCRIPT_PATH, header, l3_result, [open_q], [], [decision], [noise]
        )

        assert "BLOCK 1" in result
        assert "BLOCK 2" in result
        assert "BLOCK 3" in result
        assert "BLOCK 4" in result
        assert "BLOCK 5" in result

        # Verify order
        idx1 = result.index("BLOCK 1")
        idx2 = result.index("BLOCK 2")
        idx3 = result.index("BLOCK 3")
        idx4 = result.index("BLOCK 4")
        idx5 = result.index("BLOCK 5")
        assert idx1 < idx2 < idx3 < idx4 < idx5

    def test_in_sprint_task_in_block_1(self) -> None:
        """In-sprint task appears in Block 1."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        task = create_sample_allocated_task("S01", "Implement SSO...")
        l3_result = Layer3Result(in_sprint=[task], out_of_sprint=[])

        result = _format_proposal(TRANSCRIPT_PATH, header, l3_result, [], [], [], [])

        assert "[S01]" in result
        assert "BLOCK 1" in result
        idx_task = result.index("[S01]")
        idx_block1 = result.index("BLOCK 1")
        assert idx_block1 < idx_task

    def test_out_of_sprint_task_in_block_2(self) -> None:
        """Out-of-sprint task appears in Block 2."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        task = create_sample_allocated_task(
            "S03", "Build dashboard...", sprint_allocation=SprintAllocation.OUT_OF_SPRINT
        )
        l3_result = Layer3Result(in_sprint=[], out_of_sprint=[task])

        result = _format_proposal(TRANSCRIPT_PATH, header, l3_result, [], [], [], [])

        assert "[S03]" in result
        assert "BLOCK 2" in result
        idx_task = result.index("[S03]")
        idx_block2 = result.index("BLOCK 2")
        assert idx_block2 < idx_task

    def test_gap_questions_in_task_output(self) -> None:
        """Gap questions appear under the task."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        task = create_sample_allocated_task(
            "S04", "Consolidate systems...", gap_questions=["What is scope?", "What are criteria?"]
        )
        l3_result = Layer3Result(in_sprint=[task], out_of_sprint=[])

        result = _format_proposal(TRANSCRIPT_PATH, header, l3_result, [], [task], [], [])

        assert "Questions to unlock estimate:" in result
        assert "What is scope?" in result
        assert "What are criteria?" in result

    def test_lead_decision_flagged(self) -> None:
        """needs_lead_decision=True shows lead decision reason."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        task = create_sample_allocated_task(
            "S04",
            "Consolidate...",
            needs_lead_decision=True,
            lead_decision_reason="MoSCoW level uncertain without effort estimate.",
        )
        l3_result = Layer3Result(in_sprint=[task], out_of_sprint=[])

        result = _format_proposal(TRANSCRIPT_PATH, header, l3_result, [], [], [], [])

        assert "⚠ Needs Lead decision:" in result
        assert "MoSCoW level uncertain" in result


class TestBuildJsonArtifact:
    def test_json_structure_correct(self) -> None:
        """JSON artifact has all required top-level keys."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        task = create_sample_allocated_task("S01", "Implement SSO...")
        l3_result = Layer3Result(in_sprint=[task], out_of_sprint=[])

        artifact = _build_json_artifact(TRANSCRIPT_PATH, header, l3_result, [], [], [])

        assert "metadata" in artifact
        assert "sprint_tasks" in artifact
        assert "out_of_sprint" in artifact
        assert "pending_answers" in artifact
        assert "decisions" in artifact
        assert "discard_appendix" in artifact

    def test_metadata_has_required_fields(self) -> None:
        """Metadata includes transcript_path, generated_at, and header."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        l3_result = Layer3Result(in_sprint=[], out_of_sprint=[])

        artifact = _build_json_artifact(TRANSCRIPT_PATH, header, l3_result, [], [], [])

        meta = artifact["metadata"]
        assert "transcript_path" in meta
        assert "generated_at" in meta
        assert "header" in meta
        assert meta["header"]["day"] == 10
        assert meta["header"]["phase"] == "Simulation"
        assert meta["header"]["participants"] == ["Alice"]

    def test_sprint_tasks_contains_in_sprint(self) -> None:
        """sprint_tasks list equals in_sprint tasks."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        task1 = create_sample_allocated_task("S01", "Task 1...")
        task2 = create_sample_allocated_task("S02", "Task 2...")
        l3_result = Layer3Result(in_sprint=[task1, task2], out_of_sprint=[])

        artifact = _build_json_artifact(TRANSCRIPT_PATH, header, l3_result, [], [], [])

        assert len(artifact["sprint_tasks"]) == 2
        assert artifact["sprint_tasks"][0]["segment_id"] == "S01"
        assert artifact["sprint_tasks"][1]["segment_id"] == "S02"

    def test_task_dict_has_all_fields(self) -> None:
        """Each task dict has all required fields."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        task = create_sample_allocated_task("S01", "Implement SSO...", effort="5 days")
        l3_result = Layer3Result(in_sprint=[task], out_of_sprint=[])

        artifact = _build_json_artifact(TRANSCRIPT_PATH, header, l3_result, [], [], [])

        task_dict = artifact["sprint_tasks"][0]
        assert task_dict["segment_id"] == "S01"
        assert task_dict["effort"] == "5 days"
        assert task_dict["moscow"] == "Must"
        assert task_dict["sprint_allocation"] == "in_sprint"
        assert "reference_match" in task_dict
        assert "l1_confidence" in task_dict
        assert "l2_confidence" in task_dict

    def test_reference_match_none_serializes(self) -> None:
        """reference_match=None serializes to null in JSON."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        task = create_sample_allocated_task(
            "S03", "Unknown task...", effort="estimate not available"
        )
        # Manually set reference_match to None
        task.reference_match = None
        l3_result = Layer3Result(in_sprint=[], out_of_sprint=[task])

        artifact = _build_json_artifact(TRANSCRIPT_PATH, header, l3_result, [], [], [])

        task_dict = artifact["out_of_sprint"][0]
        assert task_dict["reference_match"] is None

    def test_json_dumps_succeeds(self) -> None:
        """json.dumps(artifact) completes without TypeError on enums."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        task = create_sample_allocated_task("S01", "Task...")
        l3_result = Layer3Result(in_sprint=[task], out_of_sprint=[])

        artifact = _build_json_artifact(TRANSCRIPT_PATH, header, l3_result, [], [], [])

        # This should not raise TypeError on enum serialization
        result_str = json.dumps(artifact)
        assert isinstance(result_str, str)
        assert len(result_str) > 0

    def test_nothing_dropped_invariant(self) -> None:
        """Total segments across all blocks equals input segments."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        task_in = create_sample_allocated_task("S01", "In sprint...")
        task_out = create_sample_allocated_task(
            "S02", "Out of sprint...", sprint_allocation=SprintAllocation.OUT_OF_SPRINT
        )
        open_q = ClassifiedSegment(
            segment_id="S03",
            excerpt="Question?",
            type=SegmentType.OPEN_QUESTION,
            confidence=Confidence.HIGH,
            reasoning="Q",
        )
        decision = ClassifiedSegment(
            segment_id="S04",
            excerpt="Decision.",
            type=SegmentType.DECISION,
            confidence=Confidence.HIGH,
            reasoning="D",
        )
        noise = ClassifiedSegment(
            segment_id="S05",
            excerpt="Noise.",
            type=SegmentType.NOISE,
            confidence=Confidence.HIGH,
            reasoning="N",
        )

        l3_result = Layer3Result(in_sprint=[task_in], out_of_sprint=[task_out])

        artifact = _build_json_artifact(
            TRANSCRIPT_PATH, header, l3_result, [open_q], [decision], [noise]
        )

        total_in_json = (
            len(artifact["sprint_tasks"])
            + len(artifact["out_of_sprint"])
            + len(artifact["pending_answers"]["open_questions"])
            + len(artifact["decisions"])
            + len(artifact["discard_appendix"])
        )

        total_input = 5  # 1 in_sprint + 1 out_of_sprint + 1 open_q + 1 decision + 1 noise
        assert total_in_json == total_input


class TestRunErrorHandling:
    def test_file_not_found(self, capsys: any, tmp_path: Path) -> None:
        """File not found raises error with correct message."""
        from sprint_composer.cli import _cmd_run

        nonexistent = tmp_path / "nonexistent.txt"
        with pytest.raises(SystemExit) as exc_info:
            _cmd_run(nonexistent)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "File not found" in captured.err

    def test_malformed_header_no_separator(self, capsys: any, tmp_path: Path) -> None:
        """Malformed header (no separator) raises error."""
        from sprint_composer.cli import _cmd_run

        transcript = tmp_path / "transcript.txt"
        transcript.write_text("day: 10\nphase: Simulation\n")

        with pytest.raises(SystemExit) as exc_info:
            _cmd_run(transcript)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err

    def test_malformed_header_non_integer_day(self, capsys: any, tmp_path: Path) -> None:
        """Malformed header (non-integer day) raises error."""
        from sprint_composer.cli import _cmd_run

        transcript = tmp_path / "transcript.txt"
        transcript.write_text("day: abc\nphase: Simulation\nparticipants: [Alice]\n---\nBody")

        with pytest.raises(SystemExit) as exc_info:
            _cmd_run(transcript)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "day" in captured.err

    def test_empty_body(self, capsys: any, tmp_path: Path) -> None:
        """Empty body after valid header raises error."""
        from sprint_composer.cli import _cmd_run

        transcript = tmp_path / "transcript.txt"
        transcript.write_text("day: 10\nphase: Simulation\nparticipants: [Alice]\n---\n")

        with pytest.raises(SystemExit) as exc_info:
            _cmd_run(transcript)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "empty" in captured.err


class TestRunHappyPath:
    def test_happy_path_stdout_format(self, monkeypatch: any, capsys: any, tmp_path: Path) -> None:
        """Happy path with monkeypatched layers produces correct output."""
        from sprint_composer.cli import _cmd_run
        from sprint_composer.models import Layer1Result, Layer2Result

        # Create fixture transcript in temp dir
        transcript = tmp_path / "transcript.txt"
        transcript.write_text(
            "day: 10\nphase: Simulation\nparticipants: [Alice]\n---\nTask one.\n\nTask two.\n"
        )

        # Mock layer results
        l1_seg1 = ClassifiedSegment(
            "S01", "Task one.", SegmentType.FIRM_REQUEST, Confidence.HIGH, "Clear"
        )
        l1_seg2 = ClassifiedSegment(
            "S02", "Task two.", SegmentType.DECISION, Confidence.HIGH, "Clear"
        )
        fake_l1 = Layer1Result([l1_seg1, l1_seg2])

        from sprint_composer.models import EnrichedSegment

        l2_seg1 = EnrichedSegment(
            "S01",
            "Task one.",
            SegmentType.FIRM_REQUEST,
            Confidence.HIGH,
            "Clear",
            None,
            "5 days",
            Confidence.HIGH,
            [],
            [],
            "Clear",
        )
        fake_l2 = Layer2Result([l2_seg1])

        task1 = create_sample_allocated_task("S01", "Task one.")
        fake_l3 = Layer3Result([task1], [])

        monkeypatch.setattr("sprint_composer.cli.classify_transcript", lambda *a, **kw: fake_l1)
        monkeypatch.setattr("sprint_composer.cli.enrich_segments", lambda *a, **kw: fake_l2)
        monkeypatch.setattr("sprint_composer.cli.allocate_tasks", lambda *a, **kw: fake_l3)

        _cmd_run(transcript)
        captured = capsys.readouterr()

        # Verify stdout contains proposal blocks
        assert "BLOCK 1" in captured.out
        assert "BLOCK 2" in captured.out
        assert "BLOCK 3" in captured.out
        assert "BLOCK 4" in captured.out
        assert "BLOCK 5" in captured.out

    def test_happy_path_stderr_progress(
        self, monkeypatch: any, capsys: any, tmp_path: Path
    ) -> None:
        """Happy path prints progress lines to stderr."""
        from sprint_composer.cli import _cmd_run
        from sprint_composer.models import Layer1Result, Layer2Result, EnrichedSegment

        transcript = tmp_path / "transcript.txt"
        transcript.write_text("day: 10\nphase: Simulation\nparticipants: [Alice]\n---\nTask.")

        l1_seg = ClassifiedSegment(
            "S01", "Task.", SegmentType.FIRM_REQUEST, Confidence.HIGH, "Clear"
        )
        fake_l1 = Layer1Result([l1_seg])

        l2_seg = EnrichedSegment(
            "S01",
            "Task.",
            SegmentType.FIRM_REQUEST,
            Confidence.HIGH,
            "Clear",
            None,
            "5 days",
            Confidence.HIGH,
            [],
            [],
            "Clear",
        )
        fake_l2 = Layer2Result([l2_seg])

        task = create_sample_allocated_task("S01", "Task.")
        fake_l3 = Layer3Result([task], [])

        monkeypatch.setattr("sprint_composer.cli.classify_transcript", lambda *a, **kw: fake_l1)
        monkeypatch.setattr("sprint_composer.cli.enrich_segments", lambda *a, **kw: fake_l2)
        monkeypatch.setattr("sprint_composer.cli.allocate_tasks", lambda *a, **kw: fake_l3)

        _cmd_run(transcript)
        captured = capsys.readouterr()

        assert "Layer 1:" in captured.err
        assert "Layer 2:" in captured.err
        assert "Layer 3:" in captured.err

    def test_happy_path_json_written(self, monkeypatch: any, tmp_path: Path) -> None:
        """Happy path writes JSON artifact sibling."""
        from sprint_composer.cli import _cmd_run
        from sprint_composer.models import Layer1Result, Layer2Result, EnrichedSegment

        transcript = tmp_path / "transcript.txt"
        transcript.write_text("day: 10\nphase: Simulation\nparticipants: [Alice]\n---\nTask.")

        l1_seg = ClassifiedSegment(
            "S01", "Task.", SegmentType.FIRM_REQUEST, Confidence.HIGH, "Clear"
        )
        fake_l1 = Layer1Result([l1_seg])

        l2_seg = EnrichedSegment(
            "S01",
            "Task.",
            SegmentType.FIRM_REQUEST,
            Confidence.HIGH,
            "Clear",
            None,
            "5 days",
            Confidence.HIGH,
            [],
            [],
            "Clear",
        )
        fake_l2 = Layer2Result([l2_seg])

        task = create_sample_allocated_task("S01", "Task.")
        fake_l3 = Layer3Result([task], [])

        monkeypatch.setattr("sprint_composer.cli.classify_transcript", lambda *a, **kw: fake_l1)
        monkeypatch.setattr("sprint_composer.cli.enrich_segments", lambda *a, **kw: fake_l2)
        monkeypatch.setattr("sprint_composer.cli.allocate_tasks", lambda *a, **kw: fake_l3)

        _cmd_run(transcript)

        json_path = transcript.with_suffix(".json")
        assert json_path.exists()
        artifact = json.loads(json_path.read_text())
        assert "metadata" in artifact
        assert artifact["metadata"]["header"]["day"] is not None


class TestAppNoArgs:
    def test_no_args_exits_zero(self, monkeypatch: any, capsys: any) -> None:
        """No args prints help and exits 0."""
        monkeypatch.setattr(sys, "argv", ["sprint-composer"])

        with pytest.raises(SystemExit) as exc_info:
            app()

        assert exc_info.value.code == 0


@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
class TestIntegration:
    def test_full_pipeline_routing(self, capsys: any, tmp_path: Path) -> None:
        """Full pipeline routes segments correctly to output blocks."""
        from sprint_composer.cli import _cmd_run

        # Copy fixture to temp dir for JSON sibling
        transcript = tmp_path / "transcript.txt"
        transcript.write_text(TRANSCRIPT_PATH.read_text())

        _cmd_run(transcript)
        captured = capsys.readouterr()

        # Verify routing per CLAUDE.md demo criteria
        # S03 (admin dashboard) should be in Block 2 (out of sprint)
        assert "S03" in captured.out
        idx_s03 = captured.out.index("S03")
        idx_block2 = captured.out.rfind("BLOCK 2", 0, idx_s03)
        idx_block3 = captured.out.find("BLOCK 3", idx_s03)
        assert idx_block2 > 0 and (idx_block3 == -1 or idx_block2 > idx_block3 - len("BLOCK 3"))

        # S07 (HIPAA question) should be in Block 3 (open questions)
        assert "S07" in captured.out

        # S06 (staging decision) should be in Block 4 (decisions)
        assert "S06" in captured.out

        # S08 (lunch noise) should be in Block 5 (discard)
        assert "S08" in captured.out

    def test_full_pipeline_json_valid(self, tmp_path: Path) -> None:
        """Full pipeline produces valid JSON artifact."""
        from sprint_composer.cli import _cmd_run

        transcript = tmp_path / "transcript.txt"
        transcript.write_text(TRANSCRIPT_PATH.read_text())

        _cmd_run(transcript)

        json_path = tmp_path / "transcript.json"
        assert json_path.exists()
        artifact = json.loads(json_path.read_text())

        assert "sprint_tasks" in artifact
        assert isinstance(artifact["sprint_tasks"], list)
        assert len(artifact["sprint_tasks"]) > 0

    def test_full_pipeline_nothing_dropped(self, tmp_path: Path) -> None:
        """Nothing-dropped invariant: all segments in JSON."""
        from sprint_composer.cli import _cmd_run
        from sprint_composer.transcript import parse_body, parse_header

        transcript = tmp_path / "transcript.txt"
        transcript_text = TRANSCRIPT_PATH.read_text()
        transcript.write_text(transcript_text)

        _cmd_run(transcript)

        json_path = tmp_path / "transcript.json"
        artifact = json.loads(json_path.read_text())

        # Count total segments in JSON
        total_in_json = (
            len(artifact["sprint_tasks"])
            + len(artifact["out_of_sprint"])
            + len(artifact["pending_answers"]["open_questions"])
            + len(artifact["decisions"])
            + len(artifact["discard_appendix"])
        )

        # Count total input segments
        header, body_start = parse_header(transcript_text)
        segments = parse_body(transcript_text, body_start)
        total_input = len(segments)

        assert total_in_json == total_input
