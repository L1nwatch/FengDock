# FengDock

Personal portal composed of:

- **FastAPI backend** (`app/`) serving the homepage links API, Loblaws board pages, and background jobs (link health + Loblaws refresh).
- **Static frontend** (`index.html`, `static/`, `tools/`) with the periodic-table home, JSON viewer, and Loblaws board/manager.
- **Caddy reverse proxy** (see `deploy/Caddyfile`) shipping alongside the backend via Docker compose.

Everything is tested and deployed through GitHub Actions → GHCR → SSH redeploy on the VPS.

## Stack

- Python 3.12 managed with [uv](https://github.com/astral-sh/uv)
- FastAPI, SQLAlchemy, and SQLite (`data/db.sqlite3`)
- APScheduler background job verifying link health
- Docker + docker compose with Caddy reverse proxy
- GitHub Actions building/pushing to GHCR and redeploying over SSH
- Cloudflare fronting the VPS with **Full (strict)** TLS

## Development

1. Install dependencies once: `uv sync`
2. Run the API: `uv run uvicorn app.main:app --reload`
3. Visit the API docs at `http://localhost:8000/docs`

### Tests

- Install dependencies first with `uv sync` so `.venv/` is created.
- Run the full FastAPI + Playwright suite from the repo root: `PYTHONPATH=. .venv/bin/pytest` (or equivalently `uv run pytest`).
- Make sure nothing else is bound to `127.0.0.1:8123` before launching the tests—the Playwright fixtures start the app server on that port.

### Development Workflow Notes

- **Use the repo virtualenv**: run tooling as `PYTHONPATH=. .venv/bin/pytest`, `.venv/bin/playwright install`, etc. `uv sync` keeps it up to date and the CI job mirrors the same environment.
- **Frontend cache busting**: whenever `static/**` JS/CSS changes, bump the `?v=` query string in the relevant template under `tools/` so browsers fetch the new asset.
- **Proxy awareness**: new routes or static pages usually need a matching stanza in `deploy/Caddyfile`, plus the runtime Dockerfile must copy any new templates/assets.
- **Tests before push**: `PYTHONPATH=. .venv/bin/pytest` (this runs unit + Playwright UI tests). CI blocks deployments if the suite fails.
- **Private board password**: use environment variable `PRIVATE_PAGE_PASSWORD_HASH` (SHA-256 hex) for `/board/manage`; during local tinkering export it manually, in CI we hash the `PRIVATE_PAGE_PASSWORD` secret.
- **Shared footer**: the JSON viewer and Loblaws pages inject the footer from `static/common/footer.html` via `static/common/footer.js`; reuse that snippet for any new tool pages to keep styling consistent.

Loblaws board specifics:

- `/board` shows read-only cards sorted by active sales first, with duplicates deduplicated by `product_code`.
- `/board/manage` accepts the hashed token (via `?token=` prompt) and exposes add/delete/refresh controls. The frontend carries the token into fetch calls.

To run the stack with Caddy locally:

```bash
cp .env.example .env  # adjust values as needed
GHCR_IMAGE=fengdock-backend:dev docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

SQLite files are stored in `data/` (ignored by git). Background jobs run automatically after the app starts; adjust `LINK_CHECK_INTERVAL_MINUTES` in your `.env` file if needed.

## Production Deployment

1. Create `.env` on the server based on `.env.example`, setting at minimum:
   - `GHCR_IMAGE=ghcr.io/<your-gh-username>/fengdock:latest`
   - `DOMAIN=your.domain`
   - Optional: `CADDY_GLOBAL_OPTIONS="email you@example.com"`
   - Optional: `PRIVATE_PAGE_PASSWORD_HASH=<sha256 hex>` (only needed for manual deployments; the GitHub Action auto-populates it when `PRIVATE_PAGE_PASSWORD` secret is set).
2. Ensure `docker`, `docker compose`, and `git` are installed on the VPS and the repo is cloned in `${DEPLOY_PATH}`.
3. GitHub Actions workflow `.github/workflows/deploy.yml` builds and pushes the image, then SSHs to the VPS, syncs the git repo, and runs:
   ```bash
   git fetch --all --prune
   git reset --hard origin/main
   docker compose pull
   docker compose up -d --remove-orphans
   docker image prune -f
   ```

### GitHub Actions Secrets

Add these secrets at repository level:

- `DEPLOY_HOST` – VPS IP or hostname
- `DEPLOY_PORT` – SSH port (default 22)
- `DEPLOY_USER` – SSH user
- `DEPLOY_PATH` – absolute path of the repo on the server
- `DEPLOY_SSH_KEY` – private key with access to the VPS
- `PRIVATE_PAGE_PASSWORD` – plaintext password used for `/board/manage` (workflow hashes it into `PRIVATE_PAGE_PASSWORD_HASH`).

No extra registry credentials are required; the workflow logs into GHCR with `GITHUB_TOKEN`.

## Cloudflare Configuration

1. Create an **A** record for `DOMAIN` pointing to the VPS public IP.
2. Under *SSL/TLS* settings, select **Full (strict)** so Cloudflare validates Caddy's Let’s Encrypt certificate end-to-end.
3. Optionally enable *Always Use HTTPS* and *Automatic HTTPS Rewrites* for redirects.
4. If you use Cloudflare Zero Trust or firewall rules, allow inbound HTTPS to reach the VPS.

## Caddy & Static Assets

- `deploy/Caddyfile` proxies `/api/*` requests to the FastAPI container (`backend:8000`) and serves `index.html` plus `/static/**` directly.
- Update `DOMAIN` and `CADDY_GLOBAL_OPTIONS` (for contact email) via environment variables.

## Useful Commands

- `uv run python -m compileall app` – quick syntax check
- `docker compose config` – verify compose file rendering
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` – local full stack

Feel free to extend the API by adding routers under `app/routers/` and registering them in `app/main.py`.
