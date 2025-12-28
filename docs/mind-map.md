# Mind Map submodule

This repo tracks the forked mind-map project as a submodule and auto-builds its static assets into `static/mind-map`.

## Branch strategy (in the mind-map fork)

- `main`: syncs only from upstream; no custom changes.
- `fengdock`: contains FengDock-specific changes; regularly rebase or merge from `main`.

## Upstream sync (in the mind-map fork)

- Add upstream: `git remote add upstream <upstream-repo-url>`
- Sync `main`: `git fetch upstream && git reset --hard upstream/main`
- Update `fengdock`: `git checkout fengdock && git rebase main` (or merge)

## FengDock automation

- Submodule path: `vendor/mind-map`.
- GitHub Action: `.github/workflows/mind-map-sync.yml`.
- The workflow fetches the `fengdock` branch when it exists, otherwise falls back to `main`.
- Build output is copied from `vendor/mind-map/dist` + `vendor/mind-map/index.html` into `static/mind-map`.
- Pages publish: handled in the `L1nwatch/mind-map` repo workflow.
