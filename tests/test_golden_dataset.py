"""Unit tests for the 25-application Golden Evaluation Dataset (T-116)."""

from __future__ import annotations

import json

from evals.golden_dataset import (
    GoldenApplication,
    GoldenDataset,
    get_golden_dataset_path,
    load_golden_dataset,
    verify_all_golden_applications,
)
from src.schemas.application import ApplicationSchema
from src.schemas.screening import OverallOutcome, ScreenId, ScreenStatus
from src.tools.grid_screens import run_deterministic_screens


def test_golden_dataset_file_exists_and_parses():
    """Verify that evals/golden_dataset.json exists and is valid JSON."""
    path = get_golden_dataset_path()
    assert path.is_file(), f"Golden dataset file not found at {path}"

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert "version" in data
    assert "applications" in data
    assert len(data["applications"]) == 25


def test_golden_dataset_composition():
    """Verify golden dataset contains exactly 25 applications: 15 passes and 10 deficiencies."""
    dataset = load_golden_dataset()
    assert isinstance(dataset, GoldenDataset)
    assert dataset.total_count == 25
    assert dataset.pass_count == 15
    assert dataset.fail_count == 10
    assert len(dataset.applications) == 25

    passes = [
        a
        for a in dataset.applications
        if a.ground_truth.expected_overall_outcome == OverallOutcome.FAST_TRACK_APPROVED
    ]
    fails = [
        a
        for a in dataset.applications
        if a.ground_truth.expected_overall_outcome == OverallOutcome.DEFICIENCY_ISSUED
    ]

    assert len(passes) == 15
    assert len(fails) == 10


def test_golden_dataset_schemas_and_immutability():
    """Verify every application complies with strict Pydantic v2 ApplicationSchema."""
    dataset = load_golden_dataset()
    for app in dataset.applications:
        assert isinstance(app, GoldenApplication)
        assert isinstance(app.application_data, ApplicationSchema)
        assert app.application_id.startswith("GOLD-")
        assert app.application_data.application_id == app.application_id
        assert app.application_data.total_export_capacity_kw > 0
        assert len(app.application_data.inverters) >= 1
        assert app.application_data.feeder_telemetry is not None


def test_golden_dataset_utility_and_technology_diversity():
    """Verify golden dataset covers all major California utilities and DER technologies."""
    dataset = load_golden_dataset()
    utilities = {a.application_data.utility_provider for a in dataset.applications}
    project_types = {a.application_data.project_type for a in dataset.applications}

    assert "Pacific Gas & Electric (PG&E)" in utilities
    assert "Southern California Edison (SCE)" in utilities
    assert "San Diego Gas & Electric (SDG&E)" in utilities

    # Technologies: Solar PV, Hybrid, Battery storage, EV charging
    assert len(project_types) >= 3


def test_all_15_clean_passes_evaluate_to_approval():
    """Verify that all 15 clean passes achieve 100% pass across all screens."""
    dataset = load_golden_dataset()
    passes = [
        a
        for a in dataset.applications
        if a.ground_truth.expected_overall_outcome == OverallOutcome.FAST_TRACK_APPROVED
    ]

    for golden_app in passes:
        screen_results, deficiencies = run_deterministic_screens(golden_app.application_data)
        failing_screens = [s for s in screen_results if s.status == ScreenStatus.FAIL]

        assert len(failing_screens) == 0, (
            f"Expected 0 failing screens for {golden_app.application_id}, "
            f"got {[s.screen_id for s in failing_screens]}"
        )
        assert len(deficiencies) == 0, (
            f"Expected 0 deficiencies for {golden_app.application_id}, "
            f"got {[d.code for d in deficiencies]}"
        )


def test_all_10_known_deficiencies_trigger_exact_failures():
    """Verify that all 10 known deficiencies fail their designated screens with exact codes."""
    dataset = load_golden_dataset()
    fails = [
        a
        for a in dataset.applications
        if a.ground_truth.expected_overall_outcome == OverallOutcome.DEFICIENCY_ISSUED
    ]

    for golden_app in fails:
        screen_results, deficiencies = run_deterministic_screens(golden_app.application_data)
        actual_failing_screens = [
            s.screen_id for s in screen_results if s.status == ScreenStatus.FAIL
        ]
        actual_deficiency_codes = [d.code for d in deficiencies]

        expected_screens = golden_app.ground_truth.failing_screens
        expected_codes = golden_app.ground_truth.expected_deficiency_codes

        assert (
            len(actual_failing_screens) > 0
        ), f"Application {golden_app.application_id} was expected to fail but passed all screens."
        assert sorted(actual_failing_screens) == sorted(expected_screens), (
            f"Failing screens mismatch for {golden_app.application_id}: "
            f"expected {expected_screens}, got {actual_failing_screens}"
        )
        assert sorted(actual_deficiency_codes) == sorted(expected_codes), (
            f"Deficiency codes mismatch for {golden_app.application_id}: "
            f"expected {expected_codes}, got {actual_deficiency_codes}"
        )


def test_deficiency_coverage_across_technical_screens():
    """Verify known deficiencies test a wide spectrum of individual and compound screens."""
    dataset = load_golden_dataset()
    fails = [
        a
        for a in dataset.applications
        if a.ground_truth.expected_overall_outcome == OverallOutcome.DEFICIENCY_ISSUED
    ]

    tested_failing_screens = {
        screen for app in fails for screen in app.ground_truth.failing_screens
    }

    # Verify coverage of Screen A, B, C, D, F, H
    assert ScreenId.SCREEN_A_APPLICABILITY in tested_failing_screens
    assert ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT in tested_failing_screens
    assert ScreenId.SCREEN_C_VOLTAGE_DROP in tested_failing_screens
    assert ScreenId.SCREEN_D_PENETRATION_15PCT in tested_failing_screens
    assert ScreenId.SCREEN_F_SHORT_CIRCUIT_RATIO in tested_failing_screens
    assert ScreenId.SCREEN_H_DISCONNECT_SWITCH in tested_failing_screens

    # Verify compound failure tests exist
    compound_cases = [a for a in fails if len(a.ground_truth.failing_screens) > 1]
    assert len(compound_cases) >= 2


def test_verify_all_golden_applications_helper():
    """Verify that verify_all_golden_applications reports 100% validity."""
    results = verify_all_golden_applications()
    assert len(results) == 25

    invalid = [r for r in results if not r["is_valid"]]
    assert len(invalid) == 0, f"Validation failed for: {invalid}"

    for r in results:
        assert r["outcome_match"] is True
        assert r["screens_match"] is True
        assert r["codes_match"] is True
