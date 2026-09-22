"""Dataset loader and benchmark verification utilities for InterconnectAI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
