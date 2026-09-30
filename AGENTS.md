# AGENTS.md — InterconnectAI Engineering Guidelines

Welcome to InterconnectAI! This document contains essential development workflows, coding standards, and architectural invariants for AI coding assistants.

---

## 1. Quick Commands Cheatsheet

### Testing & Quality Gates
- **Run all unit & integration tests**: `pytest tests/`
- **Run a single test file**: `pytest tests/test_benchmarks.py`
- **Run pre-commit hooks**: `pre-commit run --all-files`
- **Run Ruff linter**: `ruff check .`
- **Run Ruff formatter**: `ruff format --check .` (or `ruff format .` to apply)
- **Run DeepEval evaluation harness**: `python -m evals.run_benchmarks --threshold 0.90`

### Local Execution & Docker
- **Start full-stack container environment**: `docker compose up --build`
- **Run containerized benchmarks**: `docker compose run --rm evals`
- **Start local Qdrant only**: `docker compose up -d qdrant`
- **Start FastAPI backend**: `uvicorn api.main:app --reload --port 8000`
- **Start Streamlit review console**: `streamlit run frontend/app.py --server.port 8501`

---

## 2. Core Architectural Invariants (Must Never Violate)

1. **Deterministic Math Enforcement (Zero LLM Calculations)**:
   - The LLM must **never** execute power flow or distribution screening math (e.g. 15% feeder penetration, voltage drop, short-circuit ratio).
   - All engineering calculations must be executed by pure, isolated deterministic Python tools in `src/tools/grid_screens.py`. The LLM's role is restricted to document parsing and memo synthesis.
2. **Strict Pydantic v2 Models**:
   - All data contracts must use Pydantic v2 with `model_config = ConfigDict(extra="forbid", frozen=True)`.
   - Never use `class Config:` (Pydantic v1 syntax).
3. **Regulatory Citation Grounding**:
   - Every deficiency or approval citation must reference valid sections of California Rule 21, IEEE 1547-2018, or FERC Order 2023.
   - Never invent or hallucinate regulatory clauses (e.g. "Rule 99", "Screen Z").
4. **Code Style & Formatting**:
   - Python 3.12+ idioms (`StrEnum`, `int | float`, `pathlib.Path`).
   - Line length limit: **Strictly <= 100 characters** (`line-length = 100`). Always wrap multiline string literals in parentheses.
   - End-of-file newlines and clean imports (`ruff` / `isort`).

---

## 3. Directory Map & Component Roles

- `src/agents/`: LangGraph `StateGraph` state machine (`graph.py`, `state.py`, `letter_generator.py`).
- `src/screens/` & `src/tools/`: Deterministic Rule 21 and IEEE 1547 calculation engines and multimodal vision extractors.
- `src/rag/`: Hybrid regulatory retrieval (Qdrant dense vectors + BM25 keyword index + cross-encoder reranker).
- `src/observability/`: OpenTelemetry and Langfuse tracing instrumentation.
- `api/`: FastAPI async runner service with SSE streaming endpoints (`/api/screen/*`).
- `frontend/`: Streamlit review console, split-screen PDF viewer, and PE override modal dialog.
- `evals/`: 25-application Golden Dataset (`golden_dataset.json`) and DeepEval benchmark harness (`run_benchmarks.py`).
- `dataset/`: Authoritative tariff markdown/PDF extracts (`dataset/tariffs/`) and benchmark applications.
- `tests/`: 130 comprehensive unit and integration tests.

---

## 4. Git & Workflow Etiquette

- **Never commit directly to git** unless explicitly instructed by the user. Always provide the suggested `git add` and `git commit` commands with descriptive commit messages.
- Always run `pre-commit run --all-files` and `pytest tests/` before considering any task complete.
