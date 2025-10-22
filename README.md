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

### Required Environment Variables

Make sure these environment variables are set in Railway:

**Required:**
- `BUDAI_OPENAI_API_KEY` - Your OpenAI API key (starts with `sk-`)
- `PORT` - Port for the service (Railway sets this automatically, typically 8002)

**Optional (with defaults):**
- `BUDAI_REDIS_URL` - Redis connection URL (defaults to `redis://localhost:6379/0`)
- `BUDAI_OPENAI_DEFAULT_MODEL` - OpenAI model to use (defaults to `gpt-4`)
- `BUDAI_ENVIRONMENT` - Environment name (defaults to `development`)

### Deployment Steps

1. **Set Environment Variables in Railway:**
   ```
   BUDAI_OPENAI_API_KEY=sk-your-api-key-here
   ```

2. **Deploy:**
   ```bash
   # Using Railway CLI
   railway up

   # Or via Railway dashboard
   # 1. Connect this repository
   # 2. Set environment variables
   # 3. Deploy
   ```

The Railway configuration is defined in `railway.json`.

### Health Check Configuration

The service includes a graceful health check that:
- Returns 200 if the service is running (liveness check)
- Reports dependency status (Redis, OpenAI) without failing the check
- Allows the service to start even if some dependencies are unavailable

This ensures Railway marks the deployment as successful even if Redis is not configured.

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

- **Redis:** Health checks and event subscription (optional - service will start without it)
- **OpenAI API:** GPT-4 for summarization (required for actual summarization)

## Troubleshooting

### Health Check Failures on Railway

If your deployment is failing health checks:

1. **Check logs for startup errors:**
   - Look for "Agent initialized: False" - indicates OpenAI API key issue
   - Look for "Event bus initialized: False" - indicates Redis connection issue (non-critical)

2. **Verify environment variables:**
   - `BUDAI_OPENAI_API_KEY` must be set correctly
   - Make sure the API key starts with `sk-`

3. **Test health endpoint:**
   ```bash
   curl https://your-service.railway.app/health
   ```
   Should return 200 even if dependencies are unhealthy

4. **Check Railway logs:**
   - The service logs startup information including initialization status
   - Look for the "=" bordered startup message with component status

### Common Issues

**Issue:** Service fails to start with "agent not initialized"
- **Solution:** Set `BUDAI_OPENAI_API_KEY` environment variable in Railway

**Issue:** Service starts but summarization endpoint returns 503
- **Solution:** Agent initialization failed. Check that OpenAI API key is valid and has credits

**Issue:** Redis connection errors in logs
- **Solution:** This is non-critical. The service will work without Redis, but events won't be published

## License

MIT License - Part of the BudAI project

