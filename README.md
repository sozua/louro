<div align="center">
  <img src="assets/logo.png" alt="Louro" width="120">
</div>

<p align="center">
  AI code reviewer for GitHub pull requests.<br>
  Self-hosted, bring your own API key.
</p>

Open a PR and Louro posts inline review comments. Reply to a comment and it replies back. If you correct it, it remembers for next time.

## Setup

You need a GitHub App, a Vercel AI Gateway API key, and a PostgreSQL database.

### 1. Create a GitHub App

Go to **GitHub Settings > Developer settings > GitHub Apps > New GitHub App**.

| Field | Value |
|-------|-------|
| Name | anything you want (e.g. `louro-dev`) |
| Homepage URL | `http://localhost:8000` (or your deploy URL) |
| Webhook URL | your public URL + `/webhooks/github` |
| Webhook secret | generate one: `openssl rand -hex 20` |

Permissions:

| Scope | Permission |
|-------|-----------:|
| Contents | Read |
| Pull requests | Read & Write |
| Metadata | Read |
| Members (org) | Read |

Events to subscribe to: Pull request, Pull request review comment, Push, Installation.

After creating the app, copy the **App ID**, generate a **private key** (.pem file), and install the app on the repos you want reviewed.

### 2. Clone and configure

```bash
git clone https://github.com/sozua/louro.git
cd louro
make setup
```

This installs dependencies, starts PostgreSQL via Docker, and creates a `.env` file. Open `.env` and fill in your credentials:

```bash
# Required -- GitHub App
GITHUB_APP_ID=123456
GITHUB_WEBHOOK_SECRET=your_secret_here
GITHUB_PRIVATE_KEY_PATH=./your-app.private-key.pem

# Required -- AI Gateway
AI_GATEWAY_API_KEY=your-gateway-key
```

### 3. Expose your local server

Louro needs to receive webhooks from GitHub:

```bash
ngrok http 8000
```

Copy the `https://...` URL and set it as the Webhook URL in your GitHub App settings, appending `/webhooks/github`.

### 4. Start the server

```bash
make dev
```

Open a PR on an installed repo. Louro will post a review once the agent finishes (usually under a minute, depending on diff size and model).

Check the server is running with `make verify` or `http://localhost:8000/health`.

## Running with Docker

```bash
cp .env.example .env
# fill in .env
docker compose up
```

Starts both the app and PostgreSQL on port 8000.

## Activating a repository

When you install the GitHub App on a repo, it gets registered with status `pending`. Louro won't review PRs until you activate it:

```bash
# List registered repos
curl http://localhost:8000/repos

# Activate (triggers onboarding -- reads the codebase to learn its conventions)
curl -X POST http://localhost:8000/repos/owner/repo/activate

# Deactivate
curl -X POST http://localhost:8000/repos/owner/repo/deactivate
```

Onboarding takes a minute or two depending on repo size. Once the status is `active`, PRs are reviewed automatically.

## Configuration

All configuration is through environment variables or a `.env` file. See [`.env.example`](.env.example) for the full list.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_APP_ID` | yes | | GitHub App ID |
| `GITHUB_WEBHOOK_SECRET` | yes | | Webhook secret from app creation |
| `GITHUB_PRIVATE_KEY` | yes* | | PEM contents inline |
| `GITHUB_PRIVATE_KEY_PATH` | yes* | | Path to the `.pem` file |
| `AI_GATEWAY_API_KEY` | yes | | API key for the AI gateway |
| `AI_GATEWAY_BASE_URL` | no | `https://ai-gateway.vercel.sh/v1` | OpenAI-compatible gateway endpoint |
| `PRIMARY_MODEL_ID` | no | `anthropic/claude-sonnet-4-5-20250929` | Model for PR reviews and onboarding |
| `STANDARD_MODEL_ID` | no | `anthropic/claude-sonnet-4-5-20250929` | Model for comment replies |
| `CLASSIFIER_MODEL_ID` | no | `anthropic/claude-haiku-4-5-20251001` | Model for sentiment classification |
| `DATABASE_URL` | no | `postgresql+asyncpg://...localhost:5433/louro` | PostgreSQL connection string |
| `API_KEY` | no | | Protects management endpoints with `X-API-Key` header |

*Provide either `GITHUB_PRIVATE_KEY` (inline PEM) or `GITHUB_PRIVATE_KEY_PATH` (file path), not both.

## Review language

Reviews default to Brazilian Portuguese (pt-BR). Change per org:

```bash
curl -X PUT http://localhost:8000/orgs/my-org/language \
  -H 'Content-Type: application/json' \
  -d '{"language": "en-US"}'
```

Supported: `pt-BR` (default), `en-US`.

## Usage tracking

Louro tracks review counts and active users per org per month, exposed through `/billing` endpoints. This is informational only -- there is no enforcement or gating. Reviews continue regardless of usage numbers. The `over_soft_cap` flag exists so hosting providers or teams can build their own dashboards or alerts on top.

## Known limitations

- **Background task lifecycle:** PR reviews, comment replies, and onboarding run as fire-and-forget `asyncio` tasks. If the process dies mid-task, that work is lost and GitHub won't retry the webhook. A durable task queue would fix this but isn't implemented yet.

## Project structure

```
src/
  main.py              # FastAPI app, routes, lifespan
  config.py            # Settings from environment variables
  models.py            # Domain models (Repository, PullRequest, Review, etc.)
  agent/               # AI agent setup, prompts, tools, rate limiting
  api/                 # REST endpoints (repos, billing, orgs)
  db/                  # SQLAlchemy models and queries
  github/              # GitHub API client, webhook handling, auth
  knowledge/           # pgvector knowledge base per repo
  usecases/            # Core logic (review_pr, handle_comment, onboard_repo)
tests/
  unit/                # No external dependencies needed
  integration/         # Needs PostgreSQL (uses testcontainers)
```

## Development

```
make install     # install all dependencies
make dev         # start dev server with auto-reload
make test-unit   # run unit tests (no database needed)
make test        # run full test suite (needs postgres)
make lint        # run ruff linter
make format      # format code with ruff
make check       # lint + typecheck + format check + unit tests
make db          # start postgres via docker compose
make db-stop     # stop docker compose
make clean       # remove caches
```

API docs at `http://localhost:8000/docs` once the server is running.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[AGPL-3.0](LICENSE)
