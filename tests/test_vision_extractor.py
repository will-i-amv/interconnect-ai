"""Automated unit and integration tests for Multimodal Vision Extractor (T-109)."""

from __future__ import annotations

import base64

import pytest
from PIL import Image

from src.agents.graph import create_interconnection_graph
from src.agents.state import AuditAction, InterconnectionState, WorkflowStep
from src.agents.vision_extractor import (
    CutsheetVisionExtractor,
    MultimodalVisionExtractor,
    SLDVisionExtractor,
    detect_device,
    encode_image_base64,
    render_pdf_to_images,
)
from src.schemas.application import (
    ApplicationSchema,
    DisconnectSwitchLocation,
    FeederTelemetrySchema,
    InterconnectionType,
    InverterSchema,
    SLDComponentSchema,
    TransformerSchema,
)
from src.utils.dataset import load_application


def test_detect_device() -> None:
    """Verify hardware acceleration device detection returns standard device string."""
    device = detect_device()
    assert device in {"cuda", "mps", "cpu"}


def test_render_pdf_to_images() -> None:
    """Verify PDF rendering to PIL Images with proper dimensions and color format."""
    pkg = load_application("APP-001-PASS-ROOFTOP-SOLAR")
    images = render_pdf_to_images(pkg["single_line_diagram_path"], dpi=100)

    assert len(images) == 1
    img = images[0]
    assert isinstance(img, Image.Image)
    assert img.mode == "RGB"
    assert img.width > 500
    assert img.height > 300


def test_encode_image_base64() -> None:
    """Verify base64 image encoding produces valid decodable string."""
    img = Image.new("RGB", (64, 64), color="blue")
    b64_str = encode_image_base64(img, format="PNG")

    assert isinstance(b64_str, str)
    decoded = base64.b64decode(b64_str)
    assert len(decoded) > 0


class TestSLDVisionExtractor:
    """Unit tests for Single-Line Diagram electrical component extraction."""

    @pytest.fixture
    def extractor(self) -> SLDVisionExtractor:
        return SLDVisionExtractor()

    def test_extract_app001_compliant_switch(self, extractor: SLDVisionExtractor) -> None:
        """Verify extraction on APP-001 with compliant exterior visible-break switch."""
        pkg = load_application("APP-001-PASS-ROOFTOP-SOLAR")
        result = extractor.extract(pkg["single_line_diagram_path"])

        components = result.components
        assert components.has_utility_disconnect_switch is True
        assert components.disconnect_switch_visible_break is True
        assert components.disconnect_switch_lockable is True
        assert components.disconnect_switch_location == DisconnectSwitchLocation.ADJACENT_TO_METER
        assert components.revenue_meter_depicted is True
        assert result.project_name is not None
        assert "SunTech Logistics" in result.project_name
        assert result.confidence_score >= 0.90

    def test_extract_app002_compliant_switch(self, extractor: SLDVisionExtractor) -> None:
        """Verify extraction on APP-002 large capacity project."""
        pkg = load_application("APP-002-FAIL-PENETRATION-15PCT")
        result = extractor.extract(pkg["single_line_diagram_path"])

        components = result.components
        assert components.has_utility_disconnect_switch is True
        assert components.disconnect_switch_location == DisconnectSwitchLocation.ADJACENT_TO_METER
        assert result.project_name is not None
        assert "Golden State Agripower" in result.project_name

    def test_extract_app003_compliant_switch(self, extractor: SLDVisionExtractor) -> None:
        """Verify extraction on APP-003 project."""
        pkg = load_application("APP-003-FAIL-NONCERTIFIED-INV")
        result = extractor.extract(pkg["single_line_diagram_path"])

        components = result.components
        assert components.has_utility_disconnect_switch is True
        assert components.disconnect_switch_location == DisconnectSwitchLocation.ADJACENT_TO_METER
        assert result.project_name is not None
        assert "Horizon Manufacturing" in result.project_name

    def test_extract_app004_missing_disconnect_switch(self, extractor: SLDVisionExtractor) -> None:
        """Verify detection of missing disconnect switch and direct bus tap deficiency."""
        pkg = load_application("APP-004-FAIL-MISSING-DISCONNECT")
        result = extractor.extract(pkg["single_line_diagram_path"])

        components = result.components
        assert components.has_utility_disconnect_switch is False
        assert components.disconnect_switch_visible_break is False
        assert components.disconnect_switch_lockable is False
        assert components.disconnect_switch_location == DisconnectSwitchLocation.NOT_DEPICTED
        assert components.main_breaker_kaic == 65.0
        assert components.grounding_electrode_system_depicted is True
        assert result.project_name is not None
        assert "Pacific Coast Storage" in result.project_name


class TestCutsheetVisionExtractor:
    """Unit tests for Inverter Cut-Sheet and Datasheet parameter extraction."""

    @pytest.fixture
    def extractor(self) -> CutsheetVisionExtractor:
        return CutsheetVisionExtractor()

    def test_extract_app001_certified_inverter(self, extractor: CutsheetVisionExtractor) -> None:
        """Verify extraction on APP-001 (SMA Sunny Tripower CORE1 50-US)."""
        pkg = load_application("APP-001-PASS-ROOFTOP-SOLAR")
        result = extractor.extract(pkg["inverter_cutsheet_path"])

        inv = result.inverter
        assert "SMA" in inv.model_name or "Sunny Tripower" in inv.model_name
        assert inv.rated_ac_power_kw == 250.0
        assert inv.nominal_voltage_v == 480.0
        assert inv.max_continuous_current_a == 300.7
        assert inv.power_factor_min == -0.80
        assert inv.power_factor_max == 0.80
        assert inv.ul_1741_sb_certified is True
        assert inv.ieee_1547_2018_compliant is True
        assert inv.anti_islanding_trip_time_s <= 2.0
        assert inv.cec_listed is True

    def test_extract_app002_certified_inverter(self, extractor: CutsheetVisionExtractor) -> None:
        """Verify extraction on APP-002 (Sungrow SG250HX)."""
        pkg = load_application("APP-002-FAIL-PENETRATION-15PCT")
        result = extractor.extract(pkg["inverter_cutsheet_path"])

        inv = result.inverter
        assert "Sungrow" in inv.model_name
        assert inv.rated_ac_power_kw == 1200.0
        assert inv.nominal_voltage_v == 480.0
        assert inv.max_continuous_current_a == 1443.4
        assert inv.ul_1741_sb_certified is True
        assert inv.ieee_1547_2018_compliant is True

    def test_extract_app003_noncertified_inverter(self, extractor: CutsheetVisionExtractor) -> None:
        """Verify negation detection on APP-003 (legacy uncertified inverter)."""
        pkg = load_application("APP-003-FAIL-NONCERTIFIED-INV")
        result = extractor.extract(pkg["inverter_cutsheet_path"])

        inv = result.inverter
        assert "SunMaster" in inv.model_name
        assert inv.rated_ac_power_kw == 500.0
        assert inv.power_factor_min == 1.0
        assert inv.power_factor_max == 1.0
        # Negation check: Lacks UL 1741-SB and IEEE 1547-2018
        assert inv.ul_1741_sb_certified is False
        assert inv.ieee_1547_2018_compliant is False
        assert inv.cec_listed is False

    def test_extract_app004_storage_inverter(self, extractor: CutsheetVisionExtractor) -> None:
        """Verify extraction on APP-004 (Tesla Megapack 2XL)."""
        pkg = load_application("APP-004-FAIL-MISSING-DISCONNECT")
        result = extractor.extract(pkg["inverter_cutsheet_path"])

        inv = result.inverter
        assert "Tesla" in inv.model_name or "Megapack" in inv.model_name
        assert inv.rated_ac_power_kw == 750.0
        assert inv.ul_1741_sb_certified is True
        assert inv.ieee_1547_2018_compliant is True


class TestMultimodalVisionExtractor:
    """Integration tests for master MultimodalVisionExtractor."""

    @pytest.fixture
    def master_extractor(self) -> MultimodalVisionExtractor:
        return MultimodalVisionExtractor()

    def test_extract_application_package(self, master_extractor: MultimodalVisionExtractor) -> None:
        """Verify extracting package directory yields both SLD and inverter specs."""
        pkg = load_application("APP-001-PASS-ROOFTOP-SOLAR")
        sld_components, inverters = master_extractor.extract_application_package(
            pkg["application_dir"]
        )

        assert isinstance(sld_components, SLDComponentSchema)
        assert len(inverters) == 1
        assert inverters[0].rated_ac_power_kw == 250.0
        assert sld_components.has_utility_disconnect_switch is True

    def test_enrich_application(self, master_extractor: MultimodalVisionExtractor) -> None:
        """Verify enrichment of base ApplicationSchema with extracted PDF artifacts."""
        base_inv = InverterSchema(
            manufacturer="Placeholder",
            model_name="Generic",
            rated_ac_power_kw=250.0,
            nominal_voltage_v=480.0,
            max_continuous_current_a=300.0,
            ul_1741_sb_certified=True,
            ieee_1547_2018_compliant=True,
            count=1,
        )
        base_app = ApplicationSchema(
            application_id="APP-TEST-ENRICH",
            applicant_name="Test Entity",
            site_address="123 Grid Way",
            utility_provider="Test Utility",
            utility_account_number="ACCT-123",
            project_type=InterconnectionType.SOLAR_PV,
            total_export_capacity_kw=250.0,
            service_voltage="480V 3-Phase",
            inverters=[base_inv],
        )

        pkg = load_application("APP-001-PASS-ROOFTOP-SOLAR")
        enriched = master_extractor.enrich_application(
            base_app,
            sld_path=pkg["single_line_diagram_path"],
            cutsheet_path=pkg["inverter_cutsheet_path"],
        )

        assert enriched.sld_components is not None
        assert enriched.sld_components.has_utility_disconnect_switch is True
        assert enriched.inverters[0].model_name != "Generic"
        assert "Sunny Tripower" in enriched.inverters[0].model_name


def test_langgraph_extraction_node_multimodal_integration() -> None:
    """Verify LangGraph extraction_node automatically enriches state using raw_documents."""
    graph = create_interconnection_graph()
    pkg = load_application("APP-001-PASS-ROOFTOP-SOLAR")

    # Initial state with unpopulated sld_components
    base_inv = InverterSchema(
        manufacturer="Draft Inverter",
        model_name="Draft Model",
        rated_ac_power_kw=250.0,
        nominal_voltage_v=480.0,
        max_continuous_current_a=300.0,
        ul_1741_sb_certified=True,
        ieee_1547_2018_compliant=True,
        count=1,
    )
    tx = TransformerSchema(
        rating_kva=1000.0,
        primary_voltage_kv=12.47,
        secondary_voltage_v=480.0,
        impedance_pct_z=2.5,
    )
    feeder = FeederTelemetrySchema(
        feeder_id="FEEDER-01",
        utility="Pacific Gas & Electric",
        nominal_voltage_kv=12.47,
        annual_peak_load_kw=5000.0,
        minimum_daytime_load_kw=2000.0,
        existing_connected_generation_kw=200.0,
    )
    app = ApplicationSchema(
        application_id=pkg["application_id"],
        applicant_name=pkg["metadata"]["applicant_name"],
        site_address="123 Solar Way",
        utility_provider=pkg["metadata"]["utility"],
        utility_account_number="ACCT-98765",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=pkg["metadata"]["capacity_kw"],
        service_voltage="480V 3-Phase",
        inverters=[base_inv],
        transformer=tx,
        sld_components=None,  # Intentionally missing to test multimodal auto-enrichment
        feeder_telemetry=feeder,
    )

    initial_state: InterconnectionState = {
        "application_id": pkg["application_id"],
        "raw_documents": [
            str(pkg["single_line_diagram_path"]),
            str(pkg["inverter_cutsheet_path"]),
        ],
        "application_data": app,
        "retrieved_citations": [],
        "screen_results": [],
        "deficiencies": [],
        "errors": [],
        "audit_log": [],
    }

    config = {"configurable": {"thread_id": "thread-vision-test-1"}}
    final_state = graph.invoke(initial_state, config=config)

    assert final_state["current_step"] == WorkflowStep.COMPLETE
    assert final_state["application_data"] is not None
    assert final_state["application_data"].sld_components is not None
    assert final_state["application_data"].sld_components.has_utility_disconnect_switch is True

    # Audit log should record tool invocation
    actions = [entry.action for entry in final_state["audit_log"]]
    assert AuditAction.TOOL_INVOCATION in actions
