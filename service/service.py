"""
Meeting Summarizer Agent HTTP Service.

Exposes the summarizer agent as an HTTP API for orchestrator invocation.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared import (
    AgentServiceSettings,
    HealthChecker,
    ServiceObservability,
    check_openai_api,
    check_redis_connection,
    create_event_bus,
    init_observability,
)

from .agent import ActionItem, Decision, MeetingSummary, create_summarizer_agent, summarize_meeting

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SummarizeRequest(BaseModel):
    """Request to summarize a meeting."""

    task_id: str
    meeting_id: str
    title: str
    transcript: str
    additional_context: Optional[Dict[str, Any]] = None


class SummarizeResponse(BaseModel):
    """Response from meeting summarization."""

    task_id: str
    meeting_id: str
    summary: str
    key_points: List[str]
    action_items: List[Dict[str, Any]]
    decisions: List[Dict[str, Any]]
    risks: List[str]
    next_steps: List[str]
    attendees_mentioned: List[str]
    metadata: Dict[str, Any]


class AgentSummarizerService:
    """Meeting Summarizer agent service application."""

    def __init__(self) -> None:
        """Initialize agent service."""
        self.settings = AgentServiceSettings()
        self.settings.service_name = "agent-summarizer"
        self.settings.port = 8002
        
        self.observability = init_observability("agent-summarizer", self.settings.service_version)
        self.health_checker = HealthChecker("agent-summarizer", self.settings.service_version)
        
        # Event bus (for publishing events) - gracefully handle Redis unavailability
        try:
            self.event_bus = create_event_bus(self.settings.redis_url)
            logger.info("Event bus initialized successfully")
        except Exception as exc:
            logger.warning("Failed to initialize event bus: %s. Service will continue without event publishing.", exc)
            self.event_bus = None
        
        # Create agent - gracefully handle initialization errors
        try:
            self.agent = create_summarizer_agent(
                model=self.settings.openai_default_model,
                reasoning_effort=self.settings.reasoning_effort,
            )
            logger.info("Agent initialized successfully with model: %s", self.settings.openai_default_model)
        except Exception as exc:
            logger.error("Failed to initialize agent: %s", exc)
            self.agent = None
        
        # Register health checks
        self._register_health_checks()

    def _register_health_checks(self) -> None:
        """Register service health checks."""
        # Liveness check - always passes if service is running
        self.health_checker.register_check("liveness", lambda: (True, "Service is running"))
        
        # Redis health check - only if event bus is available
        if self.event_bus is not None:
            async def redis_check() -> tuple[bool, str]:
                try:
                    return await check_redis_connection(self.event_bus.redis)
                except Exception as exc:
                    return (False, f"Redis check failed: {exc}")
            
            self.health_checker.register_check("redis", redis_check)
        else:
            # Register a check that reports Redis as unavailable but not critical
            self.health_checker.register_check("redis", lambda: (False, "Event bus not initialized"))
        
        # OpenAI API health check - make it non-blocking
        async def openai_check() -> tuple[bool, str]:
            try:
                return await check_openai_api(self.settings.openai_api_key)
            except Exception as exc:
                return (False, f"OpenAI check failed: {exc}")
        
        self.health_checker.register_check("openai_api", openai_check)
        
        # Agent check
        def agent_check() -> tuple[bool, str]:
            if self.agent is not None:
                return (True, "Agent initialized")
            return (False, "Agent not initialized")
        
        self.health_checker.register_check("agent", agent_check)

    async def initialize(self) -> None:
        """Initialize async components."""
        logger.info("Initializing agent summarizer service")

    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        logger.info("Shutting down agent summarizer service")

    async def summarize(self, request: SummarizeRequest) -> SummarizeResponse:
        """Summarize a meeting.

        Args:
            request: Summarization request

        Returns:
            Summarization response
        """
        # Check if agent is initialized
        if self.agent is None:
            logger.error("Cannot summarize: agent not initialized")
            raise HTTPException(
                status_code=503,
                detail="Service unavailable: agent not initialized. Check environment variables.",
            )
        
        with self.observability.trace_operation("agent.summarize") as span:
            span.set_tag("task_id", request.task_id)
            span.set_tag("meeting_id", request.meeting_id)
            span.set_tag("transcript_length", len(request.transcript))
            
            logger.info("Summarizing meeting: %s (%s)", request.meeting_id, request.title)
            
            try:
                # Invoke agent
                summary = await summarize_meeting(
                    agent=self.agent,
                    meeting_id=request.meeting_id,
                    title=request.title,
                    transcript=request.transcript,
                    additional_context=request.additional_context,
                )
                
                # Emit metrics
                self.observability.emit_metric(
                    "agent.invocation.success",
                    1.0,
                    {"agent": "summarizer"},
                )
                
                # Publish event if event bus is available
                if self.event_bus is not None:
                    try:
                        from shared import SummaryGeneratedEvent
                        event = SummaryGeneratedEvent(
                            meeting_id=request.meeting_id,
                            summary=summary.summary,
                            action_items=[item.model_dump() for item in summary.action_items],
                            risks=summary.risks,
                            summary_metadata=summary.metadata,
                        )
                        await self.event_bus.publish(event)
                    except Exception as event_exc:
                        logger.warning("Failed to publish event: %s", event_exc)
                
                # Convert to response
                response = SummarizeResponse(
                    task_id=request.task_id,
                    meeting_id=request.meeting_id,
                    summary=summary.summary,
                    key_points=summary.key_points,
                    action_items=[item.model_dump() for item in summary.action_items],
                    decisions=[dec.model_dump() for dec in summary.decisions],
                    risks=summary.risks,
                    next_steps=summary.next_steps,
                    attendees_mentioned=summary.attendees_mentioned,
                    metadata=summary.metadata,
                )
                
                logger.info(
                    "Meeting summarized: %s - %d action items, %d risks",
                    request.meeting_id,
                    len(summary.action_items),
                    len(summary.risks),
                )
                
                return response
            
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception("Failed to summarize meeting: %s", exc)
                
                self.observability.emit_metric(
                    "agent.invocation.failure",
                    1.0,
                    {"agent": "summarizer"},
                )
                
                raise HTTPException(
                    status_code=500,
                    detail=f"Summarization failed: {str(exc)}",
                )


# Create FastAPI app
app = FastAPI(title="BudAI Agent Summarizer", version="1.0.0")
service = AgentSummarizerService()


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize on startup."""
    await service.initialize()
    logger.info("=" * 60)
    logger.info("Agent summarizer service started")
    logger.info("Environment: %s", service.settings.environment)
    logger.info("Port: %s", service.settings.port)
    logger.info("Model: %s", service.settings.openai_default_model)
    logger.info("Agent initialized: %s", service.agent is not None)
    logger.info("Event bus initialized: %s", service.event_bus is not None)
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup on shutdown."""
    await service.shutdown()


@app.get("/")
async def root() -> JSONResponse:
    """Root endpoint."""
    return JSONResponse(
        content={
            "service": "BudAI Agent Summarizer",
            "version": "1.0.0",
            "agent": "Meeting Summarizer",
            "status": "running",
        }
    )


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint per PRIME_DIRECTIVE requirements.
    
    Returns 200 if the liveness check passes (service is running).
    Dependency failures (Redis, OpenAI) are reported but don't fail the health check.
    """
    health_report = await service.health_checker.check_health()
    
    # Check if liveness check passed - that's all we need for Railway health check
    liveness_check = next((c for c in health_report.checks if c.name == "liveness"), None)
    is_alive = liveness_check and liveness_check.status == "healthy"
    
    # Return 200 if service is alive, even if some dependencies are unhealthy
    # This allows the service to start and be marked as healthy by Railway
    status_code = 200 if is_alive else 503
    
    return JSONResponse(
        content=health_report.model_dump(),
        status_code=status_code,
    )


@app.post("/summarize")
async def summarize(request: SummarizeRequest) -> JSONResponse:
    """Summarize a meeting.

    Args:
        request: Summarization request with meeting details

    Returns:
        Structured meeting summary
    """
    response = await service.summarize(request)
    return JSONResponse(content=response.model_dump())


def main() -> None:
    """Run the agent summarizer service."""
    import uvicorn

    port = int(os.getenv("PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()

