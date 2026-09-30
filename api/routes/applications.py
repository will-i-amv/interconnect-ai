"""FastAPI route handlers for InterconnectAI application catalog, runner, and SSE stream."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from api.schemas import (
    ApplicationDetailResponse,
    ApplicationSummaryResponse,
    ScreeningRunRequest,
    ScreeningRunResponse,
)
from src.agents.graph import create_interconnection_graph
from src.agents.state import WorkflowStep
from src.observability import get_tracer
from src.schemas.application import ApplicationSchema
from src.schemas.screening import OverallOutcome
from src.schemas.tariff import TariffJurisdiction
from src.utils.dataset import (
    load_application,
    load_application_schema,
    load_dataset_catalog,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["screening"])


def _to_json_serializable(obj: Any) -> Any:
    """Recursively convert objects, enums, Pydantic models, and paths to serializable types."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _to_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set):
        return [_to_json_serializable(item) for item in obj]
    return obj


def _resolve_application_package(
    application_id: str,
    explicit_schema: ApplicationSchema | None = None,
    explicit_docs: list[str] | None = None,
    jurisdiction: TariffJurisdiction = TariffJurisdiction.CA_RULE_21,
) -> dict[str, Any]:
    """Prepare initial state container from explicit inputs or benchmark dataset fallback."""
    app_data: ApplicationSchema | None = explicit_schema
    raw_docs: list[str] = list(explicit_docs or [])

    # Check benchmark catalog if schema or docs need dataset resolution
    try:
        catalog = load_dataset_catalog()
        has_benchmark = application_id in catalog.get("applications", {})
    except Exception:
        has_benchmark = False

    if app_data is None and has_benchmark:
        with contextlib.suppress(Exception):
            app_data = load_application_schema(application_id)

    if not raw_docs and has_benchmark:
        try:
            pkg = load_application(application_id)
            doc_keys = (
                "application_form_path",
                "single_line_diagram_path",
                "inverter_cutsheet_path",
            )
            for path_key in doc_keys:
                p = pkg.get(path_key)
                if p and isinstance(p, Path) and p.is_file():
                    raw_docs.append(str(p))
        except Exception as exc:
            logger.warning("Could not resolve document paths for %s: %s", application_id, exc)

    if app_data is None and not has_benchmark:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Application '{application_id}' is not recognized in the benchmark catalog, "
                "and no explicit 'application_data' schema was provided."
            ),
        )

    return {
        "application_id": application_id,
        "application_data": app_data,
        "raw_documents": raw_docs,
        "jurisdiction": jurisdiction,
        "current_step": WorkflowStep.INTAKE,
        "errors": [],
        "audit_log": [],
    }


# -----------------------------------------------------------------------------
# Catalog & Application Metadata Endpoints
# -----------------------------------------------------------------------------


@router.get(
    "/applications",
    response_model=list[ApplicationSummaryResponse],
    summary="List benchmark applications catalog",
)
async def list_applications_catalog() -> list[ApplicationSummaryResponse]:
    """Retrieve all available benchmark interconnection applications with metadata."""
    try:
        catalog = load_dataset_catalog()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load application catalog: {exc}",
        ) from exc

    results: list[ApplicationSummaryResponse] = []
    apps = catalog.get("applications", {})

    for app_id, meta in sorted(apps.items()):
        results.append(
            ApplicationSummaryResponse(
                application_id=app_id,
                applicant_name=meta.get("applicant_name", "Unknown Applicant"),
                project_type=meta.get("project_type", "Solar PV"),
                capacity_kw=float(meta.get("capacity_kw", 0.0)),
                utility=meta.get("utility", "Unknown Utility"),
                feeder_id=meta.get("feeder_id", "FEEDER-01"),
                expected_outcome=meta.get("expected_outcome", "UNKNOWN"),
                failing_screens=meta.get("failing_screens", []),
                required_citations=meta.get("required_citations", []),
            )
        )
    return results


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationDetailResponse,
    summary="Get application details and telemetry",
)
async def get_application_details(application_id: str) -> ApplicationDetailResponse:
    """Retrieve metadata, telemetry parameters, and document paths for an application."""
    try:
        catalog = load_dataset_catalog()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load application catalog: {exc}",
        ) from exc

    apps = catalog.get("applications", {})
    if application_id not in apps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{application_id}' not found in benchmark catalog.",
        )

    meta = apps[application_id]
    summary = ApplicationSummaryResponse(
        application_id=application_id,
        applicant_name=meta.get("applicant_name", "Unknown Applicant"),
        project_type=meta.get("project_type", "Solar PV"),
        capacity_kw=float(meta.get("capacity_kw", 0.0)),
        utility=meta.get("utility", "Unknown Utility"),
        feeder_id=meta.get("feeder_id", "FEEDER-01"),
        expected_outcome=meta.get("expected_outcome", "UNKNOWN"),
        failing_screens=meta.get("failing_screens", []),
        required_citations=meta.get("required_citations", []),
    )

    try:
        pkg = load_application(application_id)
        telemetry = pkg.get("telemetry", {})
        files = {
            "application_form": str(pkg.get("application_form_path", "")),
            "single_line_diagram": str(pkg.get("single_line_diagram_path", "")),
            "inverter_cutsheet": str(pkg.get("inverter_cutsheet_path", "")),
        }
    except Exception:
        telemetry = {}
        files = {}

    structured_schema: ApplicationSchema | None = None
    with contextlib.suppress(Exception):
        structured_schema = load_application_schema(application_id)

    return ApplicationDetailResponse(
        application_id=application_id,
        summary=summary,
        telemetry=telemetry,
        files=files,
        structured_schema=structured_schema,
    )


# -----------------------------------------------------------------------------
# Screening Runner Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/screen/run",
    response_model=ScreeningRunResponse,
    summary="Execute full technical screening workflow",
)
async def run_screening(request: ScreeningRunRequest) -> ScreeningRunResponse:
    """Run the complete LangGraph technical screening state machine asynchronously."""
    initial_state = _resolve_application_package(
        application_id=request.application_id,
        explicit_schema=request.application_data,
        explicit_docs=request.raw_documents,
        jurisdiction=request.jurisdiction,
    )

    tracer = get_tracer()
    thread_id = f"api-run-{request.application_id}-{uuid.uuid4().hex[:8]}"
    start_time = time.perf_counter()

    # Compile and execute state machine in a worker thread to keep the event loop responsive
    def _execute() -> dict[str, Any]:
        with tracer.trace(
            name="screening_workflow",
            application_id=request.application_id,
            jurisdiction=request.jurisdiction.value if request.jurisdiction else None,
            tags={"thread_id": thread_id, "mode": "run"},
        ):
            graph = create_interconnection_graph()
            cb = tracer.get_langchain_callback(
                application_id=request.application_id,
                jurisdiction=str(request.jurisdiction),
            )
            return graph.invoke(
                initial_state,
                config={
                    "configurable": {"thread_id": thread_id},
                    "callbacks": [cb],
                },
            )

    result_state = await asyncio.to_thread(_execute)
    execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

    return ScreeningRunResponse(
        application_id=result_state.get("application_id", request.application_id),
        overall_outcome=result_state.get("overall_outcome", OverallOutcome.DEFICIENCY_ISSUED),
        screen_results=result_state.get("screen_results", []),
        deficiencies=result_state.get("deficiencies", []),
        formal_letter_markdown=result_state.get("formal_letter_markdown"),
        audit_log=result_state.get("audit_log", []),
        execution_time_ms=execution_time_ms,
        requires_human_override=result_state.get("requires_human_override", False),
    )


# -----------------------------------------------------------------------------
# Server-Sent Events (SSE) Streaming Endpoints
# -----------------------------------------------------------------------------


async def _sse_event_generator(initial_state: dict[str, Any]):
    """Yield Server-Sent Events for each node update during LangGraph execution."""
    app_id = initial_state.get("application_id", "UNKNOWN")
    thread_id = f"api-stream-{app_id}-{uuid.uuid4().hex[:8]}"

    # Event queue for thread-safe cross-thread event pushing
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _sync_worker():
        tracer = get_tracer()
        try:
            with tracer.trace(
                name="screening_stream_workflow",
                application_id=app_id,
                jurisdiction=str(initial_state.get("jurisdiction", "")),
                tags={"thread_id": thread_id, "mode": "stream"},
            ):
                graph = create_interconnection_graph()
                cb = tracer.get_langchain_callback(
                    application_id=app_id,
                    jurisdiction=str(initial_state.get("jurisdiction", "")),
                )
                for update in graph.stream(
                    initial_state,
                    config={
                        "configurable": {"thread_id": thread_id},
                        "callbacks": [cb],
                    },
                    stream_mode="updates",
                ):
                    if not isinstance(update, dict):
                        continue
                    for node_name, node_output in update.items():
                        step_val = (
                            node_output.get("current_step").value
                            if hasattr(node_output.get("current_step"), "value")
                            else str(node_output.get("current_step", node_name.upper()))
                        )
                        payload = {
                            "node": node_name,
                            "step": step_val,
                            "message": f"Completed node '{node_name}'",
                            "errors": node_output.get("errors", []),
                            "overall_outcome": (
                                node_output.get("overall_outcome").value
                                if hasattr(node_output.get("overall_outcome"), "value")
                                else None
                            ),
                            "screens_evaluated": (
                                len(node_output.get("screen_results", []))
                                if "screen_results" in node_output
                                else None
                            ),
                            "deficiencies_found": (
                                len(node_output.get("deficiencies", []))
                                if "deficiencies" in node_output
                                else None
                            ),
                            "has_letter": bool(node_output.get("formal_letter_markdown")),
                            "timestamp_utc": datetime.now(UTC).isoformat(),
                        }
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            ("node_complete", payload),
                        )
            loop.call_soon_threadsafe(
                queue.put_nowait,
                (
                    "done",
                    {
                        "status": "completed",
                        "application_id": app_id,
                        "timestamp_utc": datetime.now(UTC).isoformat(),
                    },
                ),
            )
        except Exception as exc:
            logger.exception("Error during graph stream execution: %s", exc)
            loop.call_soon_threadsafe(
                queue.put_nowait,
                (
                    "error",
                    {
                        "status": "error",
                        "error": str(exc),
                        "timestamp_utc": datetime.now(UTC).isoformat(),
                    },
                ),
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    # Launch graph worker in background thread
    worker_thread = threading.Thread(target=_sync_worker, daemon=True)
    worker_thread.start()

    # Yield initial start notification
    start_payload = {
        "status": "started",
        "application_id": app_id,
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }
    yield f"event: start\ndata: {json.dumps(start_payload)}\n\n"

    while True:
        item = await queue.get()
        if item is None:
            break
        event_name, data_dict = item
        serialized_data = json.dumps(_to_json_serializable(data_dict))
        yield f"event: {event_name}\ndata: {serialized_data}\n\n"


@router.post(
    "/screen/stream",
    summary="Stream real-time screening state transitions via Server-Sent Events (POST)",
)
async def stream_screening_post(request: ScreeningRunRequest) -> StreamingResponse:
    """Stream real-time LangGraph node execution events over SSE."""
    initial_state = _resolve_application_package(
        application_id=request.application_id,
        explicit_schema=request.application_data,
        explicit_docs=request.raw_documents,
        jurisdiction=request.jurisdiction,
    )
    return StreamingResponse(
        _sse_event_generator(initial_state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/screen/stream/{application_id}",
    summary="Stream real-time screening state transitions via Server-Sent Events (GET)",
)
async def stream_screening_get(
    application_id: str,
    jurisdiction: TariffJurisdiction = TariffJurisdiction.CA_RULE_21,
) -> StreamingResponse:
    """Stream real-time LangGraph node execution events over SSE for a catalog application ID."""
    initial_state = _resolve_application_package(
        application_id=application_id,
        jurisdiction=jurisdiction,
    )
    return StreamingResponse(
        _sse_event_generator(initial_state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# -----------------------------------------------------------------------------
# Telemetry & Observability Endpoints
# -----------------------------------------------------------------------------


@router.get(
    "/telemetry/traces",
    summary="Get recent execution traces",
)
async def get_traces(application_id: str | None = None) -> list[dict[str, Any]]:
    """Retrieve telemetry traces and latencies, optionally filtered by application ID."""
    tracer = get_tracer()
    traces = tracer.get_traces(application_id=application_id)
    return [_to_json_serializable(t) for t in traces]


@router.get(
    "/telemetry/summary/{trace_id}",
    summary="Get telemetry execution summary for a specific trace",
)
async def get_trace_summary(trace_id: str) -> dict[str, Any]:
    """Retrieve summarized latency breakdowns and node timings for a trace."""
    tracer = get_tracer()
    summary = tracer.export_summary(trace_id)
    if "error" in summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=summary["error"],
        )
    return summary
