---
name: cross-repo-review
description: The orchestrator as reviewer. Reviews a change in ANY cvhome-saas repo (a working tree, a branch, a PR number, or a merged commit) for what it can break in the OTHER repos and in production - a port, service, env var, secret, route, image pin, SLO, hostname, schema or CLI flag that another repo copies or depends on. Use before opening a PR from the orchestrator, when asked "review this", "will this break infra/load-testing/prod", "is it safe to merge", to review a PR link in cvhome, cvhome-platform, lcl, load-testing, saas-gateway, caddy-domainlookup, aws-otel-collector, or periodically to audit drift across all repos. Runs scripts/impact.py and scripts/contract-check.py, then a semantic review per consumer, and produces a verdict with per-repo follow-ups; can post it as a PR comment.
---

# Cross-repo review

A PR is reviewed inside one repo, but the failure shows up in another: cvhome changes a port and the
platform's ECS target group still points at the old one; a Caddyfile gains a directive the pinned
saas-gateway build does not have; a k6 client encodes a request shape the controller no longer accepts;
the collector drops a metric a dashboard alarms on. This skill is the review that looks *across*.

Two tools do the mechanical half; the rest is reading the consumers the tools name.

| Tool | What it answers |
|---|---|
| `scripts/impact.py <repo> [--head <branch> \| --pr N \| --files …]` | Which changed files are contract surfaces, who consumes them in other repos, which checks to run, which questions to answer |
| `scripts/contract-check.py [--<repo> <path>]` | Do all the copies of each contract agree *right now*, with the proposed change substituted in (`--cvhome <worktree>` etc.) |

The rules in both scripts are the executable form of `org-router/references/cross-repo-contracts.md`.
If you find a coupling neither knows about, add it to all three.

## Procedure

1. **Get the change in a path.**
   - Working tree / branch in a checkout: use it directly (`cvhome/.claude/worktrees/<name>` for cvhome).
   - A PR: `gh pr checkout N` inside a throwaway worktree so `main` stays clean:
     ```bash
     cd /Volumes/Disk/IdeaProjects/cvhome-saas
     git -C <repo> fetch origin pull/N/head:review/pr-N
     git -C <repo> worktree add ../.wt/<repo>-pr-N review/pr-N      # cvhome: .claude/worktrees/review-pr-N
     ```
   - A merged commit: `--base <sha>^ --head <sha>`.
   Make sure every *other* repo is current first: `scripts/clone.sh` (fetch + behind/ahead report), and
   fast-forward clean `main`s. Reviewing against a stale consumer produces false confidence.

2. **Map the impact.** `scripts/impact.py <repo> --head <branch>` (or `--pr N`). Read the output as the
   review checklist: one section per touched contract surface with its consumers and questions. Nothing
   matched → repo-local review only; say so and stop the cross-repo part.

3. **Run the contract check with the change substituted in.**
   `scripts/contract-check.py --<repo> <path-to-change>` (all checks; `--only` with the list impact.py
   printed is the minimum). Compare with a baseline run without the override: a WARN that already
   existed on `main` is pre-existing drift, not this change's fault, but it is still reported.

4. **Read the consumers.** For each consumer impact.py named, open the file and answer the question with
   evidence (path:line), not by assumption. Typical reads:
   - `cvhome-platform/services.yaml` and `modules/*/main.tf` for env/secret/port/edge.
   - `cvhome/store-pod/spg/Caddyfile` and `GatewayRouteLocatorImpl.java` for routes.
   - `load-testing/k6/lib/clients/<svc>.js` and `docs/coverage.md` for request shapes.
   - `saas-gateway/Dockerfile` and the pinned sha's tree (`git -C saas-gateway show <sha>:Dockerfile`) for
     Caddy directives.
   - `aws-otel-collector/otel-config.yaml` for metric filters; `cvhome/extra/monitoring/grafana/dashboards`
     for who uses them.
   - `cvhome-platform/flavours.yaml` for sizes when JVM/pool settings move.
   Also ask the production questions the scripts cannot: rolling deploy compatibility (old image + new DDL
   for a few minutes), mutable `:latest` images, secrets that need rotation, data migrations, and whether
   the change lands in the right order across repos (producers before consumers, § org-router step 3).

5. **Verdict.** One of:
   - **SAFE** — no cross-repo effect, or every copy already updated in linked PRs.
   - **NEEDS FOLLOW-UP** — safe to merge *this* repo, but repo X must change before/after (name the file,
     the branch to use, the order). Typical: app PR first, platform `services.yaml` next, k6 client after.
   - **BLOCKS** — merging this alone breaks a consumer in production or CI (drift check will fail; env var
     unset on Fargate; route unreachable; pinned image lacks a directive). Say exactly what breaks and how.
   Include the contract-check lines that changed status, and pre-existing drift separately.

6. **Deliver.** Print the report (template below). If asked, post it:
   `gh pr comment N -R cvhome-saas/<repo> --body-file <report.md>`. Then clean the review worktree:
   `git -C <repo> worktree remove ../.wt/<repo>-pr-N && git -C <repo> branch -D review/pr-N`.
   Follow-ups the user approves become work items for `cross-repo-change`.

## Report template

```
## Cross-repo review — cvhome-saas/<repo> <branch|PR #N>

**Verdict: SAFE | NEEDS FOLLOW-UP | BLOCKS**

### Contract surfaces touched
- <file> → consumers: …

### Findings
1. **BLOCKS** <what breaks in prod/CI> — evidence `<repo>/<path>:<line>` … Fix: <repo>, <file>, <change>.
2. **FOLLOW-UP** …
3. **NOTE** (pre-existing drift, not this change) …

### contract-check.py
<lines whose status differs from main; then "pre-existing: …">

### Merge order
1. cvhome-saas/<repo>#N (this)  2. cvhome-saas/<other> <branch> (needed before deploy)  3. …
```

## Standing audit

Run `scripts/contract-check.py` with no overrides on a schedule or whenever `scripts/status.sh` shows a
repo moved: it is the same review applied to what is already merged. Current known WARNs live in
`org-router/references/known-drift.md`; a new WARN or any FAIL is a finding to route.
