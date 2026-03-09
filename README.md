# marathon-bot

A Telegram bot that connects Strava to an AI coach. It uses Google ADK (Agent Development Kit) to provide marathon training plans, run summaries, and nutrition logging through a multi-agent system.

## Features

- **Strava integration**: OAuth for connecting accounts; webhooks for activity create/update/delete
- **Telegram**: Commands and chat; send messages and receive AI responses
- **Multi-agent AI**: Specialist agents for Strava data queries, motivational coaching, and nutrition
- **Marathon plans**: Create, update, and delete training plans; get guidance after workouts
- **Meal logging**: Log meals with macronutrient estimates and set nutrition targets

## Project structure

| Path | Purpose |
|------|---------|
| `app.py` | FastAPI app: webhooks, OAuth callback, session handling, ADK runner. |
| `main_agent/` | ADK agents and tools: `agent.py` (router + sub-agents), `agent_tools.py` (DB queries, plans, meals). |
| `strava_client.py` | Strava OAuth, token refresh, activity fetch and sync. |
| `database.py` | SQLAlchemy engine, sessions, token and lookup helpers. |
| `models.py` | ORM models: Token, Activity, MarathonPlan, Meal, UserTarget. |
| `create_strava_webhook.py` | One-off script to register the Strava webhook (run with env set). |
| `tests/` | Pytest tests for the app. |
| `helper_files/` | Dev-only utilities (e.g. directory tree script); see `helper_files/README.md`. |

## Architecture

The app is a FastAPI service that receives webhooks from Strava and Telegram. Incoming events are routed to an ADK Runner, which delegates to a main agent and sub-agents (Strava agent, motivation agent, nutritionist agent). User and token state are stored in a database (PostgreSQL or SQLite). Strava activities, marathon plans, meals, and user targets are persisted in the same database.

```
Strava/Telegram → FastAPI → ADK Runner → Main Agent → Strava / Motivation / Nutritionist agents
                                    ↓
                              Database (tokens, activities, plans, meals)
```

## Prerequisites

- Python 3.11+
- A [Strava API application](https://www.strava.com/settings/api) (client ID, client secret, redirect URI)
- A [Telegram Bot](https://core.telegram.org/bots#botfather) (bot token)
- Optional: Google Cloud (Vertex AI, Secret Manager) for Gemini and production secrets

## Local setup

1. Clone the repo and install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Copy the example env file and fill in your values:

   ```bash
   cp .env.example .env
   ```

   See [Environment variables](#environment-variables) below.

3. Run the app (database tables are created on startup):

   ```bash
   uvicorn app:app --reload
   ```

   Or:

   ```bash
   python -m uvicorn app:app --reload
   ```

4. For local Strava webhook testing (e.g. with ngrok), set `STRAVA_WEBHOOK_URL` to your public URL and run:

   ```bash
   python create_strava_webhook.py
   ```

## Environment variables

Use `.env.example` as a reference. Required variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (e.g. `postgresql://user:password@host:5432/dbname`). If unset, the app uses SQLite at `./strava.db`. |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from BotFather. |
| `STRAVA_CLIENT_ID` | Strava API application client ID. |
| `STRAVA_CLIENT_SECRET` | Strava API application client secret. |
| `STRAVA_REDIRECT_URI` | OAuth redirect URI registered in your Strava app (e.g. `https://your-domain.com/callback`). |
| `STRAVA_VERIFY_TOKEN` | A secret you choose for Strava webhook subscription verification. |
| `STRAVA_WEBHOOK_URL` | Full URL where Strava sends webhook events (e.g. `https://your-domain.com/webhook`). Used by `create_strava_webhook.py`. |
| `GOOGLE_API_KEY` | Google API key for Gemini (or use Vertex AI). |
| `GOOGLE_GENAI_USE_VERTEXAI` | Set to `"true"` when using Vertex AI instead of an API key. |

Optional: `TESTING=true` skips ADK Runner and DB init (e.g. for unit tests). `PORT` (default 8080). `DEBUG` enables extra logging (e.g. parsed `DATABASE_URL`).

## Deployment

The repo includes a `Dockerfile` and `cloudbuild.yaml` for building and deploying to Google Cloud Run. Store secrets (e.g. `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `STRAVA_VERIFY_TOKEN`, Strava and Google credentials) in a secret manager (e.g. GCP Secret Manager) and inject them at runtime—do not put secrets in code or in the image.

**Security**: If you deploy with public access (e.g. Cloud Run with `--allow-unauthenticated`), endpoints such as `/profile/{athlete_id}` are reachable by anyone who knows the URL. Restrict production access using IAM, a reverse proxy, or a VPN as appropriate.

## Testing

Run tests with:

```bash
pytest
```

With `TESTING=true`, the app skips ADK Runner and database initialization so unit tests can run without full credentials.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, running tests, and how to submit changes.

## License

See [LICENSE](LICENSE).
