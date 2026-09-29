"""FastAPI main application entry point for InterconnectAI."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.applications import router as applications_router
from api.schemas import HealthCheckResponse


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    app = FastAPI(
        title="InterconnectAI Screening API",
        description="Autonomous Grid Interconnection Reviewer & Screening Copilot API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Enable CORS for local Streamlit, Next.js, or external client development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get(
        "/health",
        response_model=HealthCheckResponse,
        summary="Service health check",
        tags=["system"],
    )
    async def health_check() -> HealthCheckResponse:
        """Return operational health status, API version, and supported jurisdictions."""
        return HealthCheckResponse()

    app.include_router(applications_router)
    return app


app = create_app()
