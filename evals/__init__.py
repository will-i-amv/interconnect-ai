"""Evaluation benchmarks and Golden Dataset test harness."""

from typing import Any

from evals.golden_dataset import (
    GoldenApplication,
    GoldenDataset,
    GoldenGroundTruth,
    build_golden_dataset,
    get_golden_dataset_path,
    load_golden_dataset,
    save_golden_dataset,
    verify_all_golden_applications,
    verify_golden_application,
)

_LAZY_BENCHMARK_EXPORTS = {
    "BenchmarkMetricResult",
    "BenchmarkReport",
    "CitationFaithfulnessDetail",
    "ScreenAccuracyDetail",
    "TariffCorpusVerifier",
    "build_deepeval_test_cases",
    "evaluate_citation_faithfulness",
    "evaluate_extraction_completeness",
    "evaluate_screening_accuracy",
    "run_benchmarks",
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_BENCHMARK_EXPORTS:
        import evals.run_benchmarks as rb

        return getattr(rb, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BenchmarkMetricResult",
    "BenchmarkReport",
    "CitationFaithfulnessDetail",
    "GoldenApplication",
    "GoldenDataset",
    "GoldenGroundTruth",
    "ScreenAccuracyDetail",
    "TariffCorpusVerifier",
    "build_deepeval_test_cases",
    "build_golden_dataset",
    "evaluate_citation_faithfulness",
    "evaluate_extraction_completeness",
    "evaluate_screening_accuracy",
    "get_golden_dataset_path",
    "load_golden_dataset",
    "run_benchmarks",
    "save_golden_dataset",
    "verify_all_golden_applications",
    "verify_golden_application",
]
