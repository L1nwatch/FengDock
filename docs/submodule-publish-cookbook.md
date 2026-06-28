# Submodule Publish Cookbook

Use this when a change is made inside `vendor/fire` and the parent `FengDock` repo must point at that new submodule commit.

## 1. Commit and push the submodule first

```sh
cd /Users/watch/Desktop/Code/FengDock/vendor/fire
git status -sb
git switch -c codex/<short-change-name>
git add <changed-files>
git commit -m "<short commit message>"
git push -u origin codex/<short-change-name>
```

Do not update the parent repo until the submodule commit exists on GitHub.

## 2. Verify the submodule branch is online

```sh
git ls-remote origin refs/heads/codex/<short-change-name>
```

The output hash must match the local submodule commit:

```sh
git rev-parse HEAD
```

## 3. Commit and push the parent submodule pointer

```sh
cd /Users/watch/Desktop/Code/FengDock
git status -sb
git diff --submodule
git switch -c codex/update-fire-submodule
git add vendor/fire
git commit -m "Update fire submodule"
git push -u origin codex/update-fire-submodule
```

`git diff --submodule` should show the parent pointer moving from the old `vendor/fire` commit to the new pushed submodule commit.

## 4. Explain where to look on GitHub

If the change was pushed to a feature branch, it will not appear on GitHub's default `main` view until the branch is merged.

Share both links:

- `https://github.com/L1nwatch/fire/tree/<submodule-branch>`
- `https://github.com/L1nwatch/FengDock/tree/<parent-branch>`

## Common checks

```sh
git -C /Users/watch/Desktop/Code/FengDock/vendor/fire status -sb
git -C /Users/watch/Desktop/Code/FengDock status -sb
git -C /Users/watch/Desktop/Code/FengDock/vendor/fire log --oneline --decorate -3
git -C /Users/watch/Desktop/Code/FengDock log --oneline --decorate -3
```

Both repos should show clean working trees before calling the publish complete.
