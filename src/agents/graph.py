"""LangGraph State Machine definition for autonomous interconnection screening."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.letter_generator import generate_letter_markdown
from src.agents.state import (
    AuditAction,
    AuditEntry,
    InterconnectionState,
    WorkflowStep,
)
from src.agents.vision_extractor import MultimodalVisionExtractor
from src.observability import get_tracer
from src.schemas.screening import (
    OverallOutcome,
    ScreeningReport,
    ScreenStatus,
)
from src.schemas.tariff import TariffCitation, TariffJurisdiction
from src.tools.grid_screens import run_deterministic_screens
from src.utils.dataset import load_application

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Node Implementations
# -----------------------------------------------------------------------------


@get_tracer().trace_node("intake")
def intake_node(state: InterconnectionState) -> dict[str, Any]:
    """Validate incoming application package and establish initial state baseline."""
    app_id = state.get("application_id")
    if not app_id:
        return {
            "current_step": WorkflowStep.ERROR,
            "errors": ["Intake validation failed: 'application_id' is required."],
            "audit_log": [
                AuditEntry(
                    step=WorkflowStep.INTAKE,
                    action=AuditAction.ERROR_RECORDED,
                    message="Missing application_id during intake",
                )
            ],
            "requires_human_override": True,
        }

    return {
        "current_step": WorkflowStep.INTAKE,
        "audit_log": [
            AuditEntry(
                step=WorkflowStep.INTAKE,
                action=AuditAction.STATE_TRANSITION,
                message=f"Application {app_id} accepted for initial review intake",
                details={"application_id": app_id},
            )
        ],
    }


@get_tracer().trace_node("extraction")
def extraction_node(state: InterconnectionState) -> dict[str, Any]:
    """Validate or extract electrical parameters (Inverter, Transformer, SLD, Telemetry)."""
    app_id = state.get("application_id", "")
    app_data = state.get("application_data")
    raw_docs = state.get("raw_documents", [])

    extractor = MultimodalVisionExtractor()
    audit_entries: list[AuditEntry] = []

    # Identify potential SLD or cut-sheet paths in raw_documents or application package
    sld_path: Path | None = None
    cutsheet_path: Path | None = None

    for doc in raw_docs:
        p = Path(doc)
        doc_lower = p.name.lower()
        if ("single_line_diagram" in doc_lower or "sld" in doc_lower) and p.is_file():
            sld_path = p
        elif ("cutsheet" in doc_lower or "datasheet" in doc_lower) and p.is_file():
            cutsheet_path = p

    # Fallback to application dataset directory if application_id is known
    if (not sld_path or not cutsheet_path) and app_id:
        try:
            pkg = load_application(app_id)
            if not sld_path and pkg.get("single_line_diagram_path", Path()).is_file():
                sld_path = pkg["single_line_diagram_path"]
            if not cutsheet_path and pkg.get("inverter_cutsheet_path", Path()).is_file():
                cutsheet_path = pkg["inverter_cutsheet_path"]
        except Exception:
            pass

    # If app_data is not provided, record extraction error and pause for human override
    if app_data is None:
        return {
            "current_step": WorkflowStep.EXTRACTION,
            "errors": ["Extraction failed: No structured application data provided or extracted."],
            "audit_log": [
                AuditEntry(
                    step=WorkflowStep.EXTRACTION,
                    action=AuditAction.ERROR_RECORDED,
                    message="Missing application_data container",
                )
            ],
            "requires_human_override": True,
        }

    # Enrich with multimodal extraction if SLD/cutsheet available
    enriched_app = app_data
    if sld_path or cutsheet_path:
        try:
            enriched_app = extractor.enrich_application(
                app_data, sld_path=sld_path, cutsheet_path=cutsheet_path
            )
            audit_entries.append(
                AuditEntry(
                    step=WorkflowStep.EXTRACTION,
                    action=AuditAction.TOOL_INVOCATION,
                    message="Enriched application parameters via MultimodalVisionExtractor",
                    details={
                        "sld_extracted": sld_path is not None,
                        "cutsheet_extracted": cutsheet_path is not None,
                        "device": extractor.device,
                    },
                )
            )
        except Exception as e:
            logger.warning(f"Multimodal enrichment warning: {e}")

    audit_entries.append(
        AuditEntry(
            step=WorkflowStep.EXTRACTION,
            action=AuditAction.STATE_TRANSITION,
            message=(
                f"Verified electrical parameters: {enriched_app.total_export_capacity_kw} kW "
                f"export, {len(enriched_app.inverters)} inverter(s)"
            ),
            details={
                "export_kw": enriched_app.total_export_capacity_kw,
                "inverter_count": len(enriched_app.inverters),
                "has_disconnect_switch": (
                    enriched_app.sld_components.has_utility_disconnect_switch
                    if enriched_app.sld_components
                    else None
                ),
            },
        )
    )

    return {
        "current_step": WorkflowStep.EXTRACTION,
        "application_data": enriched_app,
        "audit_log": audit_entries,
    }


@get_tracer().trace_node("retrieval")
def retrieval_node(state: InterconnectionState) -> dict[str, Any]:
    """Retrieve regulatory grounding clauses and tariffs for the active jurisdiction."""
    app_id = state.get("application_id", "UNKNOWN")

    # In T-107, we establish the baseline regulatory citations for Rule 21 & IEEE 1547.
    # Future tickets connect dynamically to the HybridRetriever.
    citations: list[TariffCitation] = [
        TariffCitation(
            citation_id=f"CITE_{app_id}_RULE21_SCREEN_A",
            document_title="Electric Rule 21",
            jurisdiction=TariffJurisdiction.CA_RULE_21,
            section_hierarchy=["Rule 21", "Section D", "Screen A"],
            section_title="Screen A - Certified Equipment",
            page_number=6,
            source_filename="ca_rule_21_extract.pdf",
            relevance_score=0.98,
            citation_label="[CA Rule 21 § Screen A - Certified Equipment, p. 6]",
            exact_quote="The Generating Facility must utilize certified equipment packages.",
            chunk_id="CA_RULE_21_SEC_D_SCREEN_A",
        ),
        TariffCitation(
            citation_id=f"CITE_{app_id}_RULE21_SCREEN_D",
            document_title="Electric Rule 21",
            jurisdiction=TariffJurisdiction.CA_RULE_21,
            section_hierarchy=["Rule 21", "Section D", "Screen D"],
            section_title="Screen D - 15% Penetration Screen",
            page_number=14,
            source_filename="ca_rule_21_extract.pdf",
            relevance_score=0.99,
            citation_label="[CA Rule 21 § Screen D - 15% Penetration Screen, p. 14]",
            exact_quote=(
                "Aggregate generation on the line section must not exceed 15% of annual peak load."
            ),
            chunk_id="CA_RULE_21_SEC_D_SCREEN_D",
        ),
        TariffCitation(
            citation_id=f"CITE_{app_id}_IEEE1547_CLAUSE_8",
            document_title="IEEE Standard 1547-2018",
            jurisdiction=TariffJurisdiction.IEEE_1547,
            section_hierarchy=["IEEE 1547-2018", "Clause 8", "Clause 8.1"],
            section_title="Clause 8.1 - Anti-Islanding Protection",
            page_number=22,
            source_filename="ieee_1547_2018_extract.pdf",
            relevance_score=0.94,
            citation_label="[IEEE 1547-2018 § Clause 8.1 - Anti-Islanding Protection, p. 22]",
            exact_quote=(
                "The DER shall detect an unintentional island and cease to energize within 2.0s."
            ),
            chunk_id="IEEE_1547_CLAUSE_8_1",
        ),
    ]

    return {
        "current_step": WorkflowStep.REGULATORY_RETRIEVAL,
        "retrieved_citations": citations,
        "audit_log": [
            AuditEntry(
                step=WorkflowStep.REGULATORY_RETRIEVAL,
                action=AuditAction.CITATION_RETRIEVED,
                message=f"Retrieved {len(citations)} tariff citations for screening evaluation",
                details={"citation_ids": [c.citation_id for c in citations]},
            )
        ],
    }


@get_tracer().trace_node("screening")
def screening_node(state: InterconnectionState) -> dict[str, Any]:
    """Evaluate deterministic engineering screens and record any deficiencies."""
    app_data = state.get("application_data")
    if not app_data:
        return {
            "current_step": WorkflowStep.ERROR,
            "errors": ["Screening failed: No application data available for screen evaluation."],
            "requires_human_override": True,
        }

    screen_results, deficiencies = run_deterministic_screens(app_data)

    return {
        "current_step": WorkflowStep.DETERMINISTIC_SCREENING,
        "screen_results": screen_results,
        "deficiencies": deficiencies,
        "audit_log": [
            AuditEntry(
                step=WorkflowStep.DETERMINISTIC_SCREENING,
                action=AuditAction.SCREEN_EVALUATED,
                message=(
                    f"Evaluated {len(screen_results)} screens: "
                    f"{len(deficiencies)} deficiency(ies) identified"
                ),
                details={
                    "screens_evaluated": [s.screen_id for s in screen_results],
                    "deficiencies_count": len(deficiencies),
                },
            )
        ],
    }


@get_tracer().trace_node("synthesis")
def synthesis_node(state: InterconnectionState) -> dict[str, Any]:
    """Assemble final formal ScreeningReport and determine approval or deficiency status."""
    app_id = state.get("application_id", "UNKNOWN")
    screen_results = state.get("screen_results", [])
    deficiencies = state.get("deficiencies", [])
    app_data = state.get("application_data")

    has_failures = any(s.status == ScreenStatus.FAIL for s in screen_results)
    overall_outcome = (
        OverallOutcome.DEFICIENCY_ISSUED if has_failures else OverallOutcome.FAST_TRACK_APPROVED
    )
    requires_human_override = overall_outcome == OverallOutcome.DEFICIENCY_ISSUED

    agg_kw = app_data.total_export_capacity_kw if app_data else 0.0
    pen_pct: float | None = None
    if app_data and app_data.feeder_telemetry and app_data.feeder_telemetry.annual_peak_load_kw:
        feeder = app_data.feeder_telemetry
        pen_pct = round(
            ((feeder.existing_connected_generation_kw + agg_kw) / feeder.annual_peak_load_kw)
            * 100.0,
            2,
        )

    report = ScreeningReport(
        application_id=app_id,
        overall_outcome=overall_outcome,
        screens=screen_results,
        deficiencies=deficiencies,
        aggregate_generation_kw=agg_kw,
        feeder_penetration_pct=pen_pct,
        engineer_sign_off_required=requires_human_override,
    )

    synthesis_state: InterconnectionState = {
        **state,
        "overall_outcome": overall_outcome,
        "screening_report": report,
    }
    letter_md = generate_letter_markdown(synthesis_state)

    step = WorkflowStep.COMPLETE if not requires_human_override else WorkflowStep.SYNTHESIS

    return {
        "current_step": step,
        "overall_outcome": overall_outcome,
        "screening_report": report,
        "formal_letter_markdown": letter_md,
        "requires_human_override": requires_human_override,
        "audit_log": [
            AuditEntry(
                step=WorkflowStep.SYNTHESIS,
                action=AuditAction.TOOL_INVOCATION,
                message="Synthesized formal interconnection decision memo with citations",
                details={
                    "outcome": overall_outcome,
                    "deficiencies_count": len(deficiencies),
                    "letter_length_chars": len(letter_md),
                },
            ),
            AuditEntry(
                step=WorkflowStep.SYNTHESIS,
                action=AuditAction.STATE_TRANSITION,
                message=f"Screening report synthesized with outcome: {overall_outcome}",
                details={
                    "outcome": overall_outcome,
                    "requires_human_override": requires_human_override,
                },
            ),
        ],
    }


@get_tracer().trace_node("human_review")
def human_review_node(state: InterconnectionState) -> dict[str, Any]:
    """Human-in-the-loop review checkpoint for overrides and sign-off."""
    app_id = state.get("application_id", "UNKNOWN")
    return {
        "current_step": WorkflowStep.HUMAN_REVIEW,
        "audit_log": [
            AuditEntry(
                step=WorkflowStep.HUMAN_REVIEW,
                action=AuditAction.STATE_TRANSITION,
                message=f"Application {app_id} queued for human engineer review and sign-off",
            )
        ],
    }


@get_tracer().trace_node("error_rollback")
def error_rollback_node(state: InterconnectionState) -> dict[str, Any]:
    """Safely catch node failures, log diagnostics, and prevent workflow crash."""
    app_id = state.get("application_id", "UNKNOWN")
    err_msgs = state.get("errors", ["Unknown execution error occurred."])
    logger.error(f"Error rollback triggered for {app_id}: {err_msgs}")

    return {
        "current_step": WorkflowStep.ERROR,
        "requires_human_override": True,
        "audit_log": [
            AuditEntry(
                step=WorkflowStep.ERROR,
                action=AuditAction.ROLLBACK_TRIGGERED,
                message=f"Workflow rolled back due to error(s): {err_msgs[-1]}",
                details={"errors": err_msgs},
            )
        ],
    }


# -----------------------------------------------------------------------------
# Conditional Routing Functions
# -----------------------------------------------------------------------------


def route_after_intake(state: InterconnectionState) -> str:
    """Route to error rollback if intake errors exist, else to extraction."""
    if state.get("errors") or state.get("current_step") == WorkflowStep.ERROR:
        return "error_rollback"
    return "extraction"


def route_after_extraction(state: InterconnectionState) -> str:
    """Route to error rollback if extraction errors exist, else to retrieval."""
    if state.get("errors") or state.get("current_step") == WorkflowStep.ERROR:
        return "error_rollback"
    return "retrieval"


def route_after_screening(state: InterconnectionState) -> str:
    """Route to error rollback if screening errors exist, else to synthesis."""
    if state.get("errors") or state.get("current_step") == WorkflowStep.ERROR:
        return "error_rollback"
    return "synthesis"


def route_after_synthesis(state: InterconnectionState) -> str:
    """Route to human review if deficiencies exist, else finish workflow."""
    if state.get("requires_human_override"):
        return "human_review"
    return END


# -----------------------------------------------------------------------------
# Graph Factory & Compiler
# -----------------------------------------------------------------------------


def create_interconnection_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Construct and compile the LangGraph Interconnection Reviewer state machine.

    Args:
        checkpointer: Optional LangGraph checkpoint saver (defaults to MemorySaver).

    Returns:
        CompiledStateGraph ready for invoke(), stream(), and checkpointing.
    """
    workflow = StateGraph(InterconnectionState)

    # Add core workflow nodes
    workflow.add_node("intake", intake_node)
    workflow.add_node("extraction", extraction_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("screening", screening_node)
    workflow.add_node("synthesis", synthesis_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("error_rollback", error_rollback_node)

    # Define edges and conditional transitions
    workflow.add_edge(START, "intake")
    workflow.add_conditional_edges("intake", route_after_intake, ["extraction", "error_rollback"])
    workflow.add_conditional_edges(
        "extraction", route_after_extraction, ["retrieval", "error_rollback"]
    )
    workflow.add_edge("retrieval", "screening")
    workflow.add_conditional_edges(
        "screening", route_after_screening, ["synthesis", "error_rollback"]
    )
    workflow.add_conditional_edges("synthesis", route_after_synthesis, ["human_review", END])
    workflow.add_edge("human_review", END)
    workflow.add_edge("error_rollback", END)

    # Use MemorySaver by default if none provided
    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()

    return workflow.compile(checkpointer=active_checkpointer)
