import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sprint_composer.layer1 import classify_transcript
from sprint_composer.layer2 import enrich_segments
from sprint_composer.layer3 import allocate_tasks
from sprint_composer.models import (
    AllocatedTask,
    ClassifiedSegment,
    Layer3Result,
    SegmentType,
)
from sprint_composer.transcript import parse_body, parse_header


def _progress(msg: str) -> None:
    """Print a progress line to stderr."""
    print(msg, file=sys.stderr)


def _die(msg: str) -> None:
    """Print 'Error: <msg>' to stderr and sys.exit(1)."""
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def _task_title(excerpt: str) -> str:
    """Return first sentence of excerpt, capped at 80 chars with ellipsis if truncated."""
    first_sentence = excerpt.split(".")[0].strip()
    if len(first_sentence) > 80:
        return first_sentence[:77] + "..."
    return first_sentence


def _format_proposal(
    transcript_path: Path,
    header: Any,  # TranscriptHeader
    l3_result: Layer3Result,
    open_questions: list[ClassifiedSegment],
    gap_question_tasks: list[AllocatedTask],
    decisions: list[ClassifiedSegment],
    noise: list[ClassifiedSegment],
) -> str:
    """Build the full 5-block proposal as a human-readable string."""
    generated_at = datetime.now(timezone.utc).isoformat()
    participants_str = ", ".join(header.participants)

    lines: list[str] = []
    lines.append("=== Sprint Composer — Proposal ===")
    lines.append(f"Transcript: {transcript_path.resolve()}")
    lines.append(f"Phase: {header.phase} (Day {header.day})")
    lines.append(f"Participants: {participants_str}")
    lines.append(f"Generated: {generated_at}")
    lines.append("")

    # BLOCK 1: PROPOSED SPRINT TASKS
    lines.append("──────────────────────────────────────────────────")
    lines.append("BLOCK 1: PROPOSED SPRINT TASKS")
    lines.append("──────────────────────────────────────────────────")
    lines.append("")

    for task in l3_result.in_sprint:
        title = _task_title(task.excerpt)
        lines.append(f"[{task.segment_id}] {title}")
        lines.append(f"  MoSCoW:     {task.moscow.value}")
        lines.append(f"  Confidence: {task.allocation_confidence.value}")
        lines.append(f"  Effort:     {task.effort}")

        if task.blockers:
            blockers_str = "; ".join(task.blockers)
            lines.append(f"  Blockers:   {blockers_str}")

        lines.append(f"  Reasoning:  {task.allocation_reasoning}")

        if task.gap_questions:
            lines.append("  Questions to unlock estimate:")
            for q in task.gap_questions:
                lines.append(f"    • {q}")

        if task.needs_lead_decision:
            lines.append(f"  ⚠ Needs Lead decision: {task.lead_decision_reason}")

        excerpt_lines = task.excerpt.split("\n")
        if len(excerpt_lines[0]) > 80:
            excerpt_preview = excerpt_lines[0][:77] + "..."
        else:
            excerpt_preview = excerpt_lines[0]
        lines.append(f'  Excerpt:    "{excerpt_preview}"')
        lines.append("")

    # BLOCK 2: OUT OF SPRINT
    lines.append("──────────────────────────────────────────────────")
    lines.append("BLOCK 2: OUT OF SPRINT")
    lines.append("──────────────────────────────────────────────────")
    lines.append("")

    for task in l3_result.out_of_sprint:
        title = _task_title(task.excerpt)
        lines.append(f"[{task.segment_id}] {title}")
        lines.append(f"  Reason: {task.allocation_reasoning}")
        lines.append("")

    # BLOCK 3: PENDING CUSTOMER ANSWERS
    lines.append("──────────────────────────────────────────────────")
    lines.append("BLOCK 3: PENDING CUSTOMER ANSWERS")
    lines.append("──────────────────────────────────────────────────")
    lines.append("")

    for seg in open_questions:
        lines.append(f"[{seg.segment_id}] Open question from meeting:")
        excerpt_lines = seg.excerpt.split("\n")
        for line in excerpt_lines:
            if line.strip():
                lines.append(f'  "{line}"')
        lines.append("")

    for task in gap_question_tasks:
        title = _task_title(task.excerpt)
        lines.append(f"Estimation questions (task {task.segment_id}):")
        for q in task.gap_questions:
            lines.append(f"  • {q}")
        lines.append("")

    # BLOCK 4: RECORDED DECISIONS
    lines.append("──────────────────────────────────────────────────")
    lines.append("BLOCK 4: RECORDED DECISIONS")
    lines.append("──────────────────────────────────────────────────")
    lines.append("")

    for seg in decisions:
        lines.append(f"[{seg.segment_id}] Decision:")
        excerpt_lines = seg.excerpt.split("\n")
        for line in excerpt_lines:
            if line.strip():
                lines.append(f'  "{line}"')
        lines.append("")

    # BLOCK 5: DISCARD APPENDIX
    lines.append("──────────────────────────────────────────────────")
    lines.append("BLOCK 5: DISCARD APPENDIX")
    lines.append("──────────────────────────────────────────────────")
    lines.append("")

    for seg in noise:
        lines.append(f"[{seg.segment_id}] Noise (off-topic):")
        excerpt_lines = seg.excerpt.split("\n")
        for line in excerpt_lines:
            if line.strip():
                lines.append(f'  "{line}"')
        lines.append("")

    lines.append("──────────────────────────────────────────────────")
    lines.append("")

    return "\n".join(lines)


def _build_json_artifact(
    transcript_path: Path,
    header: Any,  # TranscriptHeader
    l3_result: Layer3Result,
    open_questions: list[ClassifiedSegment],
    decisions: list[ClassifiedSegment],
    noise: list[ClassifiedSegment],
) -> dict[str, Any]:
    """Build the machine-readable JSON artifact dict."""
    generated_at = datetime.now(timezone.utc).isoformat()

    # Collect gap_question_tasks (all tasks with non-empty gap_questions)
    gap_question_tasks = [
        task for task in (l3_result.in_sprint + l3_result.out_of_sprint) if task.gap_questions
    ]

    artifact: dict[str, Any] = {
        "metadata": {
            "transcript_path": str(transcript_path.resolve()),
            "generated_at": generated_at,
            "header": {
                "day": header.day,
                "phase": header.phase,
                "participants": header.participants,
            },
        },
        "sprint_tasks": [_task_to_dict(task) for task in l3_result.in_sprint],
        "out_of_sprint": [_task_to_dict(task) for task in l3_result.out_of_sprint],
        "pending_answers": {
            "open_questions": [
                {
                    "segment_id": seg.segment_id,
                    "excerpt": seg.excerpt,
                    "l1_confidence": seg.confidence.value,
                    "l1_reasoning": seg.reasoning,
                }
                for seg in open_questions
            ],
            "gap_questions": [
                {
                    "task_segment_id": task.segment_id,
                    "task_title": _task_title(task.excerpt),
                    "questions": task.gap_questions,
                }
                for task in gap_question_tasks
            ],
        },
        "decisions": [
            {
                "segment_id": seg.segment_id,
                "excerpt": seg.excerpt,
                "l1_confidence": seg.confidence.value,
                "l1_reasoning": seg.reasoning,
            }
            for seg in decisions
        ],
        "discard_appendix": [
            {
                "segment_id": seg.segment_id,
                "excerpt": seg.excerpt,
                "l1_confidence": seg.confidence.value,
                "l1_reasoning": seg.reasoning,
            }
            for seg in noise
        ],
    }

    return artifact


def _task_to_dict(task: AllocatedTask) -> dict[str, Any]:
    """Convert an AllocatedTask to a dict for JSON serialization."""
    return {
        "segment_id": task.segment_id,
        "excerpt": task.excerpt,
        "type": task.type.value,
        "l1_confidence": task.l1_confidence.value,
        "l1_reasoning": task.l1_reasoning,
        "reference_match": (
            {
                "task_id": task.reference_match.task_id,
                "task_name": task.reference_match.task_name,
                "project_id": task.reference_match.project_id,
                "project_name": task.reference_match.project_name,
                "effort_days": task.reference_match.effort_days,
                "effort_confidence": task.reference_match.effort_confidence.value,
                "blockers": task.reference_match.blockers,
                "notes": task.reference_match.notes,
            }
            if task.reference_match
            else None
        ),
        "effort": task.effort,
        "l2_confidence": task.l2_confidence.value,
        "blockers": task.blockers,
        "gap_questions": task.gap_questions,
        "enrichment_reasoning": task.enrichment_reasoning,
        "moscow": task.moscow.value,
        "sprint_allocation": task.sprint_allocation.value,
        "allocation_confidence": task.allocation_confidence.value,
        "dependency_order": task.dependency_order,
        "needs_lead_decision": task.needs_lead_decision,
        "lead_decision_reason": task.lead_decision_reason,
        "allocation_reasoning": task.allocation_reasoning,
    }


def _cmd_run(transcript_path: Path) -> None:
    """
    Orchestrate the full pipeline and emit the 5-block proposal.

    Reads transcript_path, parses header + body, runs classify_transcript →
    enrich_segments → allocate_tasks, prints formatted proposal to stdout,
    writes JSON sibling to transcript_path.with_suffix('.json').

    All user-facing errors print 'Error: <named message>' to stderr and exit 1.
    Progress lines print to stderr so stdout stays clean for the proposal.
    """
    # Step 1: Check file exists
    if not transcript_path.exists():
        _die(f"File not found: {transcript_path}")

    # Step 2: Read file
    try:
        text = transcript_path.read_text()
    except OSError as e:
        _die(f"Cannot read file '{transcript_path}': {e}")

    # Step 3: Parse header
    try:
        header, body_start = parse_header(text)
    except Exception as e:
        _die(str(e))

    # Step 4: Parse body
    segments = parse_body(text, body_start)
    if not segments:
        _die("Transcript body is empty — no segments found after the header.")

    # Step 5: Layer 1 - Classification
    try:
        _progress("Layer 1: classifying…")
        l1_result = classify_transcript(segments)
    except Exception as e:
        error_msg = str(e)
        if "GEMINI_API_KEY" in error_msg:
            _die(error_msg)
        elif hasattr(e, "__class__") and e.__class__.__name__ == "ClassificationError":
            _die(f"Layer 1 classification failed: {error_msg}")
        else:
            _die(f"Layer 1 classification failed: {error_msg}")

    # Step 6: Layer 2 - Enrichment
    try:
        _progress("Layer 2: enriching…")
        l2_result = enrich_segments(l1_result)
    except Exception as e:
        error_msg = str(e)
        if "GEMINI_API_KEY" in error_msg:
            _die(error_msg)
        elif hasattr(e, "__class__") and e.__class__.__name__ == "EnrichmentError":
            _die(f"Layer 2 enrichment failed: {error_msg}")
        else:
            _die(f"Layer 2 enrichment failed: {error_msg}")

    # Step 7: Layer 3 - Allocation
    try:
        _progress("Layer 3: allocating…")
        l3_result = allocate_tasks(l2_result, phase=header.phase, day=header.day)
    except Exception as e:
        error_msg = str(e)
        if "GEMINI_API_KEY" in error_msg:
            _die(error_msg)
        elif hasattr(e, "__class__") and e.__class__.__name__ == "AllocationError":
            _die(f"Layer 3 allocation failed: {error_msg}")
        else:
            _die(f"Layer 3 allocation failed: {error_msg}")

    # Step 8: Partition non-task segments
    open_questions: list[ClassifiedSegment] = []
    decisions: list[ClassifiedSegment] = []
    noise: list[ClassifiedSegment] = []

    for seg in l1_result.segments:
        if seg.type == SegmentType.OPEN_QUESTION:
            open_questions.append(seg)
        elif seg.type == SegmentType.DECISION:
            decisions.append(seg)
        elif seg.type == SegmentType.NOISE:
            noise.append(seg)

    # Step 9: Collect gap_question_tasks
    gap_question_tasks = [
        task for task in (l3_result.in_sprint + l3_result.out_of_sprint) if task.gap_questions
    ]

    # Step 10: Format and print proposal
    proposal = _format_proposal(
        transcript_path, header, l3_result, open_questions, gap_question_tasks, decisions, noise
    )
    print(proposal)

    # Step 11: Build and write JSON artifact
    artifact = _build_json_artifact(
        transcript_path, header, l3_result, open_questions, decisions, noise
    )
    json_path = transcript_path.with_suffix(".json")
    json_path.write_text(json.dumps(artifact, indent=2))

    # Step 12: Notify user
    print(f"\nJSON artifact written to: {json_path}")


def app() -> None:
    """
    Entry point for the sprint-composer CLI.

    Subcommands:
      run <transcript_path>   — parse header, run L1→L2→L3, emit 5-block proposal
      (explain <task_id>      — T06 adds this subcommand here)

    With no subcommand: prints help + example command to stdout; exits 0.
    """
    parser = argparse.ArgumentParser(
        prog="sprint-composer",
        description="CLI agent that turns a raw meeting transcript into a structured 5-block sprint-plan proposal",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Run the pipeline on a transcript")
    run_parser.add_argument("transcript_path", type=Path, help="Path to the transcript file")

    # parse arguments
    args = parser.parse_args()

    if args.command == "run":
        _cmd_run(args.transcript_path)
    else:
        parser.print_help()
        sys.exit(0)
