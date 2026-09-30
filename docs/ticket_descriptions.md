# Ticket Directory & Implementation Plan

This document outlines the complete engineering roadmap and ticket specifications for **InterconnectAI**.

Execution is structured into 7 sequential phases. The core AI engineering scope encompasses **Phases 1 through 5**. **Phases 6 and 7** are optional production and modeling extensions.

```
Phase 1: Foundation & Schemas (T-101 - T-103)
Phase 2: Hybrid RAG & Knowledge Retrieval (T-104 - T-106)
Phase 3: Agentic Screening State Machine (T-107 - T-110)
Phase 4: Full-Stack Serving & Streamlit UI (T-111 - T-114)
Phase 5: Automated Evals & Observability (T-115 - T-117)
Phase 6: [OPTIONAL ADD-ON] Production Hardening & Live Utility Ingestion (T-118 - T-124)
Phase 7: [OPTIONAL ADD-ON] Compound AI / Tabular ML Modeling (T-125 - T-127)
```

---

### Phase 1 — Foundation & Schemas

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-101` | `SETUP` | Repository initialization, Docker Compose environment, linting/formatting config | `docker-compose.yml`, `pyproject.toml`, ruff/black, pre-commit hooks |
| `T-102` | `DATA` | Curate synthetic & public benchmark dataset (CA Rule 21 PDF, IEEE 1547, sample SLDs, cut-sheets) | `dataset/tariffs/`, `dataset/applications/`, metadata schemas |
| `T-103` | `SCHEMA` | Define Pydantic models for technical schemas (Inverter, Transformer, Line, Screen Results) | `src/schemas/application.py`, `src/schemas/screening.py` |

---

### Phase 2 — Knowledge Retrieval & Hybrid RAG

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-104` | `RAG` | Ingestion pipeline with layout-aware PDF chunking (Docling/PyMuPDF) | `src/rag/ingest.py`, hierarchical section-preserving chunker |
| `T-105` | `RAG` | Vector database setup (Qdrant or pgvector) + BM25 keyword index | Hybrid retriever combining dense embeddings + BM25 with RRF |
| `T-106` | `RAG` | Cross-encoder reranking pipeline (BGE-Reranker or Cohere API) with device-agnostic PyTorch/ONNX runtime (CUDA/MPS/CPU fallback) | `src/rag/reranker.py`, citation tracking with exact page numbers |

---

### Phase 3 — Agentic State Machine & Deterministic Screening

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-107` | `AGENT` | LangGraph state machine definition: application state, history, error rollback | `src/agents/state.py`, `src/agents/graph.py` |
| `T-108` | `TOOLS` | Deterministic screening tools: 15% penetration screen, anti-islanding check, short-circuit ratio | `src/tools/grid_screens.py`, comprehensive unit test suite |
| `T-109` | `VISION` | Multimodal extractor for Single-Line Diagrams & Equipment Cut-Sheets with device-agnostic local vision inference support | `src/agents/vision_extractor.py`, extracts inverter model & switch config |
| `T-110` | `AGENT` | Deficiency & Approval synthesis node: generates structured formal letters with citations | `src/agents/letter_generator.py`, Markdown/PDF exportable memo |

---

### Phase 4 — Full-Stack Serving & Streamlit UI

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-111` | `API` | FastAPI async backend with runner endpoint for application screening execution | `api/routes/applications.py`, `/api/screen/run` and `/api/screen/stream` endpoints |
| `T-112` | `STREAMLIT` | Streamlit interactive dashboard: Application catalog browser, queue status metrics, filterable review table with pass/fail badges | `frontend/app.py`, `frontend/views/dashboard.py` |
| `T-113` | `STREAMLIT` | Split-screen Review Console: Embedded multi-page PDF viewer on left, live LangGraph reasoning log & screen evaluation matrix on right | `frontend/views/review_console.py`, `frontend/components/pdf_viewer.py` |
| `T-114` | `HUMAN` | Human-in-the-loop override interface (`st.dialog` modal): edit extracted parameters, sign-off on approvals with audit trail | `frontend/components/override_dialog.py`, audit log tracker |


---

### Phase 5 — Automated Evals & Observability

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-115` | `OBSERVE` | Integrate Langfuse/Phoenix tracing across all LLM calls, tools, and token latencies | `src/observability/tracer.py`, trace tags by application ID |
| `T-116` | `EVALS` | Build golden test set of 25 synthetic applications (15 clean passes, 10 known deficiencies) | `evals/golden_dataset.json`, ground truth labels |
| `T-117` | `EVALS` | Automated evaluation harness using DeepEval: Tariff citation faithfulness & screen accuracy | `evals/run_benchmarks.py`, CI/CD failure thresholds on hallucination |

---

### Phase 6 — [OPTIONAL ADD-ON] Production Hardening & Live Utility Ingestion

> [!NOTE]
> **This phase is strictly optional.** It builds upon the complete system to introduce enterprise production capabilities: live regulatory scraping, cloud object storage, and multi-utility jurisdiction management.

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-118` | `INGEST-PROD` | Hybrid Regulatory Ingestion: Remote fetcher with hash-based caching, version tracking, and offline fallback | `src/rag/remote_fetcher.py`, CLI `--fetch-remote`, `dataset/tariffs/cache/` |
| `T-119` | `STORAGE` | Cloud Object Storage Integration (S3 / MinIO) for multi-tenant PDF and SLD artifact archival | `src/storage/s3_client.py`, docker-compose MinIO service |
| `T-120` | `MULTI-JURIS` | Multi-jurisdiction tariff router: Dynamic switching between CA Rule 21, NY Standard Interconnection Requirements (SIR), and PJM Manual 14 | `src/rag/router.py`, jurisdiction config schema |
| `T-121` | `LOCAL-LLM` | Self-Hosted Open-Source LLM Serving: Air-gapped vLLM / Ollama engine running open-weight models (Llama 3.3 / Qwen 2.5) for NERC-CIP utility data sovereignty | `docker-compose.local-llm.yml`, local model provider switch in `src/agents/` |
| `T-122` | `GPU-OPT` | Hardware-Accelerated Inference & Reranking: CUDA/TensorRT and ONNX Runtime optimization for BGE-Reranker and local embeddings | `src/rag/accelerators.py`, GPU latency benchmark report |
| `T-123` | `FINE-TUNE` | Vision-Language Model (VLM) Fine-Tuning: LoRA/QLoRA fine-tuning of open VLM (Qwen2.5-VL) on electrical Single-Line Diagrams for structured Pydantic extraction | `notebooks/02_vlm_lora_finetune.ipynb`, LoRA adapters in `models/sld_lora/` |
| `T-124` | `POSTGRES` | Production PostgreSQL Application State & LangGraph Checkpointing: Multi-worker async state persistence using `langgraph-checkpoint-postgres` (`AsyncPostgresSaver`), connection pooling, and historical application queue storage | `src/storage/db.py`, `docker-compose.yml` (Postgres service), LangGraph checkpointer integration, unit tests in `tests/test_storage_db.py` |

---

### Phase 7 — [OPTIONAL ADD-ON] Compound AI / Classical ML Modeling

> [!NOTE]
> **This phase is strictly optional.** It will only be executed once Phases 1–6 are complete and verified. It extends the core AI system into a Compound AI architecture using tabular ML techniques.

| Ticket | Category | Description | Deliverables |
|---|---|---|---|
| `T-125` | `ML-DATA` | Ingest historical interconnection queue dataset (e.g., LBNL Queued Up dataset) and engineer features | `notebooks/01_queue_eda.ipynb`, `src/ml/feature_pipeline.py` |
| `T-126` | `ML-MODEL` | Train & tune LightGBM/XGBoost regressor to predict **Study Completion Delay (days)** & **Upgrade Cost ($)** | `src/ml/train.py`, `models/queue_delay_model.joblib`, model comparison report |
| `T-127` | `COMPOUND`| Expose trained ML model as an internal LangGraph tool (`predict_queue_delay_risk`) | Tool integration in `src/tools/ml_forecaster.py`, UI risk score badge |
