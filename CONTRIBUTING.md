# Contributing to Louro

## Getting started

1. Fork the repo and clone your fork
2. Run `make setup` (installs dependencies and starts PostgreSQL)
3. Copy `.env.example` to `.env` and fill in your credentials
4. Run `make dev` to start the server

If you don't have a GitHub App set up yet, you can still run unit tests with `make test-unit` without any configuration.

## Running tests

```bash
make test-unit   # fast, no database needed
make test        # full suite, needs postgres running (make db)
```

Integration tests use [testcontainers](https://testcontainers.com/) to spin up a PostgreSQL instance automatically. You need Docker running.

## Code style

We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting. Run `make check` before pushing, it runs lint + format check + unit tests.

The config is in `pyproject.toml`. Line length is 120. Target is Python 3.12.

## Submitting changes

1. Create a branch from `main`
2. Make your changes
3. Run `make check` to make sure everything passes
4. Open a pull request against `main`

Keep PRs focused on one thing. If you're fixing a bug and want to refactor something nearby, that's two PRs.

## Reporting bugs

Open a GitHub issue. Include:
- What you expected to happen
- What actually happened
- Steps to reproduce, if possible
- Relevant logs (redact any secrets)

## Adding a new AI provider

The provider abstraction is in `src/agent/factory.py`. Add a new case to the `_build_model_for_id` function using the [agno](https://docs.agno.com) model class for your provider, then add the corresponding settings to `src/config.py`.

## Questions?

Open an issue. There's no mailing list or Discord yet.
