# Submodule Publish Cookbook

Use this for changes inside `vendor/fire`, `vendor/TriggerToDo`, or another submodule.

Rule: if the change must appear on GitHub/default deploys, push the submodule `main` first, then update and push `FengDock/main`.

## Publish Submodule

```sh
cd /Users/watch/Desktop/Code/FengDock/vendor/<submodule>
git status -sb
git switch -c codex/<change-name>
git add <changed-files>
git commit -m "<message>"
git push -u origin codex/<change-name>

git switch main
git pull --ff-only origin main
git merge --ff-only codex/<change-name>
git push origin main
git ls-remote origin refs/heads/main
```

Stop if `git merge --ff-only` fails.

## Publish FengDock Pointer

```sh
cd /Users/watch/Desktop/Code/FengDock
git status -sb
git diff --submodule
git add vendor/<submodule>
git commit -m "Update <submodule> submodule"
git push origin main
git ls-files -s vendor/<submodule>
git ls-remote origin refs/heads/main
```

## Final Check

```sh
git -C /Users/watch/Desktop/Code/FengDock/vendor/<submodule> status -sb
git -C /Users/watch/Desktop/Code/FengDock status -sb
```

Both repos should be clean before saying the push is complete.
