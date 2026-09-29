"""Data Transfer Objects (DTOs) and request/response schemas for the InterconnectAI API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.agents.state import AuditEntry, WorkflowStep
from src.schemas.application import ApplicationSchema
from src.schemas.screening import DeficiencyItem, OverallOutcome, ScreenResult
from src.schemas.tariff import TariffJurisdiction


class HealthCheckResponse(BaseModel):
    """Health check status response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str = Field(default="healthy", description="Service health status")
    service: str = Field(default="InterconnectAI Screening API", description="Service description")
    version: str = Field(default="0.1.0", description="API version")
    supported_jurisdictions: list[str] = Field(
        default_factory=lambda: [TariffJurisdiction.CA_RULE_21.value],
        description="Supported regulatory rulebook jurisdictions",
    )


class ApplicationSummaryResponse(BaseModel):
    """Summary representation of a benchmark interconnection application for queue listing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: str = Field(..., description="Unique application identifier")
    applicant_name: str = Field(..., description="Applicant legal business or individual name")
    project_type: str = Field(..., description="Classification of the generation project")
    capacity_kw: float = Field(..., description="Aggregate nameplate/export capacity in kW")
    utility: str = Field(..., description="Target utility provider")
    feeder_id: str = Field(..., description="Assigned distribution feeder ID")
    expected_outcome: str = Field(..., description="Ground-truth expected outcome")
    failing_screens: list[str] = Field(
        default_factory=list, description="Ground-truth expected failing screens"
    )
    required_citations: list[str] = Field(
        default_factory=list, description="Mandatory tariff citation references"
    )


class ApplicationDetailResponse(BaseModel):
    """Detailed metadata and telemetry for a single benchmark application."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: str = Field(..., description="Unique application identifier")
    summary: ApplicationSummaryResponse = Field(..., description="High-level application metadata")
    telemetry: dict[str, Any] = Field(
        default_factory=dict, description="Feeder telemetry parameters"
    )
    files: dict[str, str] = Field(
        default_factory=dict, description="Associated document file names"
    )
    structured_schema: ApplicationSchema | None = Field(
        default=None, description="Pre-parsed electrical application schema if available"
    )


class ScreeningRunRequest(BaseModel):
    """Execution request payload for the interconnection technical review state machine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: str = Field(
        ..., description="Unique benchmark application ID or incoming submission ID"
    )
    application_data: ApplicationSchema | None = Field(
        default=None,
        description=(
            "Optional explicit electrical application schema. If omitted, the runner "
            "automatically resolves and loads schema data from the benchmark dataset."
        ),
    )
    raw_documents: list[str] = Field(
        default_factory=list,
        description="Optional paths to application PDFs, single-line diagrams, or cut-sheets.",
    )
    jurisdiction: TariffJurisdiction = Field(
        default=TariffJurisdiction.CA_RULE_21,
        description="Target tariff jurisdiction (e.g. CA Rule 21).",
    )


class ScreeningRunResponse(BaseModel):
    """Comprehensive output of the autonomous screening workflow execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: str = Field(..., description="Application identifier reviewed")
    overall_outcome: OverallOutcome = Field(
        ..., description="Overall screening determination (PASS, FAIL_DEFICIENT, etc.)"
    )
    screen_results: list[ScreenResult] = Field(
        default_factory=list, description="Evaluation results for Screens A through I"
    )
    deficiencies: list[DeficiencyItem] = Field(
        default_factory=list, description="Specific deficiencies and required statutory cures"
    )
    formal_letter_markdown: str | None = Field(
        default=None, description="Synthesized formal utility decision memo in Markdown"
    )
    audit_log: list[AuditEntry] = Field(
        default_factory=list, description="Complete chronological audit trail of state transitions"
    )
    execution_time_ms: float = Field(
        ..., description="Total execution time of the screening pipeline in milliseconds"
    )
    requires_human_override: bool = Field(
        default=False,
        description="Indicates whether engineering review or deficiency sign-off is required",
    )


class StreamEventPayload(BaseModel):
    """Payload representing an intermediate or terminal Server-Sent Event (SSE)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: str = Field(..., description="Event name: start, node_complete, error, done")
    node: str | None = Field(default=None, description="Active graph node name")
    step: WorkflowStep | None = Field(default=None, description="Workflow step enumeration")
    message: str = Field(default="", description="Human-readable event summary")
    data: dict[str, Any] = Field(default_factory=dict, description="Event data payload")
    timestamp_utc: str = Field(..., description="ISO 8601 UTC timestamp")
