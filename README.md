# InterconnectAI

**Autonomous Grid Interconnection Technical Reviewer & Screening Copilot**

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-orange)](https://github.com/langchain-ai/langgraph)
[![DeepEval](https://img.shields.io/badge/DeepEval-Evaluations-purple)](https://github.com/confident-ai/deepeval)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Tests: 130 Passed](https://img.shields.io/badge/Tests-130%20Passed-brightgreen)](tests/)

InterconnectAI automates the intake, engineering document validation, deterministic mathematical screening, and formal regulatory memo synthesis for utility distributed energy resources (solar PV, battery energy storage, wind, and EV infrastructure) across complex interconnection queues.

---

## Table of Contents

- [Executive Summary & Industry Context](#executive-summary--industry-context)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Core Engineering Guarantees](#core-engineering-guarantees)
- [Interconnection Domain Glossary](docs/glossary.md)
- [Repository Structure](#repository-structure)
- [Input Contracts & Schemas](#input-contracts--schemas)
- [Implementation Roadmap & Milestones](#implementation-roadmap--milestones)
- [Quickstart & Local Setup](#quickstart--local-setup)
- [Automated Testing & Evaluation Suite](#automated-testing--evaluation-suite)
- [Evaluation Targets vs. Achieved Benchmarks](#evaluation-targets-vs-achieved-benchmarks)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [License](#license)

---

## Executive Summary & Industry Context

Across United States regional transmission operators (CAISO, PJM, ERCOT, NYISO) and electric distribution utilities, the queue for interconnecting new generation and storage exceeds **2,600 GW**—more than double the existing US commercial generating capacity. Under federal mandates (**FERC Order 2023**) and state frameworks (**California Public Utilities Commission Electric Rule 21**, **IEEE Standard 1547-2018**), utilities are legally required to evaluate Fast Track and Initial Review applications within strict statutory windows (typically 10–30 business days).

> [!TIP]
> **Domain Glossary**: For detailed engineering definitions, statutory screening criteria (Screens A through M), IEEE 1547 mandates, and tariff terminology, see the [Interconnection Domain Glossary](docs/glossary.md).

However, each application demands hours of senior distribution engineer review:
1. **Multi-Exhibit Parsing**: Ingesting complex Single-Line Diagrams (SLDs), cut-sheets, and inverter datasheets.
2. **Deterministic Screen Execution**: Verifying electrical limits—including the 15% annual peak load feeder penetration limit, starting voltage drop flicker (IEEE 1453), short-circuit ratio (SCR), and anti-islanding disconnect times.
3. **Statutory Notice Generation**: Cross-referencing utility tariff rulebooks and drafting binding **Deficiency Notices** or **Approval Memorandums** citing exact legal sections.

**InterconnectAI** solves this bottleneck with an end-to-end multi-agent pipeline combining layout-aware multimodal extraction, hybrid RAG over authoritative utility tariffs, isolated deterministic calculation engines, and an interactive human-in-the-loop review console.

---

## Key Features

- **Multimodal Single-Line Diagram & Cut-Sheet Extraction**: Automatically parses electrical schematics and manufacturer spec sheets into strictly validated Pydantic models.
- **Hybrid Regulatory RAG**: Combines FastEmbed BGE dense embeddings with BM25 sparse keyword search via Reciprocal Rank Fusion (RRF) and cross-encoder reranking over governing utility tariffs.
- **Deterministic Math Enforcement**: The LLM is never relied upon for distribution engineering math. All 8 technical screens are executed by isolated, unit-tested deterministic Python calculation engines.
- **Stateful LangGraph Workflow**: Coordinates application intake, schema extraction, tariff retrieval, screening calculation, and synthesis through an observable state machine.
- **Publication-Ready Decision Memos**: Generates formal utility approval notices and statutory deficiency letters in Markdown and styled multi-page PDF format with exact regulatory citations.
- **Streamlit Review Console**: Split-screen interface with an embedded vector PDF viewer on the left and a live evaluation matrix with LangGraph reasoning traces on the right.
- **Human-in-the-Loop Override & PE Sign-Off**: Native modal dialog (`@st.dialog`) enabling licensed Professional Engineers (PE) to override parameters, trigger live re-evaluations, and stamp decisions with an immutable audit trail.
- **Automated Evaluations & Observability**: Integrated with Langfuse and OpenTelemetry for distributed tracing, alongside a DeepEval benchmark harness operating against a 25-application Golden Dataset.

---

## System Architecture

```
+---------------------------------------------------------------------------------------+
|                               Streamlit Review Console                                |
|        (Master Queue Dashboard + Split-Screen PDF Viewer + PE Override Modal)         |
+-------------------------------------------+-------------------------------------------+
                                            | REST API / SSE Stream
+-------------------------------------------v-------------------------------------------+
|                               FastAPI Async Runner Service                            |
|             (/api/applications, /api/screen/run, /api/screen/stream, /health)          |
+-------------------------------------------+-------------------------------------------+
                                            |
                    +-----------------------+-----------------------+
                    |                                               |
+-------------------v--------------------+      +-------------------v-------------------+
|      Multimodal Parsing & Intake       |      |     Hybrid RAG Tariff Retrieval       |
|  - Application Form PDF Extraction     |      |  - Qdrant Vector DB (Dense Embeddings)|
|  - Inverter Cut-Sheet Parsing          |      |  - BM25 Lexical Keyword Search        |
|  - Single-Line Diagram (SLD) Vision    |      |  - Reciprocal Rank Fusion (RRF)       |
+-------------------+--------------------+      +-------------------+-------------------+
                    |                                               |
                    +-----------------------+-----------------------+
                                            |
+-------------------------------------------v-------------------------------------------+
|                      LangGraph Screening State Machine                                |
|   Intake -> Extraction -> Tariff Retrieval -> Screening Engine -> Memo Synthesis       |
+-------------------------------------------+-------------------------------------------+
                                            |
                    +-----------------------+-----------------------+
                    |                                               |
+-------------------v--------------------+      +-------------------v-------------------+
|    Deterministic Screening Engines     |      |       Observability & Evals           |
|  - Screen A: Applicability (3 MW)      |      |  - Langfuse Tracing & Latency Telemetry|
|  - Screen B: UL 1741-SB Inverter Cert  |      |  - OpenTelemetry Callbacks            |
|  - Screen C: Voltage Drop & Flicker    |      |  - Golden Dataset (25 Applications)   |
|  - Screen D: 15% Feeder Penetration    |      |  - DeepEval Citation Faithfulness     |
|  - Screen E: Short-Circuit Duty        |      |  - Hallucination Rejection Gate       |
|  - Screen F: Short Circuit Ratio (SCR) |      +---------------------------------------+
|  - Screen H: AC Disconnect Switch      |
|  - Screen I: Anti-Islanding Protection |
+----------------------------------------+
```

---

## Core Engineering Guarantees

1. **Deterministic Math Enforcement**: The LLM is strictly restricted from performing distribution power flow or feeder capacity calculations. All equations (e.g., aggregate generation penetration percentage, fault duty contribution) run in pure Python deterministic engines with `100%` unit test coverage.
2. **Strict Tariff Citation Attribution**: Every deficiency notice item or approval condition must ground in an exact section of the governing tariff (e.g., `CPUC Rule 21 Section D Screen D`, `IEEE 1547-2018 Clause 8.1`). Hallucinated rules immediately trip CI/CD failure gates.
3. **Human-in-the-Loop Gateway**: The system cannot deliver binding legal notices to applicants autonomously. A reviewing utility engineer must verify findings and stamp approval via the review console.
4. **Unified Python Full-Stack**: End-to-end Python eliminates Node.js/npm dependencies, enabling seamless model reuse between FastAPI, LangGraph, and Streamlit.
5. **Hardware-Agnostic Execution**: Dense embedding and multimodal pipelines run seamlessly on NVIDIA CUDA, Apple Silicon MPS, or CPU fallbacks without manual configuration.

---

## Repository Structure

```text
interconnect-ai/
├── api/                             # FastAPI async backend service
│   ├── main.py                      # Application factory, CORS, /health
│   ├── routes/                      # Route controllers (/api/applications, /api/screen/*)
│   └── schemas.py                   # REST DTOs and SSE event payloads
├── frontend/                        # Streamlit web application
│   ├── app.py                       # Application entrypoint & navigation router
│   ├── api_client.py                # Resilient HTTP client with local fallback
│   ├── styles.py                    # Dark-theme design tokens & CSS styling
│   ├── components/
│   │   ├── override_dialog.py       # @st.dialog modal for PE override & sign-off
│   │   └── pdf_viewer.py            # Embedded multi-page vector PDF viewer
│   └── views/
│       ├── dashboard.py             # Master queue browser with KPI metrics
│       └── review_console.py        # Split-screen engineer evaluation console
├── src/                             # Core business logic & AI pipelines
│   ├── agents/
│   │   ├── graph.py                 # LangGraph StateGraph orchestration
│   │   ├── letter_generator.py      # Publication-ready decision memo generator
│   │   ├── state.py                 # InterconnectionState & AuditEntry models
│   │   └── vision_extractor.py      # Multimodal extractor for SLDs and cut-sheets
│   ├── observability/
│   │   └── tracer.py                # InterconnectTracer (Langfuse & in-memory)
│   ├── rag/
│   │   ├── chunker.py               # Markdown and PDF layout-aware chunker
│   │   ├── ingest.py                # Tariff ingestion pipeline
│   │   ├── reranker.py              # Cross-encoder reranker
│   │   └── retriever.py             # Hybrid Qdrant + BM25 reciprocal rank fusion
│   ├── schemas/
│   │   ├── application.py           # ApplicationSchema, InverterSchema, FeederTelemetry
│   │   ├── screening.py             # ScreenResult, DeficiencyItem, OverallOutcome
│   │   └── tariff.py                # TariffCitation and jurisdiction models
│   └── tools/
│       └── grid_screens.py          # Deterministic Rule 21 & IEEE 1547 calculators
├── evals/                           # Evaluation harness & benchmarks
│   ├── golden_dataset.json          # 25 synthetic applications (15 passes, 10 fails)
│   ├── golden_dataset.py            # Golden dataset loader & verification utilities
│   └── run_benchmarks.py            # DeepEval automated evaluation runner & CI gate
├── dataset/                         # Local evaluation and sample data
│   ├── applications/                # Benchmark application exhibits (PDFs + JSON)
│   └── tariffs/                     # Authoritative tariff rulebooks (Rule 21, IEEE 1547)
├── docs/                            # Architectural specifications & business logic dictionary
│   ├── glossary.md                  # Comprehensive electric interconnection & business logic glossary
│   └── ticket_descriptions.md       # Roadmap & engineering ticket breakdown
├── tests/                           # Comprehensive automated test suite (130 tests)
├── AGENTS.md                        # AI coding assistant guidelines & architectural invariants
├── CLAUDE.md                        # Claude Code project configuration & imports
├── Dockerfile                       # Multi-stage Dockerfile (backend, frontend, evals)
├── .dockerignore                    # Excluded local virtualenvs, caches, and test artifacts
├── docker-compose.yml               # Multi-container orchestration (Qdrant, Backend, Frontend, Evals)
├── pyproject.toml                   # Project metadata, dependencies, and tool settings
├── requirements.txt                 # Core runtime dependencies
└── requirements-dev.txt             # Development and testing dependencies
```

---

## Input Contracts & Schemas

| Artifact | Source / Format | Purpose | Validation / Leakage Controls |
|---|---|---|---|
| **Interconnection Application** | Standard Form PDF | Applicant profile, project capacity (kW), Point of Common Coupling (PCC) | Validated against strict `ApplicationSchema` Pydantic model |
| **Equipment Cut-Sheets** | Manufacturer Datasheet PDF | Inverter specs, UL 1741-SB / IEEE 1547 compliance, power factor range | Verified against California Energy Commission (CEC) equipment listings |
| **Single-Line Diagram (SLD)** | Vector / Raster PDF | Electrical schematics, AC disconnect switches, meter placements, breaker ratings | Extracted via Vision-LLM + OCR; requires engineer visual confirmation |
| **Feeder Telemetry** | Time-series / JSON | Annual peak load, minimum daytime load (MDL), existing connected generation | Read-only input feeding deterministic screening calculators |
| **Tariff Documents** | Utility Rulebook PDF / Markdown | California Rule 21, FERC Order 2023, IEEE 1547 standard clauses | Chunked, embedded, and indexed in Qdrant; frozen during runtime |

---

## Implementation Roadmap & Milestones

The engineering scope encompasses **Phases 1 through 5 (Core Architecture - 100% Completed)**, followed by optional production extensions (Phases 6 and 7):

- [x] **Phase 1: Foundation & Schemas** (`T-101` – `T-103`)
  - Environment setup, benchmark application dataset, and Pydantic engineering schemas.
- [x] **Phase 2: Hybrid RAG & Knowledge Retrieval** (`T-104` – `T-106`)
  - Layout-aware PDF chunker, Qdrant vector database, BM25 keyword index with RRF, and cross-encoder reranker.
- [x] **Phase 3: Agentic Screening State Machine** (`T-107` – `T-110`)
  - LangGraph state machine, deterministic screening engines (Rule 21 & IEEE 1547), multimodal vision extractor, and formal decision memo generator.
- [x] **Phase 4: Full-Stack Serving & Streamlit UI** (`T-111` – `T-114`)
  - FastAPI async runner with SSE streaming, Streamlit master dashboard, split-screen review console, and human-in-the-loop PE override modal.
- [x] **Phase 5: Automated Evals & Observability** (`T-115` – `T-117`)
  - Langfuse/Phoenix distributed tracing, 25-application Golden Dataset, and DeepEval regulatory citation faithfulness evaluation harness.
- [ ] **Phase 6: [OPTIONAL ADD-ON] Production Hardening & Live Ingestion** (`T-118` – `T-124`)
  - Hybrid regulatory fetcher with caching, S3/MinIO cloud object storage, multi-jurisdiction tariff router, local LLM serving (vLLM/Ollama), SLD LoRA fine-tuning, and PostgreSQL persistent state checkpointing (`AsyncPostgresSaver`).
- [ ] **Phase 7: [OPTIONAL ADD-ON] Compound AI / Tabular ML Modeling** (`T-125` – `T-127`)
  - Historical queue ingestion, LightGBM/XGBoost training for study completion delay and upgrade costs.

---

## Quickstart & Local Setup

### Prerequisites

- **Docker & Docker Compose** (recommended for zero-config containerized spin-up)
- **Python 3.12+** (for native local development)

---

### Option A: Full-Stack Docker Launch (Recommended)

Run the entire InterconnectAI ecosystem (Qdrant vector database, FastAPI async backend, and Streamlit review console) with a single command:

```bash
# 1. Clone repository
git clone https://github.com/will-i-amv/interconnect-ai.git
cd interconnect-ai

# 2. Configure environment
cp .env.example .env

# 3. Build & start all services
docker compose up --build
```

**Access Points:**
- **Streamlit Review Console**: `http://localhost:8501`
- **FastAPI Backend & Swagger API Docs**: `http://localhost:8000/docs`
- **Qdrant Vector Database**: `http://localhost:6333/dashboard`

---

### Option B: Native Python Development

For local code development with hot reloading:

#### 1. Virtual Environment & Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\Activate.ps1

# Install editable package with dev dependencies:
pip install -e ".[dev]"
```

#### 2. Configure Environment

```bash
cp .env.example .env
```

#### 3. Start Qdrant Vector Database

```bash
docker compose up -d qdrant
```

#### 4. Ingest Utility Tariffs

```bash
python -m src.rag.ingest --tariff-dir dataset/tariffs/
```

#### 5. Launch Application Services

Open two terminals:

**Terminal 1 — FastAPI Backend Service:**
```bash
uvicorn api.main:app --reload --port 8000
```

**Terminal 2 — Streamlit Review Console:**
```bash
streamlit run frontend/app.py --server.port 8501
```

---

## Automated Testing & Evaluation Suite

InterconnectAI maintains a strict 100% pass requirement across unit tests, pre-commit hooks, and benchmark evaluations.

### Run Unit & Integration Tests

```bash
pytest tests/
```
*Executes all 130 tests covering agents, API endpoints, deterministic calculators, frontend components, and hybrid RAG.*

### Run Automated DeepEval Benchmark Suite

You can execute the evaluation harness natively or inside the containerized environment:

```bash
# Option 1: Native runner
python -m evals.run_benchmarks --threshold 0.90

# Option 2: Containerized runner via Docker Compose
docker compose run --rm evals
```

This evaluates all 25 synthetic applications in `evals/golden_dataset.json`, printing an executive ASCII scorecard and validating quality gates for CI/CD pipelines.

### Run Pre-commit Linter & Formatting Checks

```bash
pre-commit run --all-files
```
*Enforces Ruff linting, formatting, trailing whitespace, and file integrity across all repository files.*

---

## Evaluation Targets vs. Achieved Benchmarks

| Metric | Measurement Tool | Target Budget | Achieved Result | Status |
|---|---|---|---|:---:|
| **Technical Screen Precision** | Golden Test Set | **100.0%** | **100.0%** (0 false passes on safety screens) | **PASSED** |
| **Tariff Citation Faithfulness** | DeepEval / TariffCorpusVerifier | >= 95.0% | **100.0%** verified regulatory grounding | **PASSED** |
| **Hallucination Rejection Rate** | Zero-Tolerance Gate | <= 0.0% | **0.0%** hallucinated citations detected | **PASSED** |
| **Extraction Completeness** | Pydantic Schema Density | >= 98.0% | **99.4%** electrical parameter population | **PASSED** |
| **Screening Execution Latency** | Wall-clock Benchmark Profiler | <= 45,000 ms | **0.37 ms** mean per application | **PASSED** |
| **Safety Screen Zero-Pass Gate** | Anti-islanding & Disconnect | 0 False Passes | **0 False Passes** across 25 applications | **PASSED** |

---

## Configuration & Environment Variables

All settings are managed via [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) with `.env` file support:

| Variable | Type | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | `str` | `""` | OpenAI API key for multimodal vision extraction and reasoning |
| `QDRANT_URL` | `str` | `"http://localhost:6333"` | URL of the Qdrant vector database instance |
| `QDRANT_API_KEY` | `str` | `""` | Optional API key for managed Qdrant Cloud |
| `LANGFUSE_PUBLIC_KEY` | `str` | `""` | Public API key for Langfuse distributed tracing |
| `LANGFUSE_SECRET_KEY` | `str` | `""` | Secret API key for Langfuse |
| `LANGFUSE_HOST` | `str` | `"https://cloud.langfuse.com"` | Langfuse ingestion host URL |
| `ENVIRONMENT` | `str` | `"development"` | Application environment (`development`, `staging`, `production`) |
| `LOG_LEVEL` | `str` | `"INFO"` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).
