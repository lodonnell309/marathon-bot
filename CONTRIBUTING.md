# Contributing to marathon-bot

Thanks for your interest in contributing. This document explains how to set up the project, run tests, and submit changes.

## Setting up the project

1. Fork and clone the repository.
2. Create a virtual environment (recommended) and install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in the required environment variables. For local development you can use SQLite (leave `DATABASE_URL` unset) and add placeholder values for Strava and Telegram if you are only running tests.
4. Run the app locally:

   ```bash
   uvicorn app:app --reload
   ```

## Running tests

Run the test suite with:

```bash
pytest
```

The app uses `TESTING=true` in the test environment to skip ADK Runner and database initialization where not needed. New code that affects existing behavior should include or update tests where appropriate.

## Submitting changes

1. Create a branch from `main` for your change (e.g. `feature/short-description` or `fix/issue-description`).
2. Make your changes and run the tests.
3. Open a pull request against `main`. Describe what you changed and why.
4. Address any review feedback.

We follow the usual GitHub flow: work in a branch, then open a PR for review.

## Code style

Follow the existing style in the codebase. The project uses Python 3.11+ and type hints where applicable. You can use tools like [Black](https://github.com/psf/black) or [Ruff](https://github.com/astral-sh/ruff) for formatting/linting if you add configuration for them.
