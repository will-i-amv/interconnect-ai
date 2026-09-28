"""Automated unit and integration tests for formal letter generator (T-110)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from src.agents.graph import create_interconnection_graph
from src.agents.letter_generator import (
    LetterGenerator,
    export_letter_pdf,
    generate_letter_markdown,
)
from src.agents.state import AuditAction, InterconnectionState, WorkflowStep
from src.schemas.application import ApplicationSchema
from src.schemas.screening import OverallOutcome
from src.schemas.tariff import TariffCitation, TariffJurisdiction
from src.tools.grid_screens import run_deterministic_screens
from tests.test_agents_graph import build_test_application


@pytest.fixture
def sample_citations() -> list[TariffCitation]:
    """Sample tariff citations for grounding tests."""
    return [
        TariffCitation(
            citation_id="CITE_TEST_RULE21_SCREEN_D",
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
            citation_id="CITE_TEST_IEEE1547_CLAUSE_8",
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


def build_state_for_app(
    app: ApplicationSchema,
    citations: list[TariffCitation],
) -> InterconnectionState:
    """Helper to run screens and build evaluated state for letter generation."""
    screen_results, deficiencies = run_deterministic_screens(app)
    has_deficiencies = len(deficiencies) > 0
    outcome = (
        OverallOutcome.DEFICIENCY_ISSUED if has_deficiencies else OverallOutcome.FAST_TRACK_APPROVED
    )

    return {
        "application_id": app.application_id,
        "raw_documents": ["application_form.pdf", "single_line_diagram.pdf"],
        "application_data": app,
        "retrieved_citations": citations,
        "screen_results": screen_results,
        "deficiencies": deficiencies,
        "overall_outcome": outcome,
        "errors": [],
        "audit_log": [],
    }


def test_approval_letter_markdown_synthesis(sample_citations: list[TariffCitation]) -> None:
    """Verify approval letter contains approval determination, screen matrix, and next steps."""
    app = build_test_application("APP-001-PASS-ROOFTOP-SOLAR")
    state = build_state_for_app(app, sample_citations)

    md = generate_letter_markdown(state)

    # Document Header & Title
    assert "Distribution Interconnection Bureau" in md
    assert "FAST TRACK INITIAL REVIEW APPROVAL NOTICE" in md
    assert "APP-001-PASS-ROOFTOP-SOLAR" in md
    assert app.applicant_name in md
    assert "250.0 kW" in md

    # Executive Determination
    assert "Fast Track Initial Review clearance is hereby granted" in md

    # Screen Matrix
    assert "Technical Screen Evaluation Matrix" in md
    assert "| `SCREEN_A_APPLICABILITY` |" in md
    assert "| `SCREEN_D_PENETRATION_15PCT` |" in md
    assert "| **PASS** |" in md
    assert "| **FAIL** |" not in md

    # Citations
    assert "[CA Rule 21 § Screen D - 15% Penetration Screen, p. 14]" in md

    # Next steps for approval
    assert "Execute Interconnection Agreement" in md
    assert "Permission to Operate (PTO)" in md

    # Should not contain deficiencies section
    assert "Identified Engineering Deficiencies" not in md


def test_deficiency_letter_markdown_synthesis_penetration(
    sample_citations: list[TariffCitation],
) -> None:
    """Verify deficiency letter for Screen D violation on APP-002."""
    app = build_test_application("APP-002-FAIL-PENETRATION-15PCT")
    state = build_state_for_app(app, sample_citations)

    md = generate_letter_markdown(state)

    assert "DEFICIENCY NOTICE & INTENT TO DENY" in md
    assert "APP-002-FAIL-PENETRATION-15PCT" in md
    assert "formal engineering deficiency(ies)" in md
    assert "Identified Engineering Deficiencies & Required Cure Actions" in md

    # Specific deficiency details
    assert "DEF_PENETRATION_EXCEEDED" in md
    assert "`SCREEN_D_PENETRATION_15PCT`" in md
    assert "10 Business Days" in md
    assert "Supplemental Review" in md

    # Screen Table must show FAIL for Screen D
    assert "| `SCREEN_D_PENETRATION_15PCT` |" in md
    assert "| **FAIL** |" in md

    # Response options
    assert "Option 1 (Cure Deficiencies)" in md
    assert "Option 2 (Supplemental Review)" in md


def test_deficiency_letter_markdown_synthesis_noncertified_inverter(
    sample_citations: list[TariffCitation],
) -> None:
    """Verify deficiency letter for Screen B violation on APP-003."""
    app = build_test_application("APP-003-FAIL-NONCERTIFIED-INV")
    state = build_state_for_app(app, sample_citations)

    md = generate_letter_markdown(state)

    assert "DEFICIENCY NOTICE" in md
    assert "DEF_NON_CERTIFIED_EQUIPMENT" in md
    assert "`SCREEN_B_CERTIFIED_EQUIPMENT`" in md
    assert "UL 1741" in md


def test_deficiency_letter_markdown_synthesis_missing_disconnect(
    sample_citations: list[TariffCitation],
) -> None:
    """Verify deficiency letter for Screen H violation on APP-004."""
    app = build_test_application("APP-004-FAIL-MISSING-DISCONNECT")
    state = build_state_for_app(app, sample_citations)

    md = generate_letter_markdown(state)

    assert "DEFICIENCY NOTICE" in md
    assert "DEF_MISSING_DISCONNECT_SWITCH" in md
    assert "`SCREEN_H_DISCONNECT_SWITCH`" in md
    assert "visible air-gap" in md


def test_export_letter_pdf(
    tmp_path: Path,
    sample_citations: list[TariffCitation],
) -> None:
    """Verify PDF generation from Markdown letter produces valid multi-page vector document."""
    app = build_test_application("APP-001-PASS-ROOFTOP-SOLAR")
    state = build_state_for_app(app, sample_citations)
    md = generate_letter_markdown(state)

    pdf_path = tmp_path / "approval_notice.pdf"
    result_path = export_letter_pdf(md, pdf_path, is_approval=True)

    assert result_path == pdf_path
    assert pdf_path.is_file()
    assert pdf_path.stat().st_size > 1000

    # Inspect PDF contents with PyMuPDF
    doc = pymupdf.open(pdf_path)
    assert len(doc) >= 1
    full_pdf_text = "".join(page.get_text() for page in doc)
    assert "APPROVAL NOTICE" in full_pdf_text
    assert app.applicant_name in full_pdf_text
    assert "APP-001-PASS-ROOFTOP-SOLAR" in full_pdf_text
    doc.close()


def test_letter_generator_class_coordinator(
    tmp_path: Path,
    sample_citations: list[TariffCitation],
) -> None:
    """Verify LetterGenerator coordinator class produces both Markdown and PDF."""
    generator = LetterGenerator(output_dir=tmp_path)
    app = build_test_application("APP-002-FAIL-PENETRATION-15PCT")
    state = build_state_for_app(app, sample_citations)

    md, pdf_path = generator.generate(state)

    assert isinstance(md, str)
    assert "DEFICIENCY NOTICE" in md
    assert pdf_path is not None
    assert pdf_path.is_file()

    doc = pymupdf.open(pdf_path)
    assert len(doc) >= 1
    doc.close()


def test_langgraph_synthesis_node_generates_formal_letter(
    sample_citations: list[TariffCitation],
) -> None:
    """Verify LangGraph end-to-end execution populates formal_letter_markdown in synthesis_node."""
    graph = create_interconnection_graph()
    app = build_test_application("APP-001-PASS-ROOFTOP-SOLAR")

    initial_state: InterconnectionState = {
        "application_id": app.application_id,
        "raw_documents": ["application_form.pdf"],
        "application_data": app,
        "retrieved_citations": sample_citations,
        "screen_results": [],
        "deficiencies": [],
        "errors": [],
        "audit_log": [],
    }

    config = {"configurable": {"thread_id": "thread-letter-test-1"}}
    final_state = graph.invoke(initial_state, config=config)

    assert final_state["current_step"] == WorkflowStep.COMPLETE
    assert final_state["overall_outcome"] == OverallOutcome.FAST_TRACK_APPROVED
    assert final_state["formal_letter_markdown"] is not None

    letter_text = final_state["formal_letter_markdown"]
    assert "FAST TRACK INITIAL REVIEW APPROVAL NOTICE" in letter_text
    assert "Technical Screen Evaluation Matrix" in letter_text
    assert "Verification & Professional Engineering Sign-Off" in letter_text

    # Audit log should capture synthesis tool invocation
    actions = [entry.action for entry in final_state["audit_log"]]
    assert AuditAction.TOOL_INVOCATION in actions
