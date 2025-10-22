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
        
        # Event bus (for publishing events)
        self.event_bus = create_event_bus(self.settings.redis_url)
        
        # Create agent
        self.agent = create_summarizer_agent(
            model=self.settings.openai_default_model,
            reasoning_effort=self.settings.reasoning_effort,
        )
        
        # Register health checks
        self._register_health_checks()

    def _register_health_checks(self) -> None:
        """Register service health checks."""
        self.health_checker.register_check("liveness", lambda: True)
        
        # Redis health check
        async def redis_check() -> tuple[bool, str]:
            return await check_redis_connection(self.event_bus.redis)
        
        self.health_checker.register_check("redis", redis_check)
        
        # OpenAI API health check
        self.health_checker.register_check(
            "openai_api",
            lambda: check_openai_api(self.settings.openai_api_key),
        )

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
    logger.info("Agent summarizer service started")


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
    """Health check endpoint per PRIME_DIRECTIVE requirements."""
    health_report = await service.health_checker.check_health()
    
    status_code = 200 if health_report.is_available() else 503
    
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

