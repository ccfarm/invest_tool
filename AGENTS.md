# Repository Guidelines

## Project Structure & Module Organization

- `frontend/`: Vue 3 + Vite app. Source in `src/`, assets in `public/`, build output in `frontend/dist/`.
- `backend/`: FastAPI service in `app/`, SQLite data in `backend/data/`, pytest tests in `tests/`.
- `design/` and `docs/`: static design mockups, PRD, implementation plan, and screenshots.
- `scripts/`, `start.sh`, and `Dockerfile`: deployment, smoke testing, and local orchestration.

## Build, Test, and Development Commands

Use `./start.sh` to install dependencies, build the frontend, and serve the app at `http://localhost:8000`.

For backend development:

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

For frontend development:

```bash
cd frontend
npm install
npm run dev
```

Verification commands:

- `cd backend && python -m pytest`: run the backend test suite.
- `cd frontend && npm run lint && npm run build`: lint and production-build the frontend.
- `./scripts/smoke_test.sh`: start the server and verify health, search, page, and SPA fallback.
- `docker build -t invest-tools . && docker run -p 8000:8000 invest-tools`: container build and run.

## Coding Style & Naming Conventions

Use 4-space indentation, type hints, and lines under 100 characters in Python; run `backend/.venv/bin/ruff check backend` before a PR.

In Vue/JavaScript, use `<script setup>`, PascalCase component/view files such as `ResultsView.vue`, and camelCase functions and variables. Run `npm run lint`; do not commit generated `frontend/dist/`.

Keep edits scoped to existing module boundaries. Update `README.md` when user-facing behavior or configuration changes.

## Testing Guidelines

Use pytest with FastAPI `TestClient`. `backend/tests/conftest.py` uses a temporary SQLite database and disables scheduled crawler/microcap tasks so tests never hit the network.

Name tests `test_<behavior>` or `test_<function>_<scenario>` (`test_search_pagination`, `test_old_record_stale`). No coverage percentage is required; run the full suite before merging.

## Commit & Pull Request Guidelines

Git history currently contains only the initial `init` commit. Use clear imperative summaries such as `feat: add stock search` or `fix: reuse same-day microcap results`.

For PRs, describe the behavior change, list verification commands, link related issues, and add screenshots for UI changes. Keep PRs focused and free of unrelated refactors.

## Security & Configuration

Configure credentials and runtime behavior through environment variables documented in `README.md`, including `AUTH_USERNAME`, `AUTH_PASSWORD`, `DB_PATH`, `TRACK_STOCKS`, and the scheduler toggles. Never commit real credentials or production data. In tests, leave the `conftest.py` scheduler overrides in place to keep the suite hermetic.
