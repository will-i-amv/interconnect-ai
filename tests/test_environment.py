"""Baseline environment and packaging verification tests."""

import sys
from pathlib import Path


def test_python_version() -> None:
    """Ensure runtime Python version meets minimum requirement (>= 3.11)."""
    assert sys.version_info >= (3, 11), f"Python >= 3.11 required, found: {sys.version}"


def test_core_package_import() -> None:
    """Verify that root package and version string can be imported."""
    import src

    assert hasattr(src, "__version__")
    assert src.__version__ == "0.1.0"


def test_subpackages_importable() -> None:
    """Verify all architectural subpackages are importable."""
    import src.agents
    import src.ml
    import src.observability
    import src.rag
    import src.schemas
    import src.tools

    assert src.schemas is not None
    assert src.rag is not None
    assert src.agents is not None
    assert src.tools is not None
    assert src.observability is not None
    assert src.ml is not None


def test_project_structure_exists() -> None:
    """Verify essential project directories and configuration files exist."""
    root = Path(__file__).resolve().parent.parent

    expected_files = [
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "docker-compose.yml",
        ".env.example",
        ".pre-commit-config.yaml",
    ]

    for filename in expected_files:
        filepath = root / filename
        assert filepath.is_file(), f"Expected file '{filename}' was not found at {filepath}"

    expected_dirs = [
        "src",
        "api",
        "dataset/tariffs",
        "dataset/applications",
        "evals",
        "tests",
    ]

    for dirname in expected_dirs:
        dirpath = root / dirname
        assert dirpath.is_dir(), f"Expected directory '{dirname}' was not found at {dirpath}"
