# Submodule Publish Cookbook

Use this when a change is made inside a submodule, such as `vendor/fire` or `vendor/TriggerToDo`, and the parent `FengDock` repo must point at that new submodule commit.

Important: if the user expects to see the change on GitHub's default view or in a deployment that builds from `main`, publishing only a `codex/...` branch is not enough. The submodule's `main` branch and the parent `FengDock` `main` branch must both be advanced and pushed.

## 1. Commit and push the submodule first

```sh
cd /Users/watch/Desktop/Code/FengDock/vendor/<submodule-name>
git status -sb
git switch -c codex/<short-change-name>
git add <changed-files>
git commit -m "<short commit message>"
git push -u origin codex/<short-change-name>
```

Do not update the parent repo until the submodule commit exists on GitHub.

## 2. If the change should be visible on `main`, fast-forward submodule `main`

Use this when the user says "push" and expects the live/default branch to include the change.

```sh
cd /Users/watch/Desktop/Code/FengDock/vendor/<submodule-name>
git switch main
git pull --ff-only origin main
git merge --ff-only codex/<short-change-name>
git push origin main
```

If the fast-forward merge fails, stop and explain the conflict instead of rewriting history.

## 3. Verify the submodule commit is online

```sh
git ls-remote origin refs/heads/codex/<short-change-name>
git ls-remote origin refs/heads/main
```

For a `main` publish, `refs/heads/main` must match the local submodule commit:

```sh
git rev-parse HEAD
```

## 4. Commit and push the parent submodule pointer

```sh
cd /Users/watch/Desktop/Code/FengDock
git status -sb
git diff --submodule
git switch -c codex/update-<submodule-name>-submodule
git add vendor/<submodule-name>
git commit -m "Update <submodule-name> submodule"
git push -u origin codex/update-<submodule-name>-submodule
```

`git diff --submodule` should show the parent pointer moving from the old submodule commit to the new pushed submodule commit.

## 5. If the parent should be visible on `main`, fast-forward `FengDock/main`

Use this after the submodule `main` branch is already pushed.

```sh
cd /Users/watch/Desktop/Code/FengDock
git switch main
git pull --ff-only origin main
git merge --ff-only codex/update-<submodule-name>-submodule
git push origin main
```

Verify the parent default branch now points at the expected commit:

```sh
git ls-remote origin refs/heads/main
git ls-files -s vendor/<submodule-name>
```

## 6. Explain where to look on GitHub

If the change was pushed to a feature branch, it will not appear on GitHub's default `main` view until the branch is merged.

If `main` was pushed, share the `main` links. If only feature branches were pushed, share both branch links:

- `https://github.com/L1nwatch/<submodule-repo>/tree/<submodule-branch-or-main>`
- `https://github.com/L1nwatch/FengDock/tree/<parent-branch>`

## Common checks

```sh
git -C /Users/watch/Desktop/Code/FengDock/vendor/fire status -sb
git -C /Users/watch/Desktop/Code/FengDock/vendor/TriggerToDo status -sb
git -C /Users/watch/Desktop/Code/FengDock status -sb
git -C /Users/watch/Desktop/Code/FengDock/vendor/fire log --oneline --decorate -3
git -C /Users/watch/Desktop/Code/FengDock/vendor/TriggerToDo log --oneline --decorate -3
git -C /Users/watch/Desktop/Code/FengDock log --oneline --decorate -3
```

The changed submodule and the parent repo should show clean working trees before calling the publish complete.
