---
name: new-repo
description: Create a new repository in the cvhome-saas GitHub organisation from the orchestrator - a shared library, a new tool, a base image, a Caddy or Go plugin, a docs site, a mirror - scaffolded with the org repo standard (AGENTS.md, worktree/push/design hooks, /go, verify receipt, PR template, labels, QA and plan templates), registered in repos.yaml and .gitignore, cloned beside the others, and wired into the release ring if it should carry the product tag. Use when the user says "create a repo", "we need a new shared lib / tool / image / plugin repo", "split X out of cvhome", or when a plan's "Other repos" section names a repo that does not exist. Also the place that says when NOT to create a repo: a new cvhome service is a module in the monorepo (project-structure references/new-service.md), not a repo.
---

# New repository

## First: is it really a repo?

| Ask | Answer |
|---|---|
| A new backend service, UI, or pod module for cvhome | **Not a repo.** `cvhome` module: `fullstack-task` → project-structure `references/new-service.md` (settings.gradle, common-config, lcl.yml, edge route, services.yaml in the platform, k6 client). |
| A shared Java library only cvhome uses | `cvhome/store-commons/<name>` module, not a repo. |
| A shared library with consumers outside cvhome, a CLI, an image or plugin with its own release, a docs site, an automation repo | **A repo.** Continue. |

## Create it

```bash
cd /Volumes/Disk/IdeaProjects/cvhome-saas
scripts/new-repo.sh <name> --kind <app|infra|tool|image|plugin|docs|ideas|mirror> \
    --usage "<one sentence: what it is for and who consumes it>" [--tag] [--entry "README.md, src/"]
```

`--tag` puts it in the release ring: it receives the product tag `vX.Y.Z` on every release
(`docs/release-plan.md`). Use it for anything the product depends on at a version (a library, an image, a
plugin); leave it off for docs, mirrors and automation.

What the script does: `gh repo create cvhome-saas/<name>` (public by default), copies `templates/repo/`,
fills `AGENTS.md` from the usage line, creates the changelog labels, makes the first commit and pushes
`main`, adds the repo to `repos.yaml` and `.gitignore`. `gh` must be authenticated with permission to create
repos in the org.

## Then, in the same session

1. `cd <name>`: write the real *Build, run and verify* section in `AGENTS.md` and the real gates in
   `scripts/verify.steps.sh`; run `scripts/verify.sh`. Add the minimal real content (a `src/`, a
   `Dockerfile`, a `go.mod`, ...) on a branch and ship it with `/go` — the scaffold commit on `main` is the
   only direct push the repo ever gets.
2. If other repos will consume it, add its contract to the orchestrator: a rule in `scripts/impact.py`
   (which files are its surface, who consumes them, what to ask), a row in
   `org-router/references/cross-repo-contracts.md`, and a section in `references/repo-map.md`.
3. If it publishes an image: mirror it through `public-dkr` (matrix entry) before any consumer pins it;
   consumers pin `X.Y.Z`, never `latest`.
4. Branch protection is not configured anywhere in the org; if you want it, say so and it is one `gh api`
   call per repo — the hooks are what enforce the rules today.
5. Commit `repos.yaml` and `.gitignore` in the orchestrator (`git add repos.yaml .gitignore && git commit
   -m "repos: add <name>"`), and mention the repo in `CLAUDE.md`'s table if it is something agents will
   route to often.

## Renaming, archiving, deleting

Outward-facing and hard to undo: confirm with the person first. Archive with
`gh repo archive cvhome-saas/<name>`, remove it from `repos.yaml`, `.gitignore`, the skills and
`impact.py`, and delete the local checkout. Never delete a repo from here.
