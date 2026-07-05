# FengDock Cookbook

Concise index for common development and operations references.

## Start Here

- [README.md](README.md) - project overview, local setup, tests, deployment, and useful commands.
- [.github/workflows/deploy.yml](.github/workflows/deploy.yml) - CI build, asset generation, image publish, and VPS deploy flow.
- [deploy/Caddyfile](deploy/Caddyfile) - production route and reverse-proxy rules.
- [Dockerfile](Dockerfile) - runtime image build and bundled frontend assets.

## Submodules

- [docs/submodule-publish-cookbook.md](docs/submodule-publish-cookbook.md) - publish changes from a submodule, then update FengDock.
- [docs/mind-map.md](docs/mind-map.md) - mind-map submodule branch strategy and static asset build notes.
- [vendor/celpip-exam-simulation/COOKBOOK.md](vendor/celpip-exam-simulation/COOKBOOK.md) - CELPIP app workflow, tests, and public preview build.
- [.gitmodules](.gitmodules) - tracked submodule paths, URLs, and branches.

## Tool Scripts

- [scripts/run_servers.py](scripts/run_servers.py) - starts FengDock, TriggerToDo, Codex proxy, and Fire in the container.
- [deploy/codex_proxy_with_interception.py](deploy/codex_proxy_with_interception.py) - Codex proxy with JSONL interaction logging.
- [tools/json-viewer.html](tools/json-viewer.html) - standalone JSON viewer served at `/tools/json-viewer`.

## Tests

- [tests/](tests) - API and Playwright UI tests.
- Run full suite: `uv run python -m pytest`.
