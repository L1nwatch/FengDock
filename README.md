# FengDock

FastAPI backend and static homepage for FengDock. The service exposes a REST API for managing homepage links, stores data in SQLite, and schedules background link health checks with APScheduler. A Docker-based deployment bundles the API with a Caddy reverse proxy, with continuous delivery via GitHub Actions and GHCR.

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

To run the stack with Caddy locally:

```bash
cp .env.example .env  # adjust values as needed
GHCR_IMAGE=fengdock-backend:dev docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

SQLite files are stored in `data/` (ignored by git). Background jobs run automatically after the app starts; adjust `LINK_CHECK_INTERVAL_MINUTES` in your `.env` file if needed.

## Production Deployment

1. Create `.env` on the server based on `.env.example`, setting at minimum:
   - `GHCR_IMAGE=ghcr.io/<your-gh-username>/fengdock:latest`
   - `DOMAIN=your.domain` (must match the Cloudflare DNS record)
   - Optional: `CADDY_GLOBAL_OPTIONS="email you@example.com"`
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
