"""Unit tests for InterconnectAI distributed tracing, telemetry, and observability."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from langchain_core.outputs import Generation, LLMResult

from api.main import app
from src.agents.graph import create_interconnection_graph
from src.agents.state import WorkflowStep
from src.observability.tracer import (
    InterconnectTracer,
    InterconnectTracingCallback,
    SpanStatus,
    SpanType,
    get_tracer,
)
from src.schemas.tariff import TariffJurisdiction
from src.utils.dataset import load_application_schema


@pytest.fixture(autouse=True)
def clean_tracer() -> None:
    """Ensure a clean tracer state before and after each test."""
    tracer = get_tracer()
    tracer.clear()
    yield
    tracer.clear()


# -----------------------------------------------------------------------------
# Unit Tests: Core Tracer Lifecycle & Fallback
# -----------------------------------------------------------------------------


def test_tracer_fallback_initialization():
    """Verify tracer initializes cleanly in offline fallback mode without credentials."""
    tracer = InterconnectTracer()
    assert tracer.has_langfuse is False
    assert tracer.has_phoenix is False
    assert len(tracer.get_traces()) == 0
    assert len(tracer.get_metrics()) == 0


def test_trace_lifecycle_manual():
    """Test manual start_trace and end_trace lifecycle."""
    tracer = InterconnectTracer()
    trace_id = tracer.start_trace(
        name="test_trace",
        application_id="APP-TEST-001",
        jurisdiction=TariffJurisdiction.CA_RULE_21.value,
        tags={"env": "test"},
    )
    assert trace_id.startswith("trace-")
    assert tracer.get_trace(trace_id) is not None

    record = tracer.end_trace(trace_id=trace_id, status=SpanStatus.OK)
    assert record is not None
    assert record.trace_id == trace_id
    assert record.application_id == "APP-TEST-001"
    assert record.status == SpanStatus.OK
    assert record.total_duration_ms is not None
    assert record.total_duration_ms >= 0.0


def test_trace_context_manager():
    """Test trace context manager and automatic status recording on success and error."""
    tracer = InterconnectTracer()

    with tracer.trace(
        name="successful_workflow",
        application_id="APP-OK-01",
        jurisdiction="CA_RULE_21",
    ) as trace_id:
        tracer.record_metric("custom_metric", 42.0, unit="kW")

    trace = tracer.get_trace(trace_id)
    assert trace is not None
    assert trace.status == SpanStatus.OK
    assert len(trace.metrics) == 1
    assert trace.metrics[0].name == "custom_metric"
    assert trace.metrics[0].value == 42.0

    # Error handling context
    with (
        pytest.raises(ValueError, match="Screening failure test"),
        tracer.trace(name="failing_workflow", application_id="APP-ERR-01"),
    ):
        raise ValueError("Screening failure test")

    failed_trace = tracer.get_latest_trace("APP-ERR-01")
    assert failed_trace is not None
    assert failed_trace.status == SpanStatus.ERROR


def test_span_lifecycle_and_nesting():
    """Test creating child spans within a trace context."""
    tracer = InterconnectTracer()

    with (
        tracer.trace(name="root_request", application_id="APP-SPAN-01"),
        tracer.span(
            name="sub_calc",
            span_type=SpanType.TOOL,
            input_payload={"val": 10},
        ) as span_id,
    ):
        assert span_id.startswith("span-")

    traces = tracer.get_traces("APP-SPAN-01")
    assert len(traces) == 1
    root = traces[0]
    assert len(root.spans) == 1
    span = root.spans[0]
    assert span.name == "sub_calc"
    assert span.span_type == SpanType.TOOL
    assert span.duration_ms is not None
    assert span.duration_ms >= 0.0


# -----------------------------------------------------------------------------
# Unit Tests: Decorators
# -----------------------------------------------------------------------------


def test_trace_node_decorator():
    """Verify @trace_node decorates state transitions and records execution summaries."""
    tracer = InterconnectTracer()

    @tracer.trace_node("mock_node")
    def mock_node(state: dict):
        return {
            "current_step": WorkflowStep.DETERMINISTIC_SCREENING,
            "screen_results": [1, 2, 3],
            "deficiencies": ["D-01"],
        }

    input_state = {
        "application_id": "APP-NODE-01",
        "jurisdiction": "CA_RULE_21",
        "current_step": WorkflowStep.INTAKE,
    }

    result = mock_node(input_state)
    assert result["current_step"] == WorkflowStep.DETERMINISTIC_SCREENING

    traces = tracer.get_traces("APP-NODE-01")
    assert len(traces) == 1
    spans = traces[0].spans
    assert len(spans) == 1
    assert spans[0].name == "mock_node"
    assert spans[0].output_payload.get("screens_evaluated") == 3
    assert spans[0].output_payload.get("deficiencies_found") == 1


def test_trace_tool_decorator():
    """Verify @trace_tool measures tool latency and tags."""
    tracer = InterconnectTracer()

    @tracer.trace_tool("math_power_flow", span_type=SpanType.TOOL)
    def calculate_power(kw: float, pf: float = 0.95) -> float:
        return kw / pf

    res = calculate_power(100.0, pf=1.0)
    assert res == 100.0

    metrics = [m for m in tracer.get_metrics() if "math_power_flow" in m.name]
    assert len(metrics) == 1
    assert metrics[0].unit == "ms"


# -----------------------------------------------------------------------------
# Unit Tests: Callback Handler
# -----------------------------------------------------------------------------


def test_interconnect_tracing_callback():
    """Verify callback handler intercepts chain, tool, and LLM events."""
    tracer = InterconnectTracer()
    cb = InterconnectTracingCallback(
        tracer=tracer,
        application_id="APP-CB-01",
        jurisdiction="CA_RULE_21",
    )

    with tracer.trace(
        name="root_callback_trace",
        application_id="APP-CB-01",
        jurisdiction="CA_RULE_21",
    ):
        # Simulate Chain Start/End
        cb.on_chain_start(serialized={"name": "ScreeningChain"}, inputs={"x": 1}, run_id="run-1")
        cb.on_chain_end(outputs={"res": "approved"}, run_id="run-1")

        # Simulate Tool Start/End
        cb.on_tool_start(serialized={"name": "ScreenTool"}, input_str="calc", run_id="run-2")
        cb.on_tool_end(output="passed", run_id="run-2")

        # Simulate LLM Start/End
        cb.on_llm_start(serialized={"name": "gpt-4o"}, prompts=["Review project"], run_id="run-3")
        llm_result = LLMResult(
            generations=[[Generation(text="Decision memo")]],
            llm_output={"token_usage": {"total_tokens": 150}},
        )
        cb.on_llm_end(response=llm_result, run_id="run-3")

    traces = tracer.get_traces("APP-CB-01")
    assert len(traces) >= 1
    all_spans = [s for t in traces for s in t.spans]
    span_names = [s.name for s in all_spans]

    assert "chain:ScreeningChain" in span_names
    assert "tool:ScreenTool" in span_names
    assert "llm:gpt-4o" in span_names

    token_metrics = [m for m in tracer.get_metrics("APP-CB-01") if m.name == "llm_total_tokens"]
    assert len(token_metrics) == 1
    assert token_metrics[0].value == 150.0


# -----------------------------------------------------------------------------
# Integration Tests: End-to-End Traced State Machine
# -----------------------------------------------------------------------------


def test_full_state_machine_execution_is_traced():
    """Verify a complete LangGraph execution produces traces and node spans."""
    tracer = get_tracer()
    tracer.clear()

    schema = load_application_schema("APP-001-PASS-ROOFTOP-SOLAR")
    initial_state = {
        "application_id": schema.application_id,
        "application_data": schema,
        "raw_documents": [],
        "jurisdiction": TariffJurisdiction.CA_RULE_21,
    }

    graph = create_interconnection_graph()
    cb = tracer.get_langchain_callback(application_id=schema.application_id)

    with tracer.trace(
        name="interconnection_workflow_test",
        application_id=schema.application_id,
        jurisdiction=TariffJurisdiction.CA_RULE_21.value,
    ) as trace_id:
        result = graph.invoke(
            initial_state,
            config={
                "configurable": {"thread_id": "test-thread-obs"},
                "callbacks": [cb],
            },
        )

    assert result.get("overall_outcome") is not None

    trace = tracer.get_trace(trace_id)
    assert trace is not None
    assert trace.application_id == "APP-001-PASS-ROOFTOP-SOLAR"
    assert trace.status == SpanStatus.OK
    assert trace.total_duration_ms is not None
    assert trace.total_duration_ms > 0

    # Ensure all primary nodes generated spans
    span_names = [s.name for s in trace.spans]
    assert "intake" in span_names
    assert "extraction" in span_names
    assert "retrieval" in span_names
    assert "screening" in span_names
    assert "synthesis" in span_names

    # Check summary export
    summary = tracer.export_summary(trace_id)
    assert summary["trace_id"] == trace_id
    assert summary["spans_count"] >= 5


# -----------------------------------------------------------------------------
# Integration Tests: FastAPI Telemetry Endpoints
# -----------------------------------------------------------------------------


def test_fastapi_telemetry_routes():
    """Verify /api/telemetry/traces and /api/telemetry/summary endpoints."""
    client = TestClient(app)

    # 1. Trigger a real screening run
    res = client.post(
        "/api/screen/run",
        json={"application_id": "APP-001-PASS-ROOFTOP-SOLAR"},
    )
    assert res.status_code == 200

    # 2. Query telemetry traces
    traces_res = client.get("/api/telemetry/traces?application_id=APP-001-PASS-ROOFTOP-SOLAR")
    assert traces_res.status_code == 200
    traces = traces_res.json()
    assert len(traces) >= 1

    first_trace = traces[0]
    trace_id = first_trace["trace_id"]
    assert first_trace["application_id"] == "APP-001-PASS-ROOFTOP-SOLAR"

    # 3. Query telemetry summary
    summary_res = client.get(f"/api/telemetry/summary/{trace_id}")
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["trace_id"] == trace_id
    assert summary["spans_count"] > 0
    assert len(summary["spans"]) > 0

    # 4. Check 404 on nonexistent trace
    bad_res = client.get("/api/telemetry/summary/trace-nonexistent")
    assert bad_res.status_code == 404
