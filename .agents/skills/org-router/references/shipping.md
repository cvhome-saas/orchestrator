# Shipping from the orchestrator — per-repo recipe

All repos: `main` is the integration branch, changes land by PR, `gh` is authenticated for
`github.com/cvhome-saas`. Commit trailer on every commit:
`Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` (plus the session link when the harness gives one).
Never `--no-verify`, never `SKIP_VERIFY=1`, never push to `main`, never merge a PR unless told to.

## 0. Make sure the checkout exists and is current

```bash
cd /Volumes/Disk/IdeaProjects/cvhome-saas
scripts/clone.sh <repo>            # clones from repos.yaml if missing, otherwise fetches and prints behind/ahead
```

If `behind > 0` on `main`, fast-forward before cutting a branch: `git -C <repo> pull --ff-only`. If the
checkout is dirty on `main` (cvhome often has untracked plans), leave those files alone and say so.

## 1. Branch per repo

| Repo | How to start | Why |
|---|---|---|
| `cvhome` | `git -C cvhome fetch origin && git -C cvhome worktree add --no-track cvhome/.claude/worktrees/<type>-<name> -b <type>/<name> origin/main`; then every path is `cvhome/.claude/worktrees/<type>-<name>/...` | hook-enforced; the primary checkout stays on clean `main` |
| `cvhome-platform`, `lcl`, `load-testing`, `e2e-testing`, `saas-gateway`, `caddy-domainlookup`, `certmagic-s3`, `aws-otel-collector`, `public-dkr`, `assets`, `cvhome-saas.github.io`, `dot-github`, `ideation` | `git -C <repo> switch -c <type>/<name> origin/main` (a worktree is fine too: `git -C <repo> worktree add ../.wt/<repo>-<name> -b <type>/<name> origin/main` — keep it outside the checkout) | no worktree rule, but a push to `main` in the image repos publishes an image |

`<type>` ∈ `feat|fix|docs|chore|refactor|test`; `<name>` kebab-case; **use the same `<type>/<name>` in every
repo one change touches** — `cvhome-platform`'s drift check compares against the app branch of the same name.

## 2. Gates before push (what each repo's CI runs)

| Repo | Run |
|---|---|
| `cvhome` | `extra/scripts/verify-before-push.sh` from the worktree (checkstyle, build, unit + integration tests, coverage floors, both frontends' lint/tests; writes the push receipt). Plus the change exercised on `lcl start -d --stack <name>` |
| `cvhome-platform` | `terraform fmt -recursive -check`, `terraform validate` per root/module (`-backend=false`), `tflint --recursive`, `python3 scripts/check-catalog-drift.py`; `cfn-lint` + `cfn-guard` if the bootstrap changed |
| `lcl` | `npm ci && npm run check && npm test && npm pack --dry-run` |
| `load-testing` | `npm test` (lint stack + `make inspect` + archives); `make selftest` against a live stack for client changes |
| `saas-gateway` | `docker build .` succeeds |
| `caddy-domainlookup`, `certmagic-s3` | `go build ./... && go vet ./...` (`go test ./...` in certmagic-s3) |
| `e2e-testing` | `npx playwright test` against a running stack (`lcl start -d` in cvhome) |
| `public-dkr` | `actionlint` on the workflow; the image:tag exists on its source registry (`docker manifest inspect`) |
| `assets` | run `fast-run.sh` on a clean Docker host; `docker compose config` on its compose file |
| `dot-github` | Markdown renders; links resolve |
| `aws-otel-collector` | `docker build .`; collector config validated with `otelcol validate --config otel-config.yaml` if available |
| `cvhome-saas.github.io` | `npm ci && npm run docs:build` |
| `ideation` | none |
| `shopizer` | never edited |

## 2b. Cross-repo review before the PR

```bash
scripts/impact.py <repo> --head <type>/<name>                 # which other repos this touches
scripts/contract-check.py --<repo> <path-to-branch-checkout>  # do the copies still agree with the change in
```

A BLOCKS finding means the PR must not be opened alone: open the sibling PR(s) first or in the same
batch, and link them. NEEDS FOLLOW-UP goes into the PR body under *Deviations* with the repo and file.
Details: the `cross-repo-review` skill.

## 3. Commit, push, PR

```bash
git -C <dir> add <paths>                       # by path; no blanket -A when untracked noise is present
git -C <dir> commit -m "<type|area>: <what changed>" -m "<why, if not obvious>" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git -C <dir> push -u origin HEAD
gh pr create -R cvhome-saas/<repo> --base main --head <type>/<name> --title "<type|area>: <what changed>" --body-file <body.md> [--label type/...]
```

PR body: `cvhome` has `.github/PULL_REQUEST_TEMPLATE.md` (*Why → What → The parts that are not obvious →
Deviations → Verification*, delete untouched checklist rows) and changelog labels `type/enhancement|bug|
documentation|test|chore|dependency-upgrade`, `warn/*`, `ignore-changelog`; an unlabelled PR lands in "Other
Changes". The other repos have no template: use the same five headings, no label. In *Verification* list
exactly what ran; never tick a gate that did not run in this session.

For a multi-repo change, each PR body links the sibling PRs ("Pairs with cvhome-saas/cvhome#NNN; land that
first") and states the merge order.

## 4. After the PR

Report the URL. Do not merge. When the user says it merged: `cvhome` → `lcl stop --stack <name>`,
`git -C cvhome worktree remove .claude/worktrees/<type>-<name>`, `git -C cvhome branch -d <type>/<name>`;
others → `git -C <repo> switch main && git -C <repo> pull --ff-only && git -C <repo> branch -d <type>/<name>`.
Image repos: remind about the pin bump / forced deployment that follows.
