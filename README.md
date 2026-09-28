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
5. **Device-Agnostic Execution**: All local embedding, reranking, and multimodal inference pipelines must be hardware-agnostic from Day 1, automatically detecting and utilizing NVIDIA CUDA or Apple MPS acceleration if available, while gracefully falling back to CPU execution without manual code changes.

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

## Ticket Directory & Implementation Roadmap

The engineering roadmap is structured into 7 sequential phases. The core AI engineering scope encompasses **Phases 1 through 5**, with **Phases 6 and 7** serving as optional production hardening and tabular ML extensions:

- **Phase 1: Foundation & Schemas** (`T-101` – `T-103`): Environment setup, benchmark application dataset, and Pydantic engineering schemas.
- **Phase 2: Hybrid RAG & Knowledge Retrieval** (`T-104` – `T-106`): Layout-aware PDF chunker, Qdrant vector database, BM25 keyword index with RRF, and cross-encoder reranker.
- **Phase 3: Agentic Screening State Machine** (`T-107` – `T-110`): LangGraph state machine, deterministic screening tools (Rule 21 & IEEE 1547), multimodal vision extractor for SLDs and cut-sheets, and formal decision letter generator.
- **Phase 4: Full-Stack Serving & Streaming UI** (`T-111` – `T-114`): FastAPI async backend, Celery/Redis queue, Next.js review console, and human-in-the-loop override modal.
- **Phase 5: Automated Evals & Observability** (`T-115` – `T-117`): Langfuse/Phoenix tracing, golden dataset benchmarks, and DeepEval regulatory citation faithfulness tests.
- **Phase 6: [OPTIONAL] Production Hardening & Advanced AI** (`T-118` – `T-123`): Hybrid regulatory ingestion, S3/MinIO cloud object storage, multi-jurisdiction router, local LLM serving, and VLM fine-tuning.
- **Phase 7: [OPTIONAL] Compound AI / Tabular ML Modeling** (`T-124` – `T-126`): Queue delay and upgrade cost estimation via LightGBM/XGBoost tabular models.

> [!TIP]
> For the complete breakdown of all 26 tickets, category classifications, descriptions, and technical deliverables, consult the **[Ticket Directory & Implementation Plan](docs/ticket_descriptions.md)**.

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
