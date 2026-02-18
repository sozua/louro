# Louro

AI code reviewer for GitHub pull requests. Self-hosted, bring your own API key.

Louro watches for new and updated PRs, fetches the diff, runs it through an AI agent, and posts inline comments on specific lines. It also adds a summary to the PR description.

If a developer replies to a review comment disagreeing or explaining a project convention, Louro stores that correction so it doesn't make the same mistake on the next PR.

## Setup

You need a GitHub App, an AI provider API key, and a PostgreSQL database.

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
|-------|-----------|
| Contents | Read |
| Pull requests | Read & Write |
| Metadata | Read |
| Members (org) | Read |

Events to subscribe to:

- Pull request
- Pull request review comment
- Push
- Installation

After creating the app:

1. Copy the **App ID** from the settings page
2. Generate a **private key** (scroll down, click "Generate a private key") and save the `.pem` file
3. Click **Install App** in the sidebar and install it on the repos you want reviewed

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

# Required -- AI provider (pick one)
ANTHROPIC_API_KEY=sk-ant-...        # default provider
# GOOGLE_API_KEY=...                # set MODEL_PROVIDER=gemini
# AWS Bedrock uses the default credential chain; set MODEL_PROVIDER=bedrock
```

### 3. Expose your local server

Louro needs to receive webhooks from GitHub, so your local server needs a public URL:

```bash
ngrok http 8000
```

Copy the `https://...` URL and set it as the **Webhook URL** in your GitHub App settings, appending `/webhooks/github`:

```
https://abc123.ngrok-free.app/webhooks/github
```

### 4. Start the server

```bash
make dev
```

Open a PR on an installed repo. Louro will post a review once the agent finishes (usually under a minute, depending on diff size and model).

You can check the server is running with `make verify` or by hitting `http://localhost:8000/health`.

## Running with Docker

If you'd rather not install Python locally:

```bash
cp .env.example .env
# fill in .env
docker compose up
```

This starts both the app and PostgreSQL. The app listens on port 8000.

## Activating a repository

When you install the GitHub App on a repo, it gets registered with status `pending`. Louro won't review PRs until you activate it:

```bash
# List registered repos
curl http://localhost:8000/repos

# Activate (triggers onboarding -- Louro reads the codebase to learn its conventions)
curl -X POST http://localhost:8000/repos/owner/repo/activate

# Deactivate
curl -X POST http://localhost:8000/repos/owner/repo/deactivate
```

Onboarding takes a minute or two depending on repo size. Once the status changes to `active`, PRs are reviewed automatically.

## Configuration

All configuration is through environment variables or a `.env` file. See [`.env.example`](.env.example) for the full list.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_APP_ID` | yes | | GitHub App ID |
| `GITHUB_WEBHOOK_SECRET` | yes | | Webhook secret from app creation |
| `GITHUB_PRIVATE_KEY` | yes* | | PEM contents inline |
| `GITHUB_PRIVATE_KEY_PATH` | yes* | | Path to the `.pem` file |
| `ANTHROPIC_API_KEY` | depends | | Required when `MODEL_PROVIDER=anthropic` |
| `GOOGLE_API_KEY` | depends | | Required when `MODEL_PROVIDER=gemini` |
| `MODEL_PROVIDER` | no | `anthropic` | `anthropic`, `bedrock`, or `gemini` |
| `PRIMARY_MODEL_ID` | no | `claude-sonnet-4-5-20250929` | Model for PR reviews and onboarding |
| `STANDARD_MODEL_ID` | no | `claude-sonnet-4-5-20250929` | Model for comment replies |
| `CLASSIFIER_MODEL_ID` | no | `claude-haiku-4-5-20251001` | Model for sentiment classification |
| `DATABASE_URL` | no | `postgresql+asyncpg://...localhost:5433/louro` | PostgreSQL connection string |
| `API_KEY` | no | | Protects management endpoints with `X-API-Key` header |

*Provide either `GITHUB_PRIVATE_KEY` (inline PEM) or `GITHUB_PRIVATE_KEY_PATH` (file path), not both.

## Review language

Reviews default to Brazilian Portuguese (pt-BR). You can change the language per organization:

```bash
curl -X PUT http://localhost:8000/orgs/my-org/language \
  -H 'Content-Type: application/json' \
  -d '{"language": "en-US"}'
```

Supported: `pt-BR` (default), `en-US`.

## How it works

1. GitHub sends a webhook when a PR is opened or updated
2. Louro verifies the signature and fetches the diff via the GitHub API
3. An AI agent ([agno](https://docs.agno.com)) analyzes the diff. It can also call tools to read full files from the repo when it needs more context.
4. The agent posts inline comments using [Conventional Comments](https://conventionalcomments.org/) labels and writes a summary to the PR description
5. When someone replies to a review comment, a classifier scores the sentiment and a second agent responds
6. If the reply corrects Louro about a project convention, that gets saved to the knowledge base

Each repo has its own knowledge base (PostgreSQL + pgvector), built during onboarding. The onboarding agent reads the file tree, config files, recent commits, and recent PRs to understand how the codebase is structured and what patterns the team prefers.

## Usage tracking

Louro tracks review counts and active users per organization per month. This data is exposed through the `/billing` API endpoints and is purely informational — there is no enforcement or gating. Reviews continue normally regardless of usage numbers.

The tracked metrics include active users (PR authors whose pushes trigger reviews), review counts, and a configurable soft cap per seat. The `over_soft_cap` flag is set when the review count exceeds the cap but has no effect on behavior. This is designed so that hosting providers or teams can build their own usage dashboards or alerts on top of the data.

## Known limitations

- **Background task lifecycle:** PR reviews, comment replies, and repository onboarding run as fire-and-forget `asyncio` tasks. If the process is stopped (e.g. deploy, crash) while a task is in flight, that work is lost and GitHub won't retry the webhook. A durable task queue (e.g. Redis, SQS) would fix this, but isn't implemented yet.

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

API docs are at `http://localhost:8000/docs` once the server is running.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[AGPL-3.0](LICENSE)
