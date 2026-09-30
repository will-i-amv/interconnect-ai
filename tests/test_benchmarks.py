"""Unit and integration tests for DeepEval automated evaluation harness & benchmark runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from evals.golden_dataset import load_golden_dataset
from evals.run_benchmarks import (
    BenchmarkReport,
    TariffCorpusVerifier,
    build_deepeval_test_cases,
    evaluate_citation_faithfulness,
    evaluate_extraction_completeness,
    evaluate_screening_accuracy,
    run_benchmarks,
)


def test_tariff_corpus_verifier_valid_rule21() -> None:
    """Verify that TariffCorpusVerifier recognizes standard CPUC Rule 21 citations."""
    verifier = TariffCorpusVerifier()

    is_valid, tariff, sec, flags = verifier.verify_citation(
        "CPUC Rule 21 Section D Screen D (15% Penetration)"
    )
    assert is_valid is True
    assert tariff == "CPUC Electric Rule 21"
    assert sec == "Screen D"
    assert len(flags) == 0

    is_valid, tariff, sec, flags = verifier.verify_citation(
        "CPUC Electric Rule 21 Section C.2 (Deficiency Notice & 10-day cure)"
    )
    assert is_valid is True
    assert tariff == "CPUC Electric Rule 21"
    assert sec == "Section C.2"
    assert len(flags) == 0


def test_tariff_corpus_verifier_valid_ieee1547() -> None:
    """Verify that TariffCorpusVerifier recognizes IEEE 1547-2018 clauses."""
    verifier = TariffCorpusVerifier()

    is_valid, tariff, sec, flags = verifier.verify_citation(
        "IEEE 1547-2018 Clause 8.1 (Anti-Islanding Disconnect <= 2.0s)"
    )
    assert is_valid is True
    assert tariff == "IEEE Standard 1547-2018"
    assert sec == "Clause 8.1"
    assert len(flags) == 0

    is_valid, tariff, sec, flags = verifier.verify_citation(
        "IEEE Standard 1547-2018 Clause 5.1 (Power Factor Requirements)"
    )
    assert is_valid is True
    assert tariff == "IEEE Standard 1547-2018"
    assert sec == "Clause 5.1"
    assert len(flags) == 0


def test_tariff_corpus_verifier_hallucination_detection() -> None:
    """Verify that TariffCorpusVerifier flags invented or hallucinated citations."""
    verifier = TariffCorpusVerifier()

    # Hallucinated CPUC rule number
    is_valid, _, _, flags = verifier.verify_citation(
        "CPUC Rule 99 Section Z Fast Track Auto Exemption"
    )
    assert is_valid is False
    assert any("hallucination" in f.lower() or "unknown" in f.lower() for f in flags)

    # Hallucinated screen letter (Screen Z does not exist)
    is_valid, _, _, flags = verifier.verify_citation(
        "CPUC Rule 21 Screen Z Phantom Feeder Invalidation"
    )
    assert is_valid is False
    assert any("hallucination" in f.lower() for f in flags)

    # Completely unreferenced citation
    is_valid, _, _, flags = verifier.verify_citation("Random Internal Guideline Article 42")
    assert is_valid is False
    assert any("unreferenced" in f.lower() for f in flags)


def test_screening_accuracy_evaluation() -> None:
    """Verify technical screen precision and zero false passes on the golden dataset."""
    dataset = load_golden_dataset()
    metrics, details = evaluate_screening_accuracy(dataset)

    assert metrics["total_applications"] == 25
    assert metrics["total_screens_evaluated"] == 25 * 8  # 8 implemented deterministic screens
    assert metrics["total_screens_matched"] == metrics["total_screens_evaluated"]
    assert metrics["screen_accuracy"] == 1.0
    assert metrics["outcome_accuracy"] == 1.0
    assert metrics["code_match_rate"] == 1.0
    assert metrics["false_passes_on_safety"] == 0
    assert metrics["safety_screen_precision"] == 1.0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1_score"] == 1.0

    # Ensure all 25 applications have individual details
    assert len(details) == 25
    for d in details:
        assert d.outcome_matched is True
        assert d.deficiency_codes_matched is True
        assert d.false_pass_on_safety is False


def test_citation_faithfulness_evaluation() -> None:
    """Verify regulatory citation faithfulness across all golden applications."""
    dataset = load_golden_dataset()
    metrics, details = evaluate_citation_faithfulness(dataset)

    assert metrics["total_citations_checked"] > 50
    assert metrics["valid_citations"] == metrics["total_citations_checked"]
    assert metrics["hallucinated_citations"] == 0
    assert metrics["citation_faithfulness_score"] >= 0.95
    assert metrics["hallucination_rate"] == 0.0
    assert len(details) == metrics["total_citations_checked"]


def test_extraction_completeness_evaluation() -> None:
    """Verify that electrical schema extraction completeness meets or exceeds 98%."""
    dataset = load_golden_dataset()
    metrics = evaluate_extraction_completeness(dataset)

    assert metrics["total_fields_inspected"] > 200
    assert metrics["populated_fields"] > 200
    assert metrics["extraction_completeness_score"] >= 0.98


def test_deepeval_test_cases_construction() -> None:
    """Verify that DeepEval LLMTestCase instances are constructed with complete schemas."""
    dataset = load_golden_dataset()
    test_cases = build_deepeval_test_cases(dataset)

    assert len(test_cases) == 25
    for tc in test_cases:
        assert tc.input and "Interconnection Application" in tc.input
        assert tc.actual_output and "Determination:" in tc.actual_output
        assert tc.expected_output and "Expected Outcome:" in tc.expected_output
        assert len(tc.retrieval_context) >= 1


def test_run_benchmarks_end_to_end(tmp_path: Path) -> None:
    """Verify complete benchmark execution and report generation."""
    output_path = tmp_path / "benchmark_test_results.json"
    report = run_benchmarks(threshold=0.90, verbose=True)
    output_path.write_text(report.model_dump_json(), encoding="utf-8")
    assert output_path.is_file()

    assert isinstance(report, BenchmarkReport)
    assert report.total_applications == 25
    assert report.overall_passed is True
    assert len(report.metrics) == 7

    # Check metric names
    metric_names = [m.metric_name for m in report.metrics]
    assert "Technical Screen Accuracy" in metric_names
    assert "Safety Screen Precision (0 False Passes)" in metric_names
    assert "Deficiency Code Exact Match Rate" in metric_names
    assert "Tariff Citation Faithfulness" in metric_names
    assert "Hallucination Rate" in metric_names
    assert "Extraction Completeness" in metric_names
    assert "Mean Screening Latency" in metric_names

    # Check all passed
    for m in report.metrics:
        assert m.passed is True


def test_run_benchmarks_ci_gate_failure() -> None:
    """Verify that CI quality gate fails when threshold is set above attainable scores."""
    # Using an impossible threshold > 1.0
    report = run_benchmarks(threshold=1.05)
    assert report.overall_passed is False

    failing_metrics = [m for m in report.metrics if not m.passed]
    assert len(failing_metrics) > 0


def test_cli_runner_execution(tmp_path: Path) -> None:
    """Verify that running python -m evals.run_benchmarks exits with code 0."""
    output_json = tmp_path / "cli_output.json"
    cmd = [
        sys.executable,
        "-m",
        "evals.run_benchmarks",
        "--threshold",
        "0.90",
        "--output",
        str(output_json),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"CLI runner failed: {proc.stderr}"
    assert "Overall Benchmark Status: PASSED" in proc.stdout
    assert output_json.is_file()
