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

# Import OpenAI client directly for now since agents SDK may not be available
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    AsyncOpenAI = None
    OPENAI_AVAILABLE = False

# Placeholder for agents SDK compatibility
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


class SimpleSummarizerAgent:
    """Simplified summarizer agent using direct OpenAI API."""
    
    def __init__(self, model: str = "gpt-4", api_key: Optional[str] = None):
        """Initialize the agent.
        
        Args:
            model: OpenAI model to use
            api_key: OpenAI API key (or from env)
        """
        import os
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("BUDAI_OPENAI_API_KEY")
        if not OPENAI_AVAILABLE:
            raise RuntimeError("OpenAI package not available")
        self.client = AsyncOpenAI(api_key=self.api_key)
        
        self.instructions = """You are a professional meeting summarizer specializing in sales calls and business meetings.

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

Respond with a valid JSON object following this structure:
{
  "title": "meeting title",
  "summary": "executive summary",
  "key_points": ["point1", "point2"],
  "action_items": [{"description": "...", "owner": "...", "due_date": "...", "priority": "..."}],
  "decisions": [{"decision": "...", "rationale": "...", "stakeholders": []}],
  "risks": ["risk1", "risk2"],
  "next_steps": ["step1", "step2"],
  "attendees_mentioned": ["name1", "name2"],
  "metadata": {}
}
"""


def create_summarizer_agent(
    model: str = "gpt-4",
    reasoning_effort: str = "medium",
) -> SimpleSummarizerAgent:
    """Create the meeting summarizer agent.

    The agent produces a deterministic JSON structure that can be fed to
    the follow-up agent and notification templates.

    Args:
        model: OpenAI model to use
        reasoning_effort: Reasoning effort level (low, medium, high)

    Returns:
        Configured Agent instance
    """
    return SimpleSummarizerAgent(model=model)


async def summarize_meeting(
    agent: SimpleSummarizerAgent,
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
    import json
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Prepare input prompt
    context_str = ""
    if additional_context:
        context_str = "\n\nAdditional Context:\n"
        for key, value in additional_context.items():
            context_str += f"- {key}: {value}\n"

    user_prompt = f"""Meeting: {title}
Meeting ID: {meeting_id}
{context_str}

Transcript:
{transcript}

Please provide a comprehensive summary of this meeting."""

    try:
        # Call OpenAI API with structured output request
        response = await agent.client.chat.completions.create(
            model=agent.model,
            messages=[
                {"role": "system", "content": agent.instructions},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        
        # Parse the response
        content = response.choices[0].message.content
        result_data = json.loads(content)
        
        # Convert action items and decisions to proper models
        action_items = [
            ActionItem(**item) if isinstance(item, dict) else ActionItem(description=str(item))
            for item in result_data.get("action_items", [])
        ]
        
        decisions = [
            Decision(**dec) if isinstance(dec, dict) else Decision(decision=str(dec))
            for dec in result_data.get("decisions", [])
        ]
        
        # Create summary object
        summary = MeetingSummary(
            title=result_data.get("title", title),
            summary=result_data.get("summary", ""),
            key_points=result_data.get("key_points", []),
            action_items=action_items,
            decisions=decisions,
            risks=result_data.get("risks", []),
            next_steps=result_data.get("next_steps", []),
            attendees_mentioned=result_data.get("attendees_mentioned", []),
            metadata=result_data.get("metadata", {}),
        )
        
    except Exception as exc:
        logger.error(f"Failed to generate summary: {exc}")
        # Fallback summary
        summary = MeetingSummary(
            title=title,
            summary=f"Summary generation encountered an error: {str(exc)}",
            metadata={"meeting_id": meeting_id, "error": str(exc)},
        )

    # Add metadata
    summary.metadata["meeting_id"] = meeting_id
    summary.metadata["agent_name"] = "Meeting Summarizer"
    summary.metadata["model"] = agent.model

    return summary


# Synchronous wrapper for compatibility
def summarize_meeting_sync(
    agent: SimpleSummarizerAgent,
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

