# InterconnectAI

**Autonomous Grid Interconnection Reviewer & Technical Screening Copilot**

Automating the intake, engineering document validation, and regulatory technical screening for utility distributed energy resources (solar, wind, battery storage) and EV load interconnection queues.

---

## Executive Summary & Industry Context

Across United States regional transmission operators (RTOs) and electric utilities (CAISO, PJM, ERCOT, NYISO), the queue for interconnecting new generation and storage exceeds **2,600 GW**—more than double the existing US generating fleet. Under modern regulatory mandates such as **FERC Order 2023** and state-level interconnection frameworks (e.g., **California Rule 21**, **IEEE 1547-2018**), utilities are legally required to evaluate projects under tight statutory deadlines.

However, each application requires hours of senior distribution engineer time:
1. Manually validating multi-page engineering exhibits, inverter specification cut-sheets, and Single-Line Diagrams (SLDs).
2. Verifying deterministic technical criteria (15% peak load feeder penetration, short-circuit ratio thresholds, anti-islanding certification).
3. Cross-referencing utility-specific tariff rulebooks and formulating legally binding **Deficiency Notices** or **Approval Memorandums**.

**InterconnectAI** is a production-grade, multi-agent AI system designed to automate this lifecycle. It combines **layout-aware multimodal parsing**, **hybrid RAG over utility tariffs**, **stateful agentic screening (LangGraph)**, and an **interactive engineer-in-the-loop dashboard**.

---

## System Architecture

```
                                  +--------------------------------------------------+
                                  |            Next.js / TypeScript Frontend         |
                                  |    (Split-screen PDF Viewer + Review Console)    |
                                  +------------------------+-------------------------+
                                                           | (SSE / REST API)
                                  +------------------------v-------------------------+
                                  |                 FastAPI Backend                  |
                                  |          (Async Job Runner + Pydantic)           |
                                  +----+--------------------+-------------------+----+
                                       |                    |                   |
               +-----------------------v----+     +---------v---------+    +----v--------------------+
               |   Multimodal Parser & OCR  |     |   Hybrid RAG      |    |   LangGraph Agent       |
               | (Docling / PyMuPDF / Vision|     |  (Qdrant/pgvector |    | (State Machine Workflow |
               |  for Single-Line Diagrams) |     |  BM25 + BGE Rerank|    |  Deterministic Screens) |
               +----------------------------+     +-------------------+    +-------------------------+
                                                                                        |
                                                                           +------------v------------+
                                                                           |  Observability & Evals  |
                                                                           |  (Langfuse + DeepEval)  |
                                                                           +-------------------------+
```

### Core Architecture Constraints & Contracts

1. **Decoupled Backend & Frontend**: The backend is an asynchronous FastAPI service exposing streaming endpoints (Server-Sent Events) for real-time agent reasoning steps. The frontend is a Next.js 14 / TypeScript application with zero heavy Python dependencies.
2. **Deterministic Screen Integrity (Zero Math Hallucinations)**: The LLM is strictly forbidden from doing distribution math (e.g., feeder penetration percentages, transformer thermal capacity limits). All calculations are executed by isolated, unit-tested deterministic Python calculation tools; the LLM merely structures inputs and formats outputs.
3. **Strict Citation Attribution**: Every deficiency or approval citation must map directly to an exact section in the ingested utility tariff handbook (e.g., `Rule 21 Section F.3.a`) with bounding-box or page-level grounding.
4. **Human-in-the-Loop Gateway**: The agent can prepare deficiency letters or recommend fast-track approvals, but cannot submit them to the applicant without explicit engineer authorization in the UI.

---

## Input Contracts & Data Sources

| Artifact | Source / Format | Purpose | Validation / Leakage Controls |
|---|---|---|---|
| **Interconnection Application** | Form PDF (Standardized Form) | Applicant profile, project capacity (kW/MW), point of common coupling (PCC) | Validated against strict `ApplicantSchema` Pydantic model |
| **Equipment Cut-Sheets** | Manufacturer Datasheets (PDF) | Inverter specs, UL 1741-SB / IEEE 1547 compliance, power factor range | Inverter model verified against California Energy Commission (CEC) listing |
| **Single-Line Diagram (SLD)** | Vector / Raster PDF / Image | Electrical schematics, disconnect switches, meter placements, breaker ratings | Extracted via Vision-LLM + OCR; requires engineer visual confirmation |
| **Substation Feeder Telemetry** | Time-series / Tabular CSV / JSON | Peak load, minimum daytime load (MDL), existing connected generation | Read-only input; feeds deterministic screening calculators |
| **Tariff & Standard Documents** | Utility Rulebook (PDF) | California Rule 21, FERC Order 2023, IEEE 1547 standard clauses | Pre-chunked and indexed in Vector DB; frozen during runtime |

---

## Ticket Directory & Implementation Plan

Execution is structured into 7 sequential phases. The core AI engineering scope encompasses **Phases 1 through 5**. **Phases 6 and 7** are optional production and modeling extensions.

```
Phase 1: Foundation & Schemas (T-101 - T-103)
Phase 2: Hybrid RAG & Knowledge Retrieval (T-104 - T-106)
Phase 3: Agentic Screening State Machine (T-107 - T-110)
Phase 4: Full-Stack Serving & Streaming UI (T-111 - T-114)
Phase 5: Automated Evals & Observability (T-115 - T-117)
Phase 6: [OPTIONAL ADD-ON] Compound AI / Tabular ML Modeling (T-118 - T-120)
Phase 7: [OPTIONAL ADD-ON] Production Hardening & Live Ingestion (T-121 - T-123)
```

### Phase 1 — Foundation & Schemas

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-101` | `SETUP` | Repository initialization, Docker Compose environment, linting/formatting config | `docker-compose.yml`, `pyproject.toml`, ruff/black, pre-commit hooks |
| `T-102` | `DATA` | Curate synthetic & public benchmark dataset (CA Rule 21 PDF, IEEE 1547, sample SLDs, cut-sheets) | `dataset/tariffs/`, `dataset/applications/`, metadata schemas |
| `T-103` | `SCHEMA` | Define Pydantic models for technical schemas (Inverter, Transformer, Line, Screen Results) | `src/schemas/application.py`, `src/schemas/screening.py` |

### Phase 2 — Knowledge Retrieval & Hybrid RAG

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-104` | `RAG` | Ingestion pipeline with layout-aware PDF chunking (Docling/PyMuPDF) | `src/rag/ingest.py`, hierarchical section-preserving chunker |
| `T-105` | `RAG` | Vector database setup (Qdrant or pgvector) + BM25 keyword index | Hybrid retriever combining dense embeddings + BM25 with RRF |
| `T-106` | `RAG` | Cross-encoder reranking pipeline (BGE-Reranker or Cohere API) | `src/rag/reranker.py`, citation tracking with exact page numbers |

### Phase 3 — Agentic State Machine & Deterministic Screening

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-107` | `AGENT` | LangGraph state machine definition: application state, history, error rollback | `src/agents/state.py`, `src/agents/graph.py` |
| `T-108` | `TOOLS` | Deterministic screening tools: 15% penetration screen, anti-islanding check, short-circuit ratio | `src/tools/grid_screens.py`, comprehensive unit test suite |
| `T-109` | `VISION` | Multimodal extractor for Single-Line Diagrams & Equipment Cut-Sheets | `src/agents/vision_extractor.py`, extracts inverter model & switch config |
| `T-110` | `AGENT` | Deficiency & Approval synthesis node: generates structured formal letters with citations | `src/agents/letter_generator.py`, Markdown/PDF exportable memo |

### Phase 4 — Full-Stack Serving & UI

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-111` | `API` | FastAPI async backend with Celery/Redis queue for async document extraction | `api/routes/applications.py`, `/api/screen/stream` SSE endpoint |
| `T-112` | `FRONTEND` | Next.js 14 dashboard: Queue list, application status, pass/fail badges | `frontend/app/dashboard/`, Tailwind/shadcn components |
| `T-113` | `FRONTEND` | Split-screen Review Console: PDF Viewer on left, live Agent reasoning log on right | `frontend/components/pdf-viewer.tsx`, `frontend/components/agent-stream.tsx` |
| `T-114` | `HUMAN` | Human-in-the-loop override interface: edit extracted parameters, sign-off on approvals | `frontend/components/override-modal.tsx`, audit log tracker |

### Phase 5 — Automated Evals & Observability

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-115` | `OBSERVE` | Integrate Langfuse/Phoenix tracing across all LLM calls, tools, and token latencies | `src/observability/tracer.py`, trace tags by application ID |
| `T-116` | `EVALS` | Build golden test set of 25 synthetic applications (15 clean passes, 10 known deficiencies) | `evals/golden_dataset.json`, ground truth labels |
| `T-117` | `EVALS` | Automated evaluation harness using DeepEval: Tariff citation faithfulness & screen accuracy | `evals/run_benchmarks.py`, CI/CD failure thresholds on hallucination |

---

### Phase 6 — [OPTIONAL ADD-ON] Compound AI / Classical ML Modeling
> [!NOTE]
> **This phase is strictly optional.** It will only be executed once Phases 1–5 are complete and verified. It extends the core AI system into a Compound AI architecture using tabular ML techniques.

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-118` | `ML-DATA` | Ingest historical interconnection queue dataset (e.g., LBNL Queued Up dataset) and engineer features | `notebooks/01_queue_eda.ipynb`, `src/ml/feature_pipeline.py` |
| `T-119` | `ML-MODEL` | Train & tune LightGBM/XGBoost regressor to predict **Study Completion Delay (days)** & **Upgrade Cost ($)** | `src/ml/train.py`, `models/queue_delay_model.joblib`, model comparison report |
| `T-120` | `COMPOUND`| Expose trained ML model as an internal LangGraph tool (`predict_queue_delay_risk`) | Tool integration in `src/tools/ml_forecaster.py`, UI risk score badge |

---

### Phase 7 — [OPTIONAL ADD-ON] Production Hardening & Live Utility Ingestion
> [!NOTE]
> **This phase is strictly optional.** It builds upon the complete system to introduce enterprise production capabilities: live regulatory scraping, cloud object storage, and multi-utility jurisdiction management.

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-121` | `INGEST-PROD` | Hybrid Regulatory Ingestion: Remote fetcher with hash-based caching, version tracking, and offline fallback | `src/rag/remote_fetcher.py`, CLI `--fetch-remote`, `dataset/tariffs/cache/` |
| `T-122` | `STORAGE` | Cloud Object Storage Integration (S3 / MinIO) for multi-tenant PDF and SLD artifact archival | `src/storage/s3_client.py`, docker-compose MinIO service |
| `T-123` | `MULTI-JURIS` | Multi-jurisdiction tariff router: Dynamic switching between CA Rule 21, NY Standard Interconnection Requirements (SIR), and PJM Manual 14 | `src/rag/router.py`, jurisdiction config schema |

---

## Quickstart & Local Setup

### 1. Environment Configuration

```bash
# Clone and enter repo
git clone https://github.com/will-i-amv/interconnect-ai.git
cd interconnect-ai

# Python virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

# Copy environment template
cp .env.example .env
```

### 2. Launch Local Infrastructure (Vector DB & Redis)

```bash
docker compose up -d qdrant redis
```

### 3. Run Ingestion & Tariff Indexing

```bash
python -m src.rag.ingest --tariff-dir dataset/tariffs/
```

### 4. Start the Application

```bash
# Terminal 1: Backend API
uvicorn api.main:app --reload --port 8000

# Terminal 2: Celery Worker
celery -A api.worker worker --loglevel=info

# Terminal 3: Frontend Dashboard
cd frontend && npm run dev
```

### 5. Run Evaluations & Benchmark Suite

```bash
pytest evals/
python -m evals.run_benchmarks --threshold 0.90
```

---

## Evaluation Framework & Target Metrics

| Metric | Measurement Tool | Target Budget | Description |
|---|---|---|---|
| **Citation Faithfulness** | DeepEval / G-Eval | >= 95% | Percentage of generated deficiency citations that exactly match source tariff text |
| **Technical Screen Precision** | Golden Test Set | **100%** | Zero false passes on deterministic safety screens (15% penetration, anti-islanding) |
| **Extraction Completeness** | Pydantic validation | >= 98% | Percentage of required electrical parameters successfully parsed from cut-sheets |
| **End-to-End Processing Time** | Langfuse Tracing | <= 45 s | Total wall-clock time to ingest, parse, screen, and draft memo for a 10-page application |
| **Token Cost per Review** | Langfuse Telemetry | <= $0.35 | Average cost per full application review using hybrid LLM routing |

---

## Known Limitations & Production Caveats

1. **Non-Standard Single-Line Diagrams**: Scanned, low-resolution raster blueprints with irregular hand annotations require human intervention. The system flags low-confidence OCR nodes for manual bounding-box verification.
2. **Synthetic Tariff Boundaries**: Default benchmarks use California Rule 21 and IEEE 1547. Adding another utility jurisdiction requires running `python -m src.rag.ingest` on the new jurisdiction tariff PDF.
3. **Deterministic Math Supremacy**: The LLM is never relied upon for distribution calculations; any deviation in feeder capacity numbers is rejected at the Pydantic schema validation layer before reaching the UI.
