"""
Meeting Summarizer Agent.

Produces structured meeting summaries with action items, risks, and decisions.
Uses OpenAI Agents SDK with structured output.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pydantic import BaseModel

# Import agents from the original SDK (we'll need to include it)
try:
    from agents import Agent, AgentOutputSchema, ModelSettings
    from agents.run import RunConfig
    from openai.types.shared import Reasoning
except ImportError:
    # Fallback - we'll need to copy the agents SDK or install it
    Agent = None
    AgentOutputSchema = None
    ModelSettings = None
    RunConfig = None
    Reasoning = None


class ActionItem(BaseModel):
    """An action item extracted from the meeting."""

    description: str
    owner: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None


class Decision(BaseModel):
    """A decision made during the meeting."""

    decision: str
    rationale: Optional[str] = None
    stakeholders: List[str] = []


class MeetingSummary(BaseModel):
    """Structured summary for downstream automation."""

    title: str
    summary: str
    key_points: List[str] = []
    action_items: List[ActionItem] = []
    decisions: List[Decision] = []
    risks: List[str] = []
    next_steps: List[str] = []
    attendees_mentioned: List[str] = []
    metadata: Dict[str, Any] = {}


def create_summarizer_agent(
    model: str = "gpt-4",
    reasoning_effort: str = "medium",
) -> Agent:
    """Create the meeting summarizer agent.

    The agent produces a deterministic JSON structure that can be fed to
    the follow-up agent and notification templates.

    Args:
        model: OpenAI model to use
        reasoning_effort: Reasoning effort level (low, medium, high)

    Returns:
        Configured Agent instance
    """
    if Agent is None:
        raise RuntimeError("OpenAI Agents SDK not available. Install openai-agents package.")

    instructions = """You are a professional meeting summarizer specializing in sales calls and business meetings.

Your role is to:
1. Extract key points, decisions, and action items from meeting transcripts
2. Identify risks, blockers, and concerns raised
3. Note next steps and follow-up requirements
4. Capture attendee names when mentioned
5. Provide a concise executive summary

Guidelines:
- Be concise but comprehensive
- Focus on actionable items and decisions
- Highlight risks and concerns prominently
- Use bullet points for clarity
- Extract owner names for action items when mentioned
- Identify due dates if specified
- Note priority levels (high/medium/low) when indicated

Your output will be used for:
- Automated follow-up emails
- CRM updates
- Team notifications
- Executive reporting
"""

    return Agent(
        name="Meeting Summarizer",
        instructions=instructions,
        model=model,
        model_settings=ModelSettings(
            reasoning=Reasoning(effort=reasoning_effort),
            verbosity="low",
        ) if Reasoning else None,
        tools=[],  # No external tools needed for summarization
        output_type=AgentOutputSchema(MeetingSummary, strict_json_schema=False),
    )


async def summarize_meeting(
    agent: Agent,
    meeting_id: str,
    title: str,
    transcript: str,
    additional_context: Optional[Dict[str, Any]] = None,
) -> MeetingSummary:
    """Summarize a meeting using the agent.

    Args:
        agent: Configured summarizer agent
        meeting_id: Meeting identifier
        title: Meeting title
        transcript: Meeting transcript text
        additional_context: Optional additional context

    Returns:
        Structured meeting summary
    """
    # Prepare input prompt
    context_str = ""
    if additional_context:
        context_str = "\n\nAdditional Context:\n"
        for key, value in additional_context.items():
            context_str += f"- {key}: {value}\n"

    prompt = f"""Meeting: {title}
Meeting ID: {meeting_id}
{context_str}

Transcript:
{transcript}

Please provide a comprehensive summary of this meeting."""

    # Run agent
    from agents import Runner

    runner = Runner(agent)
    result = await runner.run(prompt)

    # Extract structured output
    if hasattr(result, 'output') and isinstance(result.output, MeetingSummary):
        summary = result.output
    else:
        # Fallback if structured output fails
        summary = MeetingSummary(
            title=title,
            summary="Summary generation failed - structured output not available",
            metadata={"meeting_id": meeting_id, "error": "structured_output_failed"},
        )

    # Add metadata
    summary.metadata["meeting_id"] = meeting_id
    summary.metadata["agent_name"] = "Meeting Summarizer"
    summary.metadata["model"] = agent.model

    return summary


# Synchronous wrapper for compatibility
def summarize_meeting_sync(
    agent: Agent,
    meeting_id: str,
    title: str,
    transcript: str,
    additional_context: Optional[Dict[str, Any]] = None,
) -> MeetingSummary:
    """Synchronous wrapper for summarize_meeting.

    Args:
        agent: Configured summarizer agent
        meeting_id: Meeting identifier
        title: Meeting title
        transcript: Meeting transcript text
        additional_context: Optional additional context

    Returns:
        Structured meeting summary
    """
    import asyncio

    return asyncio.run(
        summarize_meeting(agent, meeting_id, title, transcript, additional_context)
    )

