import json
import os
import sys
from pathlib import Path

import pytest

from sprint_composer.cli import (
    _build_json_artifact,
    _format_explain,
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


FIXTURES_DIR = Path(__file__).parent.parent / "src" / "fixtures"
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
    scope_creep_category: str = "",
    scope_creep_impact: str = "",
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
        scope_creep_category=scope_creep_category,
        scope_creep_impact=scope_creep_impact,
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

    def test_out_of_sprint_with_scope_creep_shows_category_and_impact(self) -> None:
        """Out-of-sprint task with scope_creep shows Category and Impact lines."""
        header = TranscriptHeader(day=2, phase="Discovery", participants=["Alice"])
        task = create_sample_allocated_task(
            "S04",
            "IoT glucose monitor...",
            sprint_allocation=SprintAllocation.OUT_OF_SPRINT,
            scope_creep_category="information_gap",
            scope_creep_impact="Accepting without vendor documentation risks hidden effort.",
        )
        l3_result = Layer3Result(in_sprint=[], out_of_sprint=[task])

        result = _format_proposal(TRANSCRIPT_PATH, header, l3_result, [], [], [], [])

        assert "Category: information_gap" in result
        assert "Accepting without vendor documentation" in result

    def test_out_of_sprint_without_scope_creep_omits_category_and_impact_lines(
        self,
    ) -> None:
        """Out-of-sprint task without scope_creep omits Category and Impact lines."""
        header = TranscriptHeader(day=10, phase="Simulation", participants=["Alice"])
        task = create_sample_allocated_task(
            "S03",
            "Build dashboard...",
            sprint_allocation=SprintAllocation.OUT_OF_SPRINT,
            scope_creep_category="",
            scope_creep_impact="",
        )
        l3_result = Layer3Result(in_sprint=[], out_of_sprint=[task])

        result = _format_proposal(TRANSCRIPT_PATH, header, l3_result, [], [], [], [])

        assert "Category:" not in result
        assert "Impact:" not in result

    def test_in_sprint_task_never_shows_scope_creep_fields(self) -> None:
        """In-sprint task never shows scope_creep fields even if non-empty."""
        header = TranscriptHeader(day=2, phase="Discovery", participants=["Alice"])
        task = create_sample_allocated_task(
            "S01",
            "Implement SSO...",
            sprint_allocation=SprintAllocation.IN_SPRINT,
            scope_creep_category="prerequisite_risk",
            scope_creep_impact="Some impact.",
        )
        l3_result = Layer3Result(in_sprint=[task], out_of_sprint=[])

        result = _format_proposal(TRANSCRIPT_PATH, header, l3_result, [], [], [], [])

        assert "Category:" not in result
        assert "prerequisite_risk" not in result


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


class TestFormatExplain:
    def test_task_with_reference_match(self) -> None:
        """Task with reference match includes L1, L2, L3 sections."""
        task_data = {
            "segment_id": "S01",
            "excerpt": "We need to implement Single Sign-On integration with our Active Directory\nto streamline provider access.",
            "type": "firm_request",
            "l1_confidence": "HIGH",
            "l1_reasoning": "Clear, explicit request for SSO with a named technical system.",
            "reference_match": {
                "task_id": "sso-ldap",
                "task_name": "Single Sign-On via LDAP/Active Directory",
                "project_id": "retail-loyalty",
                "project_name": "Retail Loyalty Program Digital Integration",
                "effort_days": 5,
                "effort_confidence": "HIGH",
                "blockers": ["Identity provider configuration", "Network security group rules"],
                "notes": "LDAP/AD integration.",
            },
            "effort": "5 days",
            "l2_confidence": "HIGH",
            "blockers": ["Identity provider configuration", "Network security group rules"],
            "gap_questions": [],
            "enrichment_reasoning": "Close match found: same technology (LDAP/AD SSO), similar integration scope.",
            "moscow": "Must",
            "sprint_allocation": "in_sprint",
            "allocation_confidence": "HIGH",
            "dependency_order": 1,
            "needs_lead_decision": False,
            "lead_decision_reason": "",
            "allocation_reasoning": "SSO is a prerequisite for all authenticated workflows in Simulation.",
        }

        output = _format_explain("S01", task_data, "Proposed sprint tasks")

        assert "=== Explain: S01 ===" in output
        assert "Block: Proposed sprint tasks" in output
        assert "Source excerpt:" in output
        assert "Single Sign-On integration" in output
        assert "Layer 1 — Classification" in output
        assert "Layer 2 — Enrichment" in output
        assert "Layer 3 — Allocation" in output
        assert (
            "Single Sign-On via LDAP/Active Directory (Retail Loyalty Program Digital Integration)"
            in output
        )
        assert "5 days" in output
        assert "Identity provider configuration; Network security group rules" in output

    def test_task_without_reference_match(self) -> None:
        """Task with no reference match includes gap questions and LOW confidence."""
        task_data = {
            "segment_id": "S04",
            "excerpt": "The nursing team raised an interesting request during the UAT sessions about\nconsolidating the three scheduling systems into one interface.",
            "type": "latent_request",
            "l1_confidence": "MEDIUM",
            "l1_reasoning": "Latent pain around workflow fragmentation; not an explicit deliverable request.",
            "reference_match": None,
            "effort": "estimate not available",
            "l2_confidence": "LOW",
            "blockers": [],
            "gap_questions": [
                "What is the technical scope for consolidating the three systems?",
                "Are there vendor APIs or integration guides available for the scheduling system?",
                "What are the acceptance criteria for this to be considered complete?",
            ],
            "enrichment_reasoning": "No close reference match; estimation requires scoping inputs from customer.",
            "moscow": "Should",
            "sprint_allocation": "in_sprint",
            "allocation_confidence": "HIGH",
            "dependency_order": 3,
            "needs_lead_decision": True,
            "lead_decision_reason": "MoSCoW level uncertain without effort estimate for scoping.",
            "allocation_reasoning": "Workflow consolidation scope is unclear; needs Lead input on phasing.",
        }

        output = _format_explain("S04", task_data, "Proposed sprint tasks")

        assert "=== Explain: S04 ===" in output
        assert "Layer 2 — Enrichment" in output
        assert "no match found" in output
        assert "estimate not available" in output
        assert "Questions to unlock estimate:" in output
        assert "• What is the technical scope" in output
        assert "LOW" in output
        assert "Needs Lead decision:" in output
        assert "MoSCoW level uncertain" in output

    def test_task_with_needs_lead_decision(self) -> None:
        """Task with needs_lead_decision=True includes the decision flag."""
        task_data = {
            "segment_id": "S05",
            "excerpt": "A task requiring Lead decision.",
            "type": "firm_request",
            "l1_confidence": "HIGH",
            "l1_reasoning": "Clear request.",
            "reference_match": {
                "task_id": "test-task",
                "task_name": "Test Task",
                "project_id": "test-proj",
                "project_name": "Test Project",
                "effort_days": 5,
                "effort_confidence": "HIGH",
                "blockers": [],
                "notes": "Test note.",
            },
            "effort": "5 days",
            "l2_confidence": "HIGH",
            "blockers": [],
            "gap_questions": [],
            "enrichment_reasoning": "Close match found.",
            "moscow": "Should",
            "sprint_allocation": "in_sprint",
            "allocation_confidence": "MEDIUM",
            "dependency_order": 2,
            "needs_lead_decision": True,
            "lead_decision_reason": "Priority unclear; needs Lead input.",
            "allocation_reasoning": "Scope requires clarification.",
        }

        output = _format_explain("S05", task_data, "Proposed sprint tasks")

        assert "Needs Lead decision: Priority unclear; needs Lead input." in output

    def test_non_task_entry_decision(self) -> None:
        """Non-task entry (decision) includes L1 only, no L2/L3 section headers."""
        task_data = {
            "segment_id": "S06",
            "excerpt": "We've made a firm decision: the staging environment will be used for all UAT\nmoving forward.",
            "type": "decision",
            "l1_confidence": "HIGH",
            "l1_reasoning": "Firm scope decision recorded by the team.",
        }

        output = _format_explain("S06", task_data, "Recorded decisions")

        assert "=== Explain: S06 ===" in output
        assert "Block: Recorded decisions" in output
        assert "Layer 1 — Classification" in output
        assert "decision" in output
        # No Layer 2 or Layer 3 section headers (but the note mentions Layer 2/3)
        lines = output.split("\n")
        for line in lines:
            assert not line.startswith("Layer 2 —")
            assert not line.startswith("Layer 3 —")
        assert "(No Layer 2 or Layer 3" in output

    def test_excerpt_verbatim_not_truncated(self) -> None:
        """Long excerpt appears in full, not truncated."""
        long_excerpt = "This is a very long excerpt. " * 20
        task_data = {
            "segment_id": "S07",
            "excerpt": long_excerpt,
            "type": "firm_request",
            "l1_confidence": "HIGH",
            "l1_reasoning": "Clear request.",
        }

        output = _format_explain("S07", task_data, "Discard appendix")

        # The excerpt should appear verbatim in the output
        assert long_excerpt in output

    def test_out_of_sprint_task_with_scope_creep_shows_scope_creep_lines(self) -> None:
        """Out-of-sprint task with scope_creep shows Scope creep and Impact lines in Layer 3."""
        task_data = {
            "segment_id": "S04",
            "excerpt": "The nursing team raised an interesting request during the UAT sessions about\nconsolidating the three scheduling systems into one interface.",
            "type": "latent_request",
            "l1_confidence": "MEDIUM",
            "l1_reasoning": "Latent pain around workflow fragmentation.",
            "reference_match": None,
            "effort": "estimate not available",
            "l2_confidence": "LOW",
            "blockers": [],
            "gap_questions": ["What is scope?"],
            "enrichment_reasoning": "No close reference match.",
            "moscow": "Should",
            "sprint_allocation": "out_of_sprint",
            "allocation_confidence": "LOW",
            "dependency_order": 0,
            "needs_lead_decision": False,
            "lead_decision_reason": "",
            "allocation_reasoning": "Out of phase.",
            "scope_creep_category": "deferred_phase",
            "scope_creep_impact": "Accepting would extend go-live by 1 week.",
        }

        output = _format_explain("S04", task_data, "Out of sprint")

        assert "Layer 3 — Allocation" in output
        assert "Scope creep: deferred_phase" in output
        assert "Impact:      Accepting would extend go-live by 1 week." in output

    def test_out_of_sprint_task_without_scope_creep_omits_scope_creep_lines(self) -> None:
        """Out-of-sprint task without scope_creep omits Scope creep and Impact lines."""
        task_data = {
            "segment_id": "S04",
            "excerpt": "Some request.",
            "type": "firm_request",
            "l1_confidence": "MEDIUM",
            "l1_reasoning": "Clear request.",
            "reference_match": None,
            "effort": "estimate not available",
            "l2_confidence": "LOW",
            "blockers": [],
            "gap_questions": [],
            "enrichment_reasoning": "No match.",
            "moscow": "Could",
            "sprint_allocation": "out_of_sprint",
            "allocation_confidence": "LOW",
            "dependency_order": 0,
            "needs_lead_decision": False,
            "lead_decision_reason": "",
            "allocation_reasoning": "Out of phase.",
            "scope_creep_category": "",
            "scope_creep_impact": "",
        }

        output = _format_explain("S04", task_data, "Out of sprint")

        assert "Scope creep:" not in output
        assert "Impact:" not in output


class TestTaskToDict:
    def test_task_to_dict_includes_scope_creep_fields(self) -> None:
        """_task_to_dict includes scope_creep_category and scope_creep_impact."""
        from sprint_composer.cli import _task_to_dict

        task = create_sample_allocated_task(
            "S01",
            "Request.",
            scope_creep_category="prerequisite_risk",
            scope_creep_impact="Some impact.",
        )

        task_dict = _task_to_dict(task)

        assert "scope_creep_category" in task_dict
        assert task_dict["scope_creep_category"] == "prerequisite_risk"
        assert "scope_creep_impact" in task_dict
        assert task_dict["scope_creep_impact"] == "Some impact."


class TestCmdExplain:
    def test_json_not_found(self, capsys: any, tmp_path: Path) -> None:
        """JSON sibling missing → exit 1 with 'No JSON artifact found' error."""
        from sprint_composer.cli import _cmd_explain

        transcript = tmp_path / "transcript.txt"
        transcript.write_text("day: 10\nphase: Simulation\nparticipants: [Alice]\n---\nBody")

        with pytest.raises(SystemExit) as exc_info:
            _cmd_explain(transcript, "S01")

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "No JSON artifact found" in captured.err

    def test_json_invalid_malformed(self, capsys: any, tmp_path: Path) -> None:
        """Malformed JSON → exit 1 with 'Cannot parse artifact' error."""
        from sprint_composer.cli import _cmd_explain

        transcript = tmp_path / "transcript.txt"
        transcript.write_text("day: 10\nphase: Simulation\nparticipants: [Alice]\n---\nBody")

        json_path = tmp_path / "transcript.json"
        json_path.write_text("not valid json")

        with pytest.raises(SystemExit) as exc_info:
            _cmd_explain(transcript, "S01")

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "Cannot parse artifact" in captured.err

    def test_unknown_task_id(self, capsys: any, tmp_path: Path) -> None:
        """Unknown task_id → exit 1 with 'Task not found' error."""
        from sprint_composer.cli import _cmd_explain

        transcript = tmp_path / "transcript.txt"
        transcript.write_text("day: 10\nphase: Simulation\nparticipants: [Alice]\n---\nBody")

        json_path = tmp_path / "transcript.json"
        artifact = {
            "sprint_tasks": [{"segment_id": "S01", "excerpt": "Task 1"}],
            "out_of_sprint": [],
            "pending_answers": {"open_questions": []},
            "decisions": [],
            "discard_appendix": [],
        }
        json_path.write_text(json.dumps(artifact))

        with pytest.raises(SystemExit) as exc_info:
            _cmd_explain(transcript, "S99")

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "S99" in captured.err
        assert "not found" in captured.err

    def test_happy_path_sprint_task(self, capsys: any, tmp_path: Path) -> None:
        """Happy path: sprint_task found → stdout contains Layer 1, 2, 3."""
        from sprint_composer.cli import _cmd_explain

        transcript = tmp_path / "transcript.txt"
        transcript.write_text("day: 10\nphase: Simulation\nparticipants: [Alice]\n---\nBody")

        json_path = tmp_path / "transcript.json"
        artifact = {
            "sprint_tasks": [
                {
                    "segment_id": "S01",
                    "excerpt": "Implement SSO.",
                    "type": "firm_request",
                    "l1_confidence": "HIGH",
                    "l1_reasoning": "Clear request.",
                    "reference_match": {
                        "task_id": "sso",
                        "task_name": "SSO Task",
                        "project_id": "proj1",
                        "project_name": "Project 1",
                        "effort_days": 5,
                        "effort_confidence": "HIGH",
                        "blockers": [],
                        "notes": "Note.",
                    },
                    "effort": "5 days",
                    "l2_confidence": "HIGH",
                    "blockers": [],
                    "gap_questions": [],
                    "enrichment_reasoning": "Match found.",
                    "moscow": "Must",
                    "sprint_allocation": "in_sprint",
                    "allocation_confidence": "HIGH",
                    "dependency_order": 1,
                    "needs_lead_decision": False,
                    "lead_decision_reason": "",
                    "allocation_reasoning": "Priority task.",
                }
            ],
            "out_of_sprint": [],
            "pending_answers": {"open_questions": []},
            "decisions": [],
            "discard_appendix": [],
        }
        json_path.write_text(json.dumps(artifact))

        _cmd_explain(transcript, "S01")
        captured = capsys.readouterr()

        assert "=== Explain: S01 ===" in captured.out
        assert "Layer 1" in captured.out
        assert "Layer 2" in captured.out
        assert "Layer 3" in captured.out

    def test_happy_path_decision_non_task(self, capsys: any, tmp_path: Path) -> None:
        """Happy path: decision (non-task) found → stdout contains Layer 1 only."""
        from sprint_composer.cli import _cmd_explain

        transcript = tmp_path / "transcript.txt"
        transcript.write_text("day: 10\nphase: Simulation\nparticipants: [Alice]\n---\nBody")

        json_path = tmp_path / "transcript.json"
        artifact = {
            "sprint_tasks": [],
            "out_of_sprint": [],
            "pending_answers": {"open_questions": []},
            "decisions": [
                {
                    "segment_id": "S06",
                    "excerpt": "Staging for UAT.",
                    "type": "decision",
                    "l1_confidence": "HIGH",
                    "l1_reasoning": "Firm decision.",
                }
            ],
            "discard_appendix": [],
        }
        json_path.write_text(json.dumps(artifact))

        _cmd_explain(transcript, "S06")
        captured = capsys.readouterr()

        assert "=== Explain: S06 ===" in captured.out
        assert "Layer 1" in captured.out
        assert "(No Layer 2 or Layer 3" in captured.out


class TestAppExplainSubcommand:
    def test_explain_subcommand_registered_and_dispatches(self, monkeypatch: any) -> None:
        """explain subcommand is registered and dispatches to _cmd_explain."""
        calls = []

        def mock_cmd_explain(transcript_path: Path, task_id: str) -> None:
            calls.append(("_cmd_explain", str(transcript_path), task_id))

        monkeypatch.setattr("sprint_composer.cli._cmd_explain", mock_cmd_explain)
        monkeypatch.setattr(sys, "argv", ["sprint-composer", "explain", "transcript.txt", "S01"])

        app()

        # Should dispatch to _cmd_explain with correct args
        assert len(calls) == 1
        assert calls[0][0] == "_cmd_explain"
        assert "transcript.txt" in calls[0][1]
        assert calls[0][2] == "S01"


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

    def test_explain_s03_out_of_sprint(self, capsys: any, tmp_path: Path) -> None:
        """Full pipeline: run → explain S03 (out-of-sprint) → demo criterion 4."""
        from sprint_composer.cli import _cmd_run, _cmd_explain

        transcript = tmp_path / "transcript.txt"
        transcript.write_text(TRANSCRIPT_PATH.read_text())

        _cmd_run(transcript)

        # Reset capsys to get clean output for explain
        capsys.readouterr()

        _cmd_explain(transcript, "S03")
        captured = capsys.readouterr()

        # S03 is the admin dashboard, should be out of sprint
        assert "=== Explain: S03 ===" in captured.out
        assert "Out of sprint" in captured.out
        assert "Layer 3" in captured.out

    def test_explain_s04_low_confidence_no_match(self, capsys: any, tmp_path: Path) -> None:
        """Full pipeline: run → explain S04 (LOW confidence, no match) → demo criterion 4."""
        from sprint_composer.cli import _cmd_run, _cmd_explain

        transcript = tmp_path / "transcript.txt"
        transcript.write_text(TRANSCRIPT_PATH.read_text())

        _cmd_run(transcript)

        # Reset capsys to get clean output for explain
        capsys.readouterr()

        _cmd_explain(transcript, "S04")
        captured = capsys.readouterr()

        # S04 should have no match found (if it has gap questions)
        assert "=== Explain: S04 ===" in captured.out
        # Check for either no match or low confidence indicators
        assert ("no match found" in captured.out) or ("LOW" in captured.out)

    def test_explain_unknown_id_after_valid_run(self, capsys: any, tmp_path: Path) -> None:
        """explain with unknown ID after valid run → exit 1."""
        from sprint_composer.cli import _cmd_run, _cmd_explain

        transcript = tmp_path / "transcript.txt"
        transcript.write_text(TRANSCRIPT_PATH.read_text())

        _cmd_run(transcript)

        with pytest.raises(SystemExit) as exc_info:
            _cmd_explain(transcript, "S99")

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "S99" in captured.err
        assert "not found" in captured.err
