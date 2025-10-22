# BudAI Agent Summarizer

AI agent for generating structured meeting summaries with action items and risk identification.

## Purpose

The Agent Summarizer uses OpenAI Agents SDK to:
- Generate structured meeting summaries
- Extract action items with owners and deadlines
- Identify risks and blockers
- Capture key decisions
- Format results for downstream workflows

**Port:** 8002

## Environment Variables

Required environment variables:

```bash
# Service identity
BUDAI_SERVICE_NAME=agent-summarizer
BUDAI_SERVICE_VERSION=1.0.0
BUDAI_ENVIRONMENT=production

# Redis (for health checks and events)
BUDAI_REDIS_URL=redis://...

# OpenAI
BUDAI_OPENAI_API_KEY=sk-...
BUDAI_OPENAI_DEFAULT_MODEL=gpt-4o

# Agent Configuration
AGENT_MAX_RETRIES=3
AGENT_TIMEOUT_SECONDS=120
```

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start Redis locally (for health checks):
```bash
docker run -d -p 6379:6379 redis:7-alpine
```

3. Set environment variables:
```bash
export BUDAI_SERVICE_NAME=agent-summarizer
export BUDAI_REDIS_URL=redis://localhost:6379/0
export BUDAI_OPENAI_API_KEY=sk-...
```

4. Run the service:
```bash
python service/service.py
```

The service will start on `http://localhost:8002`.

## Railway Deployment

Deploy directly from this repository:

```bash
# Using Railway CLI
railway up

# Or via Railway dashboard
# 1. Connect this repository
# 2. Set environment variables
# 3. Deploy
```

The Railway configuration is defined in `railway.json`.

## Health Check

```bash
curl http://localhost:8002/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "agent-summarizer",
  "version": "1.0.0",
  "dependencies": {
    "redis": "healthy",
    "openai": "healthy"
  }
}
```

## API Endpoints

### Agent Execution
- `POST /agent/summarize` - Generate meeting summary

Request body:
```json
{
  "meeting_id": "meeting-123",
  "transcript": "...",
  "metadata": {
    "title": "Sprint Planning",
    "attendees": ["alice@example.com", "bob@example.com"],
    "duration_minutes": 60
  }
}
```

Response:
```json
{
  "summary": {
    "overview": "...",
    "action_items": [
      {
        "task": "Review PRs",
        "owner": "alice@example.com",
        "deadline": "2025-10-25"
      }
    ],
    "risks": [
      {
        "description": "Dependency on external API",
        "severity": "medium"
      }
    ],
    "decisions": ["Approved budget increase"],
    "next_steps": ["Schedule follow-up"]
  },
  "execution_time_ms": 3421
}
```

### Health
- `GET /health` - Health check endpoint

## Architecture

The Agent Summarizer:
1. Receives summarization requests via HTTP
2. Uses OpenAI Agents SDK to process transcripts
3. Structures output with action items, risks, decisions
4. Returns formatted summary
5. Can be scaled horizontally for concurrent meetings

## Agent Implementation

Built using OpenAI Agents SDK with:
- **Tools:** Custom functions for extracting action items, risks
- **Instructions:** Domain-specific prompts for meeting analysis
- **Memory:** Context from previous meetings (when available)
- **Validation:** Output schema validation via Pydantic

## Scaling

The agent-summarizer is stateless and can be scaled based on meeting load:
- Peak hours: 3+ replicas
- Off-hours: 1 replica
- Auto-scaling based on CPU/memory

## Dependencies

- **Redis:** Health checks and event subscription (required)
- **OpenAI API:** GPT-4 for summarization (required)

## License

MIT License - Part of the BudAI project

