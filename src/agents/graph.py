"""LangGraph State Machine definition for autonomous interconnection screening."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.state import (
    AuditAction,
    AuditEntry,
    InterconnectionState,
    WorkflowStep,
)
from src.schemas.screening import (
    DeficiencyItem,
    OverallOutcome,
    ScreenId,
    ScreeningReport,
    ScreenResult,
    ScreenStatus,
)
from src.schemas.tariff import TariffCitation, TariffJurisdiction

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Node Implementations
# -----------------------------------------------------------------------------


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


def extraction_node(state: InterconnectionState) -> dict[str, Any]:
    """Validate or extract electrical parameters (Inverter, Transformer, SLD, Telemetry)."""
    app_data = state.get("application_data")
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

    return {
        "current_step": WorkflowStep.EXTRACTION,
        "audit_log": [
            AuditEntry(
                step=WorkflowStep.EXTRACTION,
                action=AuditAction.STATE_TRANSITION,
                message=(
                    f"Verified electrical parameters: {app_data.total_export_capacity_kw} kW "
                    f"export, {len(app_data.inverters)} inverter(s)"
                ),
                details={
                    "export_kw": app_data.total_export_capacity_kw,
                    "inverter_count": len(app_data.inverters),
                },
            )
        ],
    }


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


def screening_node(state: InterconnectionState) -> dict[str, Any]:
    """Evaluate deterministic engineering screens and record any deficiencies."""
    app_data = state.get("application_data")
    if not app_data:
        return {
            "current_step": WorkflowStep.ERROR,
            "errors": ["Screening failed: No application data available for screen evaluation."],
            "requires_human_override": True,
        }

    screen_results: list[ScreenResult] = []
    deficiencies: list[DeficiencyItem] = []

    # Screen B: Certified Equipment Screen
    all_certified = all(
        inv.ul_1741_sb_certified and inv.ieee_1547_2018_compliant for inv in app_data.inverters
    )
    if all_certified:
        screen_results.append(
            ScreenResult(
                screen_id=ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT,
                screen_name="Certified Equipment Screen",
                status=ScreenStatus.PASS,
                calculated_value="All inverters UL 1741-SB & IEEE 1547-2018 certified",
                threshold_value="UL 1741-SB & IEEE 1547-2018",
                citation="CPUC Rule 21 Section D.1",
                reasoning="All inverters hold required smart inverter safety certifications.",
            )
        )
    else:
        screen_results.append(
            ScreenResult(
                screen_id=ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT,
                screen_name="Certified Equipment Screen",
                status=ScreenStatus.FAIL,
                calculated_value="Non-certified inverter equipment detected",
                threshold_value="UL 1741-SB & IEEE 1547-2018",
                citation="CPUC Rule 21 Section D.1",
                reasoning=(
                    "Proposed inverter package lacks UL 1741-SB smart inverter certification."
                ),
            )
        )
        deficiencies.append(
            DeficiencyItem(
                code="DEF_NON_CERTIFIED_EQUIPMENT",
                title="Non-Certified Inverter Equipment",
                description=(
                    "Proposed inverter package lacks UL 1741-SB smart inverter certification."
                ),
                violating_screen=ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT,
                required_cure_action="Replace proposed inverter with a UL 1741-SB certified model.",
                cure_deadline_business_days=10,
                tariff_citation="CPUC Rule 21 Section D.1 / E.2",
            )
        )

    # Screen D: 15% Penetration Screen
    feeder = app_data.feeder_telemetry
    total_der_kw = feeder.existing_connected_generation_kw + app_data.total_export_capacity_kw
    penetration_pct = (total_der_kw / feeder.annual_peak_load_kw) * 100.0

    if penetration_pct <= 15.0:
        screen_results.append(
            ScreenResult(
                screen_id=ScreenId.SCREEN_D_PENETRATION_15PCT,
                screen_name="15% Feeder Penetration Screen",
                status=ScreenStatus.PASS,
                calculated_value=round(penetration_pct, 2),
                threshold_value="<= 15.0%",
                citation="CPUC Rule 21 Section D.2",
                reasoning=(
                    f"Aggregate feeder penetration of {penetration_pct:.1f}% is within "
                    "the 15.0% fast-track threshold."
                ),
            )
        )
    else:
        screen_results.append(
            ScreenResult(
                screen_id=ScreenId.SCREEN_D_PENETRATION_15PCT,
                screen_name="15% Feeder Penetration Screen",
                status=ScreenStatus.FAIL,
                calculated_value=round(penetration_pct, 2),
                threshold_value="<= 15.0%",
                citation="CPUC Rule 21 Section D.2",
                reasoning=(
                    f"Aggregate feeder penetration of {penetration_pct:.1f}% exceeds "
                    "the 15.0% fast-track limit."
                ),
            )
        )
        deficiencies.append(
            DeficiencyItem(
                code="DEF_PENETRATION_EXCEEDED",
                title="Feeder Penetration Limit Exceeded",
                description=(
                    f"Aggregate feeder penetration of {penetration_pct:.1f}% exceeds "
                    "the 15.0% fast-track limit."
                ),
                violating_screen=ScreenId.SCREEN_D_PENETRATION_15PCT,
                required_cure_action=(
                    "Application must proceed to Supplemental Review "
                    "or reduce project export capacity."
                ),
                cure_deadline_business_days=10,
                tariff_citation="CPUC Rule 21 Section D.2 & Section F",
            )
        )

    # Screen H: Disconnect Switch Screen
    has_compliant_disconnect = (
        app_data.sld_components.has_utility_disconnect_switch
        and app_data.sld_components.disconnect_switch_visible_break
        and app_data.sld_components.disconnect_switch_lockable
    )
    if has_compliant_disconnect:
        screen_results.append(
            ScreenResult(
                screen_id=ScreenId.SCREEN_H_DISCONNECT_SWITCH,
                screen_name="Visible AC Disconnect Switch",
                status=ScreenStatus.PASS,
                calculated_value="Compliant disconnect present on SLD",
                threshold_value="Visible, lockable, utility-accessible AC switch",
                citation="CPUC Rule 21 Section D.4",
                reasoning="Single-Line Diagram verifies external lockable AC disconnect switch.",
            )
        )
    else:
        screen_results.append(
            ScreenResult(
                screen_id=ScreenId.SCREEN_H_DISCONNECT_SWITCH,
                screen_name="Visible AC Disconnect Switch",
                status=ScreenStatus.FAIL,
                calculated_value="Missing or non-accessible AC disconnect switch",
                threshold_value="Visible, lockable, utility-accessible AC switch",
                citation="CPUC Rule 21 Section D.4",
                reasoning=(
                    "SLD omits a visible-break, utility-accessible, lockable AC disconnect switch."
                ),
            )
        )
        deficiencies.append(
            DeficiencyItem(
                code="DEF_MISSING_DISCONNECT_SWITCH",
                title="Missing or Non-Compliant AC Disconnect Switch",
                description=(
                    "SLD omits a visible-break, utility-accessible, lockable AC disconnect switch."
                ),
                violating_screen=ScreenId.SCREEN_H_DISCONNECT_SWITCH,
                required_cure_action=(
                    "Update Single-Line Diagram to depict a lockable, "
                    "utility-accessible exterior AC disconnect."
                ),
                cure_deadline_business_days=10,
                tariff_citation="CPUC Rule 21 Section D.4 / Safety Standards",
            )
        )

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

    letter_md = (
        f"# Interconnection Review Notice: {app_id}\n\n"
        f"**Outcome**: {overall_outcome}\n"
        f"**Screens Evaluated**: {len(screen_results)}\n"
        f"**Deficiencies**: {len(deficiencies)}\n"
    )

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
                action=AuditAction.STATE_TRANSITION,
                message=f"Screening report synthesized with outcome: {overall_outcome}",
                details={
                    "outcome": overall_outcome,
                    "requires_human_override": requires_human_override,
                },
            )
        ],
    }


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


def error_rollback_node(state: InterconnectionState) -> dict[str, Any]:
    """Safely catch node failures, log diagnostics, and prevent workflow crash."""
    app_id = state.get("application_id", "UNKNOWN")
    err_msgs = state.get("errors", ["Unknown execution error occurred."])
    logger.error("Error rollback triggered for %s: %s", app_id, err_msgs)

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
