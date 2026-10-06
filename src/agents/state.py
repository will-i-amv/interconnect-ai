"""LangGraph state schema and audit trail definitions for interconnection screening."""

from __future__ import annotations

import operator
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.application import ApplicationSchema
from src.schemas.screening import (
    DeficiencyItem,
    OverallOutcome,
    ScreeningReport,
    ScreenResult,
)
from src.schemas.tariff import TariffCitation


class WorkflowStep(StrEnum):
    """Stages in the autonomous interconnection screening lifecycle."""

    INTAKE = "INTAKE"
    EXTRACTION = "EXTRACTION"
    REGULATORY_RETRIEVAL = "REGULATORY_RETRIEVAL"
    DETERMINISTIC_SCREENING = "DETERMINISTIC_SCREENING"
    SYNTHESIS = "SYNTHESIS"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class AuditAction(StrEnum):
    """Types of auditable actions recorded during workflow execution."""

    STATE_TRANSITION = "STATE_TRANSITION"
    TOOL_INVOCATION = "TOOL_INVOCATION"
    CITATION_RETRIEVED = "CITATION_RETRIEVED"
    SCREEN_EVALUATED = "SCREEN_EVALUATED"
    ERROR_RECORDED = "ERROR_RECORDED"
    ROLLBACK_TRIGGERED = "ROLLBACK_TRIGGERED"
    OVERRIDE_APPLIED = "OVERRIDE_APPLIED"


class AuditEntry(BaseModel):
    """Deterministic, immutable record of an event in the agent state machine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of the recorded action",
    )
    step: WorkflowStep = Field(..., description="Workflow stage where action occurred")
    action: AuditAction = Field(..., description="Classification of action")
    message: str = Field(..., description="Human-readable event summary")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary structured context"
    )


def append_citations(
    existing: Sequence[TariffCitation],
    new_items: Sequence[TariffCitation],
) -> list[TariffCitation]:
    """Reducer that appends citations while deduplicating by citation_id."""
    seen = {cit.citation_id for cit in existing}
    merged = list(existing)
    for item in new_items:
        if item.citation_id not in seen:
            seen.add(item.citation_id)
            merged.append(item)
    return merged


def append_screens(
    existing: Sequence[ScreenResult],
    new_items: Sequence[ScreenResult],
) -> list[ScreenResult]:
    """Reducer that appends screen results, updating by screen_id if already present."""
    screen_map = {scr.screen_id: scr for scr in existing}
    for item in new_items:
        screen_map[item.screen_id] = item
    return list(screen_map.values())


def append_deficiencies(
    existing: Sequence[DeficiencyItem],
    new_items: Sequence[DeficiencyItem],
) -> list[DeficiencyItem]:
    """Reducer that appends deficiency items, updating by error code if already present."""
    def_map = {def_item.code: def_item for def_item in existing}
    for item in new_items:
        def_map[item.code] = item
    return list(def_map.values())


class InterconnectionState(TypedDict, total=False):
    """Central LangGraph State Schema for the Interconnection Reviewer Agent."""

    # Intake Identification
    application_id: str
    raw_documents: list[str]

    # Intake Technical Data
    application_data: ApplicationSchema | None

    # Regulatory Grounding (Phase 2 RAG)
    retrieved_citations: Annotated[list[TariffCitation], append_citations]

    # Engineering Screening & Deficiency (Phase 3 Tools & Synthesis)
    screen_results: Annotated[list[ScreenResult], append_screens]
    deficiencies: Annotated[list[DeficiencyItem], append_deficiencies]
    screening_report: ScreeningReport | None
    formal_letter_markdown: str | None

    # Control Flow & Status
    current_step: WorkflowStep
    overall_outcome: OverallOutcome | None

    # Telemetry, Audit Trail & Error Handling
    errors: Annotated[list[str], operator.add]
    audit_log: Annotated[list[AuditEntry], operator.add]

    # Human-in-the-loop Gate
    requires_human_override: bool
    human_override_notes: str | None
