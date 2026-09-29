"""Dataset loader and benchmark verification utilities for InterconnectAI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.schemas.application import (
    ApplicationSchema,
    DisconnectSwitchLocation,
    FeederTelemetrySchema,
    InterconnectionType,
    InverterSchema,
    SLDComponentSchema,
    TransformerSchema,
)


def get_dataset_root() -> Path:
    """Return the absolute path to the dataset root directory."""
    return Path(__file__).resolve().parent.parent.parent / "dataset"


def load_dataset_catalog() -> dict[str, Any]:
    """Load the master dataset catalog and benchmark ground-truth index."""
    catalog_path = get_dataset_root() / "dataset_index.json"
    if not catalog_path.is_file():
        raise FileNotFoundError(f"Dataset catalog not found at {catalog_path}")
    with catalog_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_applications() -> list[str]:
    """Return a sorted list of all benchmark application IDs."""
    catalog = load_dataset_catalog()
    return sorted(catalog.get("applications", {}).keys())


def load_application(application_id: str) -> dict[str, Any]:
    """Load paths and telemetry for a specific benchmark application case.

    Args:
        application_id: Unique benchmark identifier (e.g. 'APP-001-PASS-ROOFTOP-SOLAR')

    Returns:
        Dictionary containing metadata, file paths, and parsed grid telemetry.
    """
    catalog = load_dataset_catalog()
    apps = catalog.get("applications", {})
    if application_id not in apps:
        available = ", ".join(apps.keys())
        raise KeyError(f"Application '{application_id}' not found. Available: {available}")

    app_dir = get_dataset_root() / "applications" / application_id
    if not app_dir.is_dir():
        raise FileNotFoundError(f"Application directory missing: {app_dir}")

    form_path = app_dir / "application_form.pdf"
    cutsheet_path = app_dir / "inverter_cutsheet.pdf"
    sld_path = app_dir / "single_line_diagram.pdf"
    telemetry_path = app_dir / "grid_telemetry.json"

    telemetry: dict[str, Any] = {}
    if telemetry_path.is_file():
        with telemetry_path.open("r", encoding="utf-8") as f:
            telemetry = json.load(f)

    return {
        "application_id": application_id,
        "metadata": apps[application_id],
        "application_dir": app_dir,
        "application_form_path": form_path,
        "inverter_cutsheet_path": cutsheet_path,
        "single_line_diagram_path": sld_path,
        "telemetry_path": telemetry_path,
        "telemetry": telemetry,
    }


def get_tariff_path(filename: str) -> Path:
    """Return the absolute path to a tariff or standard document.

    Args:
        filename: Name of the tariff file (e.g. 'ca_rule_21_extract.pdf')
    """
    path = get_dataset_root() / "tariffs" / filename
    if not path.is_file():
        raise FileNotFoundError(f"Tariff document not found: {path}")
    return path


def load_application_schema(application_id: str) -> ApplicationSchema:
    """Construct a validated ApplicationSchema from benchmark catalog and telemetry.

    Args:
        application_id: Benchmark application identifier.

    Returns:
        Structured and validated ApplicationSchema instance.
    """
    catalog = load_dataset_catalog()
    apps = catalog.get("applications", {})
    if application_id not in apps:
        available = ", ".join(apps.keys())
        raise KeyError(f"Application '{application_id}' not found. Available: {available}")

    entry = apps[application_id]
    pkg = load_application(application_id)
    telemetry_raw = pkg["telemetry"]

    inv = InverterSchema(
        manufacturer="SMA Solar",
        model_name="Sunny Tripower",
        rated_ac_power_kw=entry["capacity_kw"],
        nominal_voltage_v=480.0,
        max_continuous_current_a=entry["capacity_kw"] * 1000 / (480 * 1.732),
        ul_1741_sb_certified="FAIL-NONCERTIFIED" not in application_id,
        ieee_1547_2018_compliant="FAIL-NONCERTIFIED" not in application_id,
        count=1,
    )

    telemetry = FeederTelemetrySchema(
        feeder_id=entry.get("feeder_id", "FEEDER-01"),
        utility=entry["utility"],
        nominal_voltage_kv=telemetry_raw.get("distribution_voltage_kv", 12.47),
        annual_peak_load_kw=telemetry_raw.get("feeder_peak_load_kw", 5000.0),
        minimum_daytime_load_kw=telemetry_raw.get("daytime_min_load_kw", 2000.0),
        existing_connected_generation_kw=telemetry_raw.get("existing_der_kw", 200.0),
    )

    sld = SLDComponentSchema(
        has_utility_disconnect_switch="MISSING-DISCONNECT" not in application_id,
        disconnect_switch_visible_break="MISSING-DISCONNECT" not in application_id,
        disconnect_switch_lockable="MISSING-DISCONNECT" not in application_id,
        disconnect_switch_location=(
            DisconnectSwitchLocation.NOT_DEPICTED
            if "MISSING-DISCONNECT" in application_id
            else DisconnectSwitchLocation.ADJACENT_TO_METER
        ),
        main_breaker_rating_a=max(400.0, (entry["capacity_kw"] * 1000 / (480 * 1.732)) * 1.25),
        main_breaker_kaic=65.0,
    )

    tx_rating = max(1000.0, entry["capacity_kw"] * 1.25)
    transformer = TransformerSchema(
        rating_kva=tx_rating,
        primary_voltage_kv=12.47,
        secondary_voltage_v=480.0,
        impedance_pct_z=2.5,
    )

    return ApplicationSchema(
        application_id=application_id,
        applicant_name=entry["applicant_name"],
        site_address="123 Solar Way",
        utility_provider=entry["utility"],
        utility_account_number="ACCT-98765",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=entry["capacity_kw"],
        service_voltage="480V 3-Phase",
        inverters=[inv],
        transformer=transformer,
        sld_components=sld,
        feeder_telemetry=telemetry,
    )
