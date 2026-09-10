---
name: repo-standard
description: The one working architecture every cvhome-saas repo follows, learned from cvhome and enforced by the orchestrator - CLAUDE.md as a one-line import of AGENTS.md, a fresh git worktree per change cut from origin/main (hook-enforced), a plan written as phases that ship as one PR with one commit per phase, a verify script that writes a push receipt the push hooks demand, /go and /reset commands, the PR template and changelog labels, a QA file per area with [verified] tags, a design record before any new screen, versions only by orchestrator tags. Use when creating or auditing a repo's CLAUDE.md/AGENTS.md, when a repo lacks hooks or commands, when asked "make repo X follow the same conventions", "add CLAUDE.md to all repos", "why is there no worktree guard here", or before the first change in a repo that has no AGENTS.md. Covers templates/repo, scripts/standard-check.py, scripts/standard-apply.sh and how to roll the standard onto an existing repo without losing its own rules.
---

# The cvhome-saas repo standard

Every repo works the same way so the orchestrator can move between them without relearning. The
canonical files are `templates/repo/` in the orchestrator; `scripts/standard-check.py` audits every
checkout against them; `scripts/standard-apply.sh <repo>` copies what is missing onto a branch.

## The architecture (what cvhome does, generalised)

| Piece | File(s) | What it enforces |
|---|---|---|
| One rulebook | `CLAUDE.md` = `@AGENTS.md`; `AGENTS.md` is the text | Claude Code auto-loads `CLAUDE.md`; other agents read `AGENTS.md`; there is one document, not two that drift |
| Worktree per change | `.claude/hooks/worktree-guard.mjs` + `.claude/settings.json` | Any Write/Edit inside the primary checkout is refused; work happens in `.claude/worktrees/<type>-<name>` on branch `<type>/<name>` cut `--no-track` from `origin/main`. Plans (`.agents/plans`, `.claude/plans`), hooks and settings stay writable. `ALLOW_MAIN_WRITES=1` is the person's escape hatch |
| Plan = one PR, phase = one commit | `.agents/plans/<name>.md` (skeleton in `.agents/plans/README.md`) | Context → why → `## Phase N — <area>` → other repos → deviations → verification. One plan, one worktree, one branch, one PR; each phase is a commit on it, easiest first, revertable alone |
| Verify before push | `scripts/verify.sh` + `scripts/verify.steps.sh` → receipt `<git-dir>/verified` | Runs exactly what CI runs; the receipt is a digest of HEAD plus uncommitted changes. `.githooks/pre-push` and `.claude/hooks/push-guard.mjs` refuse a push without a matching receipt, a push to `main`, or `--no-verify`. `SKIP_VERIFY=1` is the person's |
| Ship / reset | `.claude/commands/go.md`, `reset.md` | `/go`: commit → verify → push `-u origin HEAD` → `gh pr create` with the template and a label. `/reset`: back to clean `main`, never discarding work unasked |
| PR shape | `.github/PULL_REQUEST_TEMPLATE.md`, `.github/release.yml`, labels | *Why / What / not obvious / Deviations / Verification*; labels `type/*`, `warn/*`, `ignore-changelog` feed both the release notes and the orchestrator's version bump |
| QA travels with the code | `qa/<area>-qa.md` (skeleton `qa/README.md`) | A user-visible behaviour is done when its case exists, tagged `[verified]` / `[not verified]`; sections `REG` and `99` for regressions and known gaps |
| Design before screen | `.agents/designs/<slug>.md` + `.claude/hooks/design-guard.mjs` (the hook ships everywhere and is a no-op without page files; the designs dir only where a UI lives) | A new Angular feature component or Next.js `page.tsx` is refused until a record with the design-canvas URL and `approved: true` exists |
| Versions | none in files | `vX.Y.Z` tags are cut by the orchestrator's `Release` workflow; no version file, no manual tag |

## Rolling it onto an existing repo

```bash
scripts/standard-check.py                 # who is missing what; WARN = present but stale/unstated
scripts/standard-apply.sh <repo>          # branch chore/repo-standard, copies only what is absent
```

Then, in the repo's branch (cvhome: its worktree):

1. **AGENTS.md exists already** (`cvhome`, `lcl`, `load-testing`): keep every repo-specific rule. Add the
   *Working conventions (org standard)* section from `templates/repo/AGENTS.md`, reconciled with what is
   there (cvhome already states most of it; add the design gate and the phase rule — one PR, one commit per phase). Never delete a rule
   the repo authored; if one contradicts the standard, say so in the PR and keep the repo's rule until the
   owner decides.
2. **Only CLAUDE.md exists** (`cvhome-platform`): rename it to `AGENTS.md`, fix its stale status claims
   while there, add the conventions section, and write the one-line `CLAUDE.md`.
3. **Neither exists**: the template `AGENTS.md` was filled from `repos.yaml`; write the *Build, run and
   verify* section from the repo's real commands.
4. `scripts/verify.steps.sh`: the real gates, identical to `.github/workflows/*`. An image repo:
   `docker build .`; Go: `go build ./... && go vet ./...`; npm: `npm run check && npm test`; Terraform:
   fmt/validate/tflint/drift; docs: `npm run docs:build`; a Markdown-only repo keeps `git diff --check`.
5. `scripts/verify.sh`, `/go`, open the PR titled `chore: adopt the cvhome-saas repo standard`, label
   `type/chore`. One PR per repo; the orchestrator runs them in parallel across repos.

## Rules for the standard itself

- The templates are copies of cvhome's files with only names generalised (`scripts/verify.sh`, receipt
  `verified`, `ALLOW_MAIN_WRITES`). Improve a hook in cvhome first, then re-copy; `standard-check.py`
  reports hooks that drifted from the template.
- `standard-check.py` runs in the orchestrator's nightly CI beside the contract check; a FAIL there is a
  repo missing a required file.
- A new repo gets all of it from `scripts/new-repo.sh` (the `new-repo` skill).
