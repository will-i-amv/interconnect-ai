"""Observability, telemetry, and distributed tracing for InterconnectAI.

Provides production-ready tracing across LangGraph workflow nodes, engineering tools,
deterministic grid screens, and multimodal extraction latencies with native
Langfuse, OpenTelemetry/Phoenix, and resilient in-memory structured fallbacks.
"""

from __future__ import annotations

import contextlib
import contextvars
import functools
import logging
import os
import time
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Data Models & Schemas
# -----------------------------------------------------------------------------


class SpanType(StrEnum):
    """Categorical classification of traced execution units."""

    WORKFLOW = "workflow"
    NODE = "node"
    TOOL = "tool"
    LLM = "llm"
    VISION = "vision"
    RETRIEVAL = "retrieval"
    SCREEN = "screen"
    SYNTHESIS = "synthesis"


class SpanStatus(StrEnum):
    """Execution status for a trace or span."""

    OK = "ok"
    ERROR = "error"


class MetricRecord(BaseModel):
    """Telemetry metric measurement (e.g. latency, token count, penetration pct)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., description="Metric identifier")
    value: float = Field(..., description="Numeric value")
    unit: str = Field(default="", description="Unit of measurement (ms, tokens, pct, etc.)")
    timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when metric was recorded",
    )
    tags: dict[str, str] = Field(default_factory=dict, description="Metadata tags")
    application_id: str | None = Field(default=None, description="Associated application ID")


class SpanRecord(BaseModel):
    """Detailed record of a single execution span within a trace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    span_id: str = Field(..., description="Unique span UUID")
    trace_id: str = Field(..., description="Parent trace UUID")
    parent_span_id: str | None = Field(default=None, description="Enclosing span UUID if nested")
    name: str = Field(..., description="Logical name of the operation")
    span_type: SpanType = Field(default=SpanType.NODE, description="Type of operation")
    application_id: str | None = Field(default=None, description="Associated application ID")
    jurisdiction: str | None = Field(default=None, description="Tariff jurisdiction")
    status: SpanStatus = Field(default=SpanStatus.OK, description="Outcome status")
    start_time_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC start time",
    )
    end_time_utc: datetime | None = Field(default=None, description="UTC end time")
    duration_ms: float | None = Field(
        default=None, description="Execution duration in milliseconds"
    )
    input_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized input data",
    )
    output_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized output summary",
    )
    error_message: str | None = Field(default=None, description="Error message if failed")
    tags: dict[str, str] = Field(default_factory=dict, description="Key-value tags")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra metadata")


class TraceRecord(BaseModel):
    """Complete root trace representing an end-to-end request or workflow run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str = Field(..., description="Unique trace UUID")
    name: str = Field(..., description="Root trace name")
    application_id: str | None = Field(default=None, description="Associated application ID")
    jurisdiction: str | None = Field(default=None, description="Tariff jurisdiction")
    status: SpanStatus = Field(default=SpanStatus.OK, description="Overall trace status")
    start_time_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC start time",
    )
    end_time_utc: datetime | None = Field(default=None, description="UTC completion time")
    total_duration_ms: float | None = Field(
        default=None,
        description="Total duration in milliseconds",
    )
    spans: list[SpanRecord] = Field(default_factory=list, description="Child spans")
    metrics: list[MetricRecord] = Field(default_factory=list, description="Recorded metrics")
    tags: dict[str, str] = Field(default_factory=dict, description="Root tags")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata")


# -----------------------------------------------------------------------------
# Context Variables for Thread/Async Safety
# -----------------------------------------------------------------------------

_CURRENT_TRACE: contextvars.ContextVar[TraceRecord | None] = contextvars.ContextVar(
    "current_trace", default=None
)
_CURRENT_SPAN: contextvars.ContextVar[SpanRecord | None] = contextvars.ContextVar(
    "current_span", default=None
)


def _sanitize_for_telemetry(data: Any, max_len: int = 1000) -> Any:
    """Safely convert payloads into JSON-serializable summaries for telemetry."""
    if data is None:
        return None
    if isinstance(data, str):
        if len(data) > max_len:
            return data[:max_len] + f"... [truncated {len(data) - max_len} chars]"
        return data
    if isinstance(data, int | float | bool):
        return data
    if isinstance(data, Enum):
        return data.value
    if isinstance(data, datetime):
        return data.isoformat()
    if hasattr(data, "model_dump"):
        return _sanitize_for_telemetry(data.model_dump(mode="json"), max_len=max_len)
    if isinstance(data, dict):
        return {
            str(key): _sanitize_for_telemetry(val, max_len=max_len)
            for key, val in list(data.items())[:50]
        }
    if isinstance(data, list | tuple | set):
        return [_sanitize_for_telemetry(item, max_len=max_len) for item in list(data)[:50]]
    return str(data)


# -----------------------------------------------------------------------------
# LangChain / LangGraph Callback Handler
# -----------------------------------------------------------------------------


class InterconnectTracingCallback(BaseCallbackHandler):
    """LangChain callback handler recording spans into InterconnectTracer."""

    def __init__(
        self,
        tracer: InterconnectTracer,
        application_id: str | None = None,
        jurisdiction: str | None = None,
    ) -> None:
        super().__init__()
        self.tracer = tracer
        self.application_id = application_id
        self.jurisdiction = jurisdiction
        self._active_spans: dict[str, str] = {}  # run_id -> span_id

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        chain_name = (serialized or {}).get("name") or "LangGraphChain"
        span_id = self.tracer.start_span(
            name=f"chain:{chain_name}",
            span_type=SpanType.NODE,
            application_id=self.application_id,
            jurisdiction=self.jurisdiction,
            input_payload=_sanitize_for_telemetry(inputs),
            tags={"run_id": str(run_id), **{tag: "true" for tag in (tags or [])}},
            metadata=metadata or {},
        )
        self._active_spans[str(run_id)] = span_id

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        **kwargs: Any,
    ) -> None:
        span_id = self._active_spans.pop(str(run_id), None)
        if span_id:
            self.tracer.end_span(
                span_id=span_id,
                status=SpanStatus.OK,
                output_payload=_sanitize_for_telemetry(outputs),
            )

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        **kwargs: Any,
    ) -> None:
        span_id = self._active_spans.pop(str(run_id), None)
        if span_id:
            self.tracer.end_span(
                span_id=span_id,
                status=SpanStatus.ERROR,
                error_message=str(error),
            )

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = (serialized or {}).get("name") or "Tool"
        span_id = self.tracer.start_span(
            name=f"tool:{tool_name}",
            span_type=SpanType.TOOL,
            application_id=self.application_id,
            jurisdiction=self.jurisdiction,
            input_payload={"input": input_str},
            tags={"run_id": str(run_id)},
            metadata=metadata or {},
        )
        self._active_spans[str(run_id)] = span_id

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        **kwargs: Any,
    ) -> None:
        span_id = self._active_spans.pop(str(run_id), None)
        if span_id:
            self.tracer.end_span(
                span_id=span_id,
                status=SpanStatus.OK,
                output_payload={"output": _sanitize_for_telemetry(output)},
            )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        **kwargs: Any,
    ) -> None:
        span_id = self._active_spans.pop(str(run_id), None)
        if span_id:
            self.tracer.end_span(
                span_id=span_id,
                status=SpanStatus.ERROR,
                error_message=str(error),
            )

    def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        model_name = (serialized or {}).get("name") or "LLM"
        span_id = self.tracer.start_span(
            name=f"llm:{model_name}",
            span_type=SpanType.LLM,
            application_id=self.application_id,
            jurisdiction=self.jurisdiction,
            input_payload={"prompts": prompts[:5]},
            tags={"run_id": str(run_id)},
            metadata=metadata or {},
        )
        self._active_spans[str(run_id)] = span_id

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        **kwargs: Any,
    ) -> None:
        span_id = self._active_spans.pop(str(run_id), None)
        if not span_id:
            return

        llm_output = response.llm_output or {}
        self.tracer.end_span(
            span_id=span_id,
            status=SpanStatus.OK,
            output_payload={
                "generations_count": len(response.generations),
                **llm_output,
            },
        )
        # Record token usage metric if present
        if "token_usage" in llm_output:
            tokens = llm_output["token_usage"].get("total_tokens", 0)
            self.tracer.record_metric(
                name="llm_total_tokens",
                value=float(tokens),
                unit="tokens",
                application_id=self.application_id,
            )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        **kwargs: Any,
    ) -> None:
        span_id = self._active_spans.pop(str(run_id), None)
        if not span_id:
            return

        self.tracer.end_span(
            span_id=span_id,
            status=SpanStatus.ERROR,
            error_message=str(error),
        )


# -----------------------------------------------------------------------------
# Main Tracer Engine
# -----------------------------------------------------------------------------


class InterconnectTracer:
    """Unified telemetry and tracing manager for InterconnectAI.

    Provides end-to-end tracing across LangGraph nodes, tool calls, and LLM vision/extraction
    latencies. Supports Langfuse and Phoenix integrations when credentials are present, with
    an automated in-memory & structured logging fallback.
    """

    def __init__(
        self,
        enable_langfuse: bool | None = None,
        enable_phoenix: bool | None = None,
    ) -> None:
        self._traces: dict[str, TraceRecord] = {}
        # span_id -> (trace_id, span, start_time)
        self._span_lookup: dict[str, tuple[str, SpanRecord, float]] = {}
        self._metrics: list[MetricRecord] = []

        # Check telemetry credentials
        self._langfuse_client: Any | None = None
        self._phoenix_enabled = False

        self._init_langfuse(enable_langfuse)
        self._init_phoenix(enable_phoenix)

    def _init_langfuse(self, explicit_enable: bool | None) -> None:
        """Initialize Langfuse client if credentials are configured."""
        pk = os.getenv("LANGFUSE_PUBLIC_KEY")
        sk = os.getenv("LANGFUSE_SECRET_KEY")
        should_enable = (explicit_enable is not False) and bool(pk and sk)

        if not should_enable:
            logger.debug(
                "Langfuse telemetry disabled or missing credentials; using in-memory tracer."
            )
            return

        try:
            from langfuse import Langfuse

            host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
            self._langfuse_client = Langfuse(public_key=pk, secret_key=sk, host=host)
            logger.info(f"Langfuse tracing successfully initialized (host={host})")
        except Exception as exc:
            logger.warning(
                f"Failed to initialize Langfuse client: {exc}. Falling back to local tracer."
            )
            self._langfuse_client = None

    def _init_phoenix(self, explicit_enable: bool | None) -> None:
        """Initialize Phoenix / OpenInference collector if configured."""
        collector = os.getenv("PHOENIX_COLLECTOR_ENDPOINT") or os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT"
        )
        should_enable = (explicit_enable is not False) and bool(collector)
        if should_enable:
            self._phoenix_enabled = True
            logger.info(f"Phoenix / OTel endpoint configured: {collector}")

    @property
    def has_langfuse(self) -> bool:
        """Return True if Langfuse remote client is actively configured."""
        return self._langfuse_client is not None

    @property
    def has_phoenix(self) -> bool:
        """Return True if Phoenix / OTel endpoint is active."""
        return self._phoenix_enabled

    # -------------------------------------------------------------------------
    # Core Trace Lifecycle
    # -------------------------------------------------------------------------

    def start_trace(
        self,
        name: str,
        application_id: str | None = None,
        jurisdiction: str | None = None,
        tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Start a new root trace and set it as active in the current context."""
        trace_id = f"trace-{uuid.uuid4().hex[:12]}"
        all_tags = dict(tags or {})
        if application_id:
            all_tags["application_id"] = application_id
        if jurisdiction:
            all_tags["jurisdiction"] = str(jurisdiction)

        record = TraceRecord(
            trace_id=trace_id,
            name=name,
            application_id=application_id,
            jurisdiction=str(jurisdiction) if jurisdiction else None,
            start_time_utc=datetime.now(UTC),
            tags=all_tags,
            metadata=dict(metadata or {}),
        )
        self._traces[trace_id] = record
        _CURRENT_TRACE.set(record)

        logger.info(
            f"Trace started: {trace_id} (name={name}, app_id={application_id}, "
            f"jurisdiction={jurisdiction})"
        )
        return trace_id

    def end_trace(
        self,
        trace_id: str | None = None,
        status: SpanStatus = SpanStatus.OK,
    ) -> TraceRecord | None:
        """End the specified or current root trace."""
        active = _CURRENT_TRACE.get()
        target_id = trace_id or (active.trace_id if active else None)
        if not target_id or target_id not in self._traces:
            return None

        trace = self._traces[target_id]
        now = datetime.now(UTC)
        total_duration = round((now - trace.start_time_utc).total_seconds() * 1000.0, 2)

        # Update trace model
        updated = TraceRecord(
            trace_id=trace.trace_id,
            name=trace.name,
            application_id=trace.application_id,
            jurisdiction=trace.jurisdiction,
            status=status,
            start_time_utc=trace.start_time_utc,
            end_time_utc=now,
            total_duration_ms=total_duration,
            spans=trace.spans,
            metrics=trace.metrics,
            tags=trace.tags,
            metadata=trace.metadata,
        )
        self._traces[target_id] = updated
        _CURRENT_TRACE.set(None)

        # Also flush to Langfuse if enabled
        if self._langfuse_client:
            with contextlib.suppress(Exception):
                self._langfuse_client.flush()

        logger.info(
            f"Trace completed: {target_id} in {total_duration:0.2f}ms "
            f"(status={status.value}, spans={len(updated.spans)})"
        )
        return updated

    @contextmanager
    def trace(
        self,
        name: str,
        application_id: str | None = None,
        jurisdiction: str | None = None,
        tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[str, None, None]:
        """Context manager to execute a code block under a root trace."""
        trace_id = self.start_trace(
            name=name,
            application_id=application_id,
            jurisdiction=jurisdiction,
            tags=tags,
            metadata=metadata,
        )
        outcome_status = SpanStatus.OK
        try:
            yield trace_id
        except Exception as exc:
            outcome_status = SpanStatus.ERROR
            self.record_error(exc, context={"trace_id": trace_id, "name": name})
            raise
        finally:
            self.end_trace(trace_id=trace_id, status=outcome_status)

    # -------------------------------------------------------------------------
    # Span Lifecycle
    # -------------------------------------------------------------------------

    def start_span(
        self,
        name: str,
        span_type: SpanType = SpanType.NODE,
        application_id: str | None = None,
        jurisdiction: str | None = None,
        input_payload: dict[str, Any] | None = None,
        tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Start a new span within the current or root trace."""
        current_trace = _CURRENT_TRACE.get()

        # Auto-create parent trace if not already created
        if not current_trace:
            new_trace_id = self.start_trace(
                name=f"auto:{name}",
                application_id=application_id,
                jurisdiction=jurisdiction,
            )
            current_trace = self._traces[new_trace_id]

        trace_id = current_trace.trace_id

        parent_span = _CURRENT_SPAN.get()
        parent_span_id = parent_span.span_id if parent_span else None
        span_id = f"span-{uuid.uuid4().hex[:10]}"

        app_id = application_id or (current_trace.application_id if current_trace else None)
        jur = jurisdiction or (current_trace.jurisdiction if current_trace else None)

        all_tags = dict(tags or {})
        if app_id:
            all_tags["application_id"] = app_id
        if jur:
            all_tags["jurisdiction"] = str(jur)
        all_tags["span_type"] = span_type.value

        start_time_perf = time.perf_counter()
        span = SpanRecord(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=name,
            span_type=span_type,
            application_id=app_id,
            jurisdiction=str(jur) if jur else None,
            status=SpanStatus.OK,
            start_time_utc=datetime.now(UTC),
            input_payload=_sanitize_for_telemetry(input_payload or {}),
            tags=all_tags,
            metadata=dict(metadata or {}),
        )

        self._span_lookup[span_id] = (trace_id, span, start_time_perf)
        _CURRENT_SPAN.set(span)
        return span_id

    def end_span(
        self,
        span_id: str,
        status: SpanStatus = SpanStatus.OK,
        output_payload: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> SpanRecord | None:
        """Conclude an active span, calculating its duration and attaching to trace."""
        lookup = self._span_lookup.pop(span_id, None)
        if not lookup:
            return None

        trace_id, span, start_time_perf = lookup
        duration_ms = round((time.perf_counter() - start_time_perf) * 1000.0, 2)
        end_time_utc = datetime.now(UTC)

        completed_span = SpanRecord(
            span_id=span.span_id,
            trace_id=span.trace_id,
            parent_span_id=span.parent_span_id,
            name=span.name,
            span_type=span.span_type,
            application_id=span.application_id,
            jurisdiction=span.jurisdiction,
            status=status,
            start_time_utc=span.start_time_utc,
            end_time_utc=end_time_utc,
            duration_ms=duration_ms,
            input_payload=span.input_payload,
            output_payload=_sanitize_for_telemetry(
                output_payload if output_payload is not None else span.output_payload
            ),
            error_message=error_message,
            tags=span.tags,
            metadata=span.metadata,
        )

        # Attach span to trace
        if trace_id in self._traces:
            trace = self._traces[trace_id]
            updated_trace = TraceRecord(
                trace_id=trace.trace_id,
                name=trace.name,
                application_id=trace.application_id,
                jurisdiction=trace.jurisdiction,
                status=(
                    SpanStatus.ERROR
                    if (status == SpanStatus.ERROR or trace.status == SpanStatus.ERROR)
                    else SpanStatus.OK
                ),
                start_time_utc=trace.start_time_utc,
                end_time_utc=trace.end_time_utc,
                total_duration_ms=trace.total_duration_ms,
                spans=[*trace.spans, completed_span],
                metrics=trace.metrics,
                tags=trace.tags,
                metadata=trace.metadata,
            )
            self._traces[trace_id] = updated_trace
            active_trace = _CURRENT_TRACE.get()
            if active_trace and active_trace.trace_id == trace_id:
                _CURRENT_TRACE.set(updated_trace)

            # Auto-end root trace if it was auto-created for this specific span
            if trace.name == f"auto:{span.name}":
                self.end_trace(trace_id=trace_id, status=updated_trace.status)

        # Reset active span
        active = _CURRENT_SPAN.get()
        if active and active.span_id == span_id:
            _CURRENT_SPAN.set(None)

        # Automatically record duration metric
        self.record_metric(
            name=f"latency_{span.span_type.value}_{span.name}",
            value=duration_ms,
            unit="ms",
            application_id=span.application_id,
            tags={"span_id": span_id, "status": status.value},
        )

        logger.debug(
            f"Span completed: {span.name} ({span.span_type.value}) in {duration_ms:0.2f}ms "
            f"[status={status.value}]"
        )
        return completed_span

    @contextmanager
    def span(
        self,
        name: str,
        span_type: SpanType = SpanType.NODE,
        application_id: str | None = None,
        jurisdiction: str | None = None,
        input_payload: dict[str, Any] | None = None,
        tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[str, None, None]:
        """Context manager to trace a child span with automatic timing and error logging."""
        span_id = self.start_span(
            name=name,
            span_type=span_type,
            application_id=application_id,
            jurisdiction=jurisdiction,
            input_payload=input_payload,
            tags=tags,
            metadata=metadata,
        )
        err_msg: str | None = None
        status = SpanStatus.OK
        try:
            yield span_id
        except Exception as exc:
            status = SpanStatus.ERROR
            err_msg = str(exc)
            raise
        finally:
            self.end_span(
                span_id=span_id,
                status=status,
                error_message=err_msg,
            )

    # -------------------------------------------------------------------------
    # Metric & Error Recording
    # -------------------------------------------------------------------------

    def record_metric(
        self,
        name: str,
        value: float,
        unit: str = "",
        application_id: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> MetricRecord:
        """Record an operational or scientific metric."""
        current_trace = _CURRENT_TRACE.get()
        app_id = application_id or (current_trace.application_id if current_trace else None)

        metric = MetricRecord(
            name=name,
            value=float(value),
            unit=unit,
            timestamp_utc=datetime.now(UTC),
            tags=dict(tags or {}),
            application_id=app_id,
        )
        self._metrics.append(metric)

        if current_trace and current_trace.trace_id in self._traces:
            trace = self._traces[current_trace.trace_id]
            updated_trace = TraceRecord(
                trace_id=trace.trace_id,
                name=trace.name,
                application_id=trace.application_id,
                jurisdiction=trace.jurisdiction,
                status=trace.status,
                start_time_utc=trace.start_time_utc,
                end_time_utc=trace.end_time_utc,
                total_duration_ms=trace.total_duration_ms,
                spans=trace.spans,
                metrics=[*trace.metrics, metric],
                tags=trace.tags,
                metadata=trace.metadata,
            )
            self._traces[current_trace.trace_id] = updated_trace

        return metric

    def record_error(
        self,
        error: BaseException,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record an error event with context metadata."""
        current_trace = _CURRENT_TRACE.get()
        app_id = current_trace.application_id if current_trace else None
        logger.error(
            f"Telemetry error recorded [app_id={app_id}, error_type={type(error).__name__}]: "
            f"{error} | context={context}"
        )
        self.record_metric(
            name="error_count",
            value=1.0,
            unit="count",
            application_id=app_id,
            tags={"exception": type(error).__name__},
        )

    # -------------------------------------------------------------------------
    # Decorators
    # -------------------------------------------------------------------------

    def trace_node(
        self,
        node_name: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for LangGraph nodes to capture execution metrics and audit transitions."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            name = node_name or func.__name__

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                state: dict[str, Any] = (
                    args[0] if args and isinstance(args[0], dict) else kwargs.get("state", {})
                )
                app_id = state.get("application_id") if isinstance(state, dict) else None
                jurisdiction = state.get("jurisdiction") if isinstance(state, dict) else None

                span_id = self.start_span(
                    name=name,
                    span_type=SpanType.NODE,
                    application_id=app_id,
                    jurisdiction=str(jurisdiction) if jurisdiction else None,
                    input_payload={
                        "current_step": (
                            (
                                state.get("current_step").value
                                if hasattr(state.get("current_step"), "value")
                                else str(state.get("current_step"))
                            )
                            if isinstance(state, dict)
                            else None
                        ),
                    },
                )
                span_status = SpanStatus.OK
                err_msg: str | None = None
                output_summary: dict[str, Any] = {}
                try:
                    result = func(*args, **kwargs)
                    if isinstance(result, dict):
                        if "current_step" in result:
                            step = result["current_step"]
                            output_summary["current_step"] = (
                                step.value if hasattr(step, "value") else str(step)
                            )
                        if "errors" in result:
                            output_summary["errors_count"] = len(result["errors"])
                        if "screen_results" in result:
                            output_summary["screens_evaluated"] = len(result["screen_results"])
                        if "deficiencies" in result:
                            output_summary["deficiencies_found"] = len(result["deficiencies"])
                    return result
                except Exception as exc:
                    span_status = SpanStatus.ERROR
                    err_msg = str(exc)
                    raise
                finally:
                    self.end_span(
                        span_id=span_id,
                        status=span_status,
                        output_payload=output_summary,
                        error_message=err_msg,
                    )

            return wrapper

        return decorator

    def trace_tool(
        self,
        tool_name: str | None = None,
        span_type: SpanType = SpanType.TOOL,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for tools, calculators, and screen engines."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            name = tool_name or func.__name__

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self.span(
                    name=name,
                    span_type=span_type,
                    input_payload={
                        "args_count": len(args),
                        "kwargs_keys": list(kwargs.keys()),
                    },
                ):
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    # -------------------------------------------------------------------------
    # LangChain Callback Provider
    # -------------------------------------------------------------------------

    def get_langchain_callback(
        self,
        application_id: str | None = None,
        jurisdiction: str | None = None,
    ) -> BaseCallbackHandler:
        """Return a LangChain/LangGraph compatible callback handler."""
        # Use Langfuse callback handler if remote Langfuse is enabled
        if self._langfuse_client:
            try:
                from langfuse.langchain import CallbackHandler

                return CallbackHandler()
            except Exception as exc:
                logger.warning(f"Could not instantiate Langfuse CallbackHandler: {exc}")

        # Fallback to local interconnect callback handler
        return InterconnectTracingCallback(
            tracer=self,
            application_id=application_id,
            jurisdiction=jurisdiction,
        )

    # -------------------------------------------------------------------------
    # Retrieval & Inspection
    # -------------------------------------------------------------------------

    def get_traces(self, application_id: str | None = None) -> list[TraceRecord]:
        """Return list of completed or active traces, optionally filtered by application ID."""
        records = list(self._traces.values())
        if application_id:
            return [tr for tr in records if tr.application_id == application_id]
        return records

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        """Retrieve trace by ID."""
        return self._traces.get(trace_id)

    def get_latest_trace(self, application_id: str) -> TraceRecord | None:
        """Retrieve the most recent trace for an application ID."""
        matches = [tr for tr in self._traces.values() if tr.application_id == application_id]
        if not matches:
            return None
        return max(matches, key=lambda tr: tr.start_time_utc)

    def get_metrics(self, application_id: str | None = None) -> list[MetricRecord]:
        """Return metrics list, optionally filtered by application ID."""
        if application_id:
            return [met for met in self._metrics if met.application_id == application_id]
        return list(self._metrics)

    def clear(self) -> None:
        """Clear in-memory traces and metrics (useful for isolated unit tests)."""
        self._traces.clear()
        self._span_lookup.clear()
        self._metrics.clear()
        _CURRENT_TRACE.set(None)
        _CURRENT_SPAN.set(None)

    def export_summary(self, trace_id: str) -> dict[str, Any]:
        """Return a human-readable telemetry summary for audit and dashboard display."""
        trace = self._traces.get(trace_id)
        if not trace:
            return {"error": f"Trace {trace_id} not found"}

        spans_summary = [
            {
                "name": sp.name,
                "type": sp.span_type.value,
                "duration_ms": sp.duration_ms,
                "status": sp.status.value,
                "error": sp.error_message,
            }
            for sp in trace.spans
        ]

        return {
            "trace_id": trace.trace_id,
            "application_id": trace.application_id,
            "jurisdiction": trace.jurisdiction,
            "status": trace.status.value,
            "total_duration_ms": trace.total_duration_ms,
            "spans_count": len(trace.spans),
            "spans": spans_summary,
            "tags": trace.tags,
        }


# -----------------------------------------------------------------------------
# Global Singleton Accessor
# -----------------------------------------------------------------------------

_GLOBAL_TRACER: InterconnectTracer | None = None


def get_tracer() -> InterconnectTracer:
    """Retrieve the global InterconnectTracer singleton instance."""
    global _GLOBAL_TRACER
    if _GLOBAL_TRACER is None:
        _GLOBAL_TRACER = InterconnectTracer()
    return _GLOBAL_TRACER
