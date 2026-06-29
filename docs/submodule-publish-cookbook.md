# Submodule Publish Cookbook

For changes inside `vendor/fire`, `vendor/TriggerToDo`, or another submodule.

## Publish Submodule

Push the submodule `main` before updating `FengDock/main`. Stop if the fast-forward merge fails.

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
git status -sb
```

## Publish FengDock

```sh
cd /Users/watch/Desktop/Code/FengDock
git status -sb
git diff --submodule
git add vendor/<submodule>
git commit -m "Update <submodule> submodule"
git push origin main
git ls-files -s vendor/<submodule>
git ls-remote origin refs/heads/main
git status -sb
```

Both repos should be clean before saying the push is complete.
