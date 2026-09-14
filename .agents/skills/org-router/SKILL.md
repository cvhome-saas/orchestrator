---
name: org-router
description: The cvhome-saas orchestrator's entry point - routes any task to the right repo(s) and skill, and owns everything no single repo can. Use FIRST for every task started from the org root before opening files. Covers the map of the organisation (cvhome full-stack app, cvhome-platform infra, lcl, load-testing, e2e-testing, saas-gateway + caddy-domainlookup + certmagic-s3 + aws-otel-collector + public-dkr images, docs site, assets, ideation) and where a fact lives versus where it is copied. Trigger on "add an endpoint / page / service / pod module", "change a port / env / route / secret", "deploy / release / promote / roll back / cut a version", "why is dev or prod failing", "add a k6 script / e2e test", "lcl won't start", "update the docs / site / profile", "new feature idea", "create a new repo / shared lib / tool", "make repo X follow the conventions / add CLAUDE.md", "review this PR / will this break infra or load-testing", "QA this", "design a new screen", "which repo owns X", "is repo Y still used", "what is the image chain for spg", and anything ambiguous between full-stack, infra, tools and docs. Classifies the ask, ensures the checkouts, splits multi-repo work into one work item per repo, hands off to fullstack-task / infra-task / tools-task / docs-task / cross-repo-change / cross-repo-review / new-repo / repo-standard, and applies the org-wide gates (worktree per change, a plan is one PR with one commit per phase, verify receipt, QA file, design record, release by tag only).
---

# cvhome-saas org router

This directory is the **org checkout**: nine sibling git repos, each with its own rules. Nothing here is
a Gradle module or a Terraform root; the org repo tracks only `repos.yaml`, the skills, `scripts/` and this
guidance. **Every real change lands in exactly one sub-repo per commit**, under that repo's own conventions.

## What the orchestrator owns (no single repo can)

| Duty | How | Where |
|---|---|---|
| The checkouts: clone, fetch, know what is behind | `scripts/clone.sh`, `scripts/status.sh`, `repos.yaml` | Step 0 |
| Routing and work division across repos, producers before consumers | this skill, `cross-repo-change` | Steps 1–4 |
| The cross-repo review: what a change in one repo breaks in another | `cross-repo-review`, `scripts/impact.py`, `scripts/contract-check.py` | Reviewer mode |
| One working architecture in every repo (AGENTS.md, worktree, a plan is one PR with one commit per phase, verify receipt, QA file, design record) | `repo-standard`, `templates/repo/`, `scripts/standard-check.py` (nightly), `scripts/standard-apply.sh` | |
| New repositories in the org, wired into the manifest and the release ring | `new-repo`, `scripts/new-repo.sh` | |
| Releases: one version, every repo tagged, a manifest — compatibility only, no deploy | `docs/releasing.md`, `Release` workflow, `scripts/release.py` | never in a sub-repo |
| QA that crosses repos and QA at a release; keeping `[verified]` honest | `references/qa.md` | |
| The design gate: a new screen starts in the design portal | `fullstack-task` § Design gate, `design-guard.mjs` | |
| Standing audit of drift between repos and against the standard | nightly `contract-check.yml` | `references/known-drift.md` |
| Decisions and their why, across repos | `docs/*.md` here; a change that spans repos has one plan, in `.agents/plans/` here (findings, order, contracts, every repo's phases, release, clean-up) and no copy in any repo; each repo's PR carries its phases as commits | `.agents/plans/org-isolation.md` |

Reference files (read on demand, not all at once):

| File | When |
|---|---|
| `references/repo-map.md` | You need the deep map of a repo: entry docs, layout, build/test, CI, what it publishes, who consumes it |
| `references/cross-repo-contracts.md` | The change touches two repos, or a "single fact" (port, service name, image, env var, SLO) that several repos copy |
| `references/known-drift.md` | Before trusting a repo's own CLAUDE.md/README, or when something "should exist but doesn't" |
| `references/shipping.md` | You are about to branch, commit, push or open a PR in any repo, or a checkout is missing/behind |
| `references/qa.md` | The task is "QA this", a release was just cut, a PR changes a user-facing path, or a repo has no QA file |

## Reviewer mode

"Review this", "will this break X", "is it safe to merge", a PR link, or a nightly audit → **`cross-repo-review`**,
not a repo-local review. It runs `scripts/impact.py` (which consumers a change touches) and
`scripts/contract-check.py` (do all copies of each contract still agree, with the change substituted in),
then reads the consumers and gives SAFE / NEEDS FOLLOW-UP / BLOCKS with per-repo follow-ups. Every PR
the orchestrator opens gets this review first (`references/shipping.md` § 2).

## Step 0 — the checkouts

Every org repo, its URL, kind and usage is in `repos.yaml` at the org root — fifteen repos, all of them part
of development. The router owns the checkouts:

```bash
cd /Volumes/Disk/IdeaProjects/cvhome-saas
scripts/clone.sh <repo> [<repo> ...]   # clones from repos.yaml if the directory is missing, else fetches; prints behind/ahead
scripts/status.sh                      # branch, ahead/behind, dirty count for every checkout
```

Run it for each repo the task will touch **before** reading code there: a stale `main` produces a plan
against code that no longer exists. Fast-forward a clean, behind `main` with `git -C <repo> pull --ff-only`.
`.github` is checked out as `dot-github/` (manifest `dir:`).

## Step 1 — classify the ask

Match the **subject** of the task, not the words in it ("deploy the new endpoint" is two tasks).

| The task is about | Owner | Hand off to |
|---|---|---|
| Java/Spring service code, Angular `console-ui`, Next.js `landing-ui` + themes, `uaa`/`cua` auth, tenancy/pods/billing logic, DDL, `.http` files, unit/integration tests, Gradle/npm build, `common-config.yml` / `lcl-config.yml` / `fargate-config.yml`, `lcl.yml` **of cvhome**, `docker-compose-*.yml`, `extra/monitoring/` (local Prometheus/Grafana/Loki/Tempo), the `spg` **Caddyfile**, cvhome CI workflows, image publish to ECR | **`cvhome/`** | `fullstack-task` |
| Terraform, CloudFormation bootstrap, ECS/Fargate task defs, Cloud Map, ALB/NLB/Route53/ACM, RDS, S3/CloudFront, IAM for the platform, CodeBuild pipeline, flavours, hibernation, autoscaling, `services.yaml`, cost, "why is prod X", anything `aws` CLI | **`cvhome-platform/`** | `infra-task` |
| The Caddy **binary/image** (plugins, Go version, xcaddy), the `domain_lookup` middleware, the S3 certificate storage plugin, the ADOT collector config that runs **on AWS**, mirroring an image to public ECR | `saas-gateway/`, `caddy-domainlookup/`, `certmagic-s3/`, `aws-otel-collector/`, `public-dkr/` | `infra-task` (§ helper images) |
| The `lcl` CLI itself (commands, schema, supervisor, ports, publishing to npm) | **`lcl/`** | `tools-task` |
| k6 scripts, clients, journeys, thresholds, fixtures, Prometheus/Grafana for load tests, `make` targets | **`load-testing/`** | `tools-task` |
| Playwright browser regression tests (correctness, not performance) | **`e2e-testing/`** | `tools-task` |
| The public docs site (VitePress), architecture pages | `cvhome-saas.github.io/` | `docs-task` |
| The org profile on github.com/cvhome-saas, the one-command evaluation install (`fast-run.sh`) | `dot-github/`, `assets/` | `docs-task` |
| A product idea, missing feature, backlog entry, feature spec before any code | `ideation/` | `docs-task` |
| In-repo docs (`AGENTS.md`, a skill's `references/*.md`, `qa/*.md`, `docs/*.md`) | the repo that owns the code | the owner's skill, docs section |
| "release", "cut a version", "bump lcl", tagging, version numbers, changelog | orchestrator | `docs/releasing.md` (runbook) — run the workflow; never tag or bump by hand in a sub-repo. A release records compatibility; it never deploys |
| "deploy 2.1.0 to dev/staging/prod", "roll back", "what version does prod run" | `cvhome-platform` (`envs/<env>.tfvars` `image_tag`, bootstrap `ImageTag`, the CodeBuild pipeline) | `infra-task` |
| "create a repo", "new shared lib / tool / image / plugin", a plan naming a repo that does not exist | orchestrator | `new-repo` (a new cvhome service is a module, not a repo) |
| "add CLAUDE.md to X", "make X follow the conventions", a repo with no AGENTS.md, missing hooks or `/go` | the repo, from here | `repo-standard` |
| "QA this", "is it verified", "run the smoke after the release" | the owning repo's stack | `references/qa.md` |
| "design a new page / screen", "mock up", a plan phase that adds a UI route | `cvhome` (console-ui, landing-ui, uaa-fe) | `fullstack-task` § Design gate — the `design` skill first, record in `.agents/designs/`, then implement |
| Two or more of the above, or a fact that is copied across repos | several | `cross-repo-change` |

Disambiguators that recur:

- **"Port" / "service name" / "new service"** → the fact lives in `cvhome/store-commons/autoconfigure/src/main/resources/common-config.yml`; `cvhome-platform/services.yaml`, `cvhome/lcl.yml`, `load-testing/k6/config/env/lcl.json` mirror it. Always `cross-repo-change`.
- **"Observability"** splits three ways: app instrumentation and local Grafana → `cvhome` (`common-config.yml` otel block, `extra/monitoring/`); the AWS collector image → `aws-otel-collector`; whether a flavour runs a collector and Container Insights → `cvhome-platform` (`flavours.yaml` `monitoring`, `services.yaml` `infra.otel-collector`).
- **"spg" / "gateway" / "custom domain / TLS"**: Caddyfile and routes → `cvhome/store-pod/spg`; the Caddy binary → `saas-gateway` (+ `caddy-domainlookup`, `certmagic-s3`); getting a new binary in front of spg → `public-dkr` matrix then the pin in cvhome; the NLB, cert bucket, `ASK_TLS_URL`/`CERT_BUCKET` env → `cvhome-platform/modules/store-pod`. The Spring `store-core-gateway` is plain `cvhome` code.
- **"Base image" / "image not found in public ECR"** → `public-dkr` (the matrix is the allow-list of what exists at `public.ecr.aws/b2i4h4k9`).
- **"Browser test" / "e2e"**: correctness → `e2e-testing` (Playwright); performance/web vitals → `load-testing` browser scripts; manual QA scripts → `cvhome/<service>/qa/*.md`.
- **"Run the stack" / "lcl won't start"**: a bug in the runner → `lcl`; a bad `lcl.yml`, a service failing its health check, hosts entries → `cvhome` (`qa/lcl-qa.md`, `references/qa-testing.md`).
- **"Deploy"**: images are built by CodeBuild from the app repo and applied by Terraform; there is **no** deploy workflow in `cvhome`. Deploy questions go to `infra-task`; "my change is not in the image" starts in `cvhome` (`build.gradle` `imageName`, `bootBuildImage`) then `cvhome-platform` (`services.yaml` `image`, drift check).
- **"Secrets"**: app-side encryption of tenant secrets (`secret-crypto`) → `cvhome`; Secrets Manager entries, bootstrap-generated secrets, ECS secret bindings → `cvhome-platform`. Never read a secret value into context (`aws secretsmanager get-secret-value` is off-limits; see cvhome-platform `CLAUDE.md` § Secret Safety).
- **Load or perf numbers** → `load-testing` measures, `cvhome` fixes, `cvhome-platform` sizes. Start in `load-testing/docs/baseline.md`.

## Step 2 — before touching the repo

1. `cd` into the repo (or address it with absolute paths). Its own `CLAUDE.md`/`AGENTS.md` and `.claude/skills/` only apply there. **Read `AGENTS.md` yourself** in `cvhome`, `lcl`, `load-testing`: `CLAUDE.md` is one line (`@AGENTS.md`) and nested auto-loading is not guaranteed from the org root.
1b. **Find the operation's runbook before typing a command.** The skills here are the map, not the manual: for
   "run a load test", "QA this", "deploy", "release", grep the target repo's `README.md`, `docs/` and `qa/` for
   the operation and follow *that* (a `## Quick start` is not the whole story — read the section after it too).
   The 2026-09-07 load test ran against the wrong stack because `AGENTS.md` and the Makefile were read and the
   README's "load stack" section was not.
2. Check `references/known-drift.md` for that repo. `cvhome-platform/CLAUDE.md` in particular still says the repo is empty; it is not.
3. Check `git -C <repo> status` and `git -C <repo> log -5`. Sibling repos advance independently; the local checkout may be behind `origin/main` (`scripts/status.sh`).
4. Apply the working mode — the same everywhere once `repo-standard` has landed there: a worktree per change cut from `origin/main` (`.claude/worktrees/<type>-<name>`, hook-enforced; the org-level hook re-applies it from here), a plan in `.agents/plans/<name>.md` whose phases are the commits of one PR, `scripts/verify.sh` before push, `/go` to ship. `scripts/standard-check.py <repo>` says whether the repo has adopted it; if not, adopt it first or follow it by hand and say so. Every push to `main` in the image and mirror repos **publishes**.

## Step 3 — order when several repos are involved

Producers before consumers. The contract graph (details in `references/cross-repo-contracts.md`):

```
caddy-domainlookup ─┐
certmagic-s3 ───────┴─► saas-gateway (Docker Hub sha-…) ─► public-dkr (mirror to public ECR) ─► cvhome/store-pod/spg (FROM) ─► cvhome-platform (pod.spg)
public-dkr also mirrors node / postgres / otel-contrib / paketo base images that cvhome Dockerfiles and buildpacks pull
aws-otel-collector (image) ────────────────────────────────────────────────────► cvhome-platform (infra.otel-collector)
cvhome common-config.yml ─► cvhome lcl.yml ─► lcl (runs it) ─► load-testing lcl.json (targets it)
cvhome common-config.yml / fargate-config.yml / build.gradle ─► cvhome-platform services.yaml (drift-checked in CI)
cvhome extra/monitoring SLO buckets ◄─► load-testing k6/config/thresholds.js (must agree)
```

A typical "feature + infra" task: 1) `cvhome` PR (code, config slices, `.http`, tests, QA) → 2) `cvhome-platform` PR (`services.yaml`, secrets, env) → 3) `load-testing` client/journey if the endpoint matters under load → 4) docs. Say which step you are on; do not squash them into one PR across repos (impossible anyway: separate git repos).

## Step 4 — divide the work

Break the task into **work items, one per repo**, each with: repo, branch name (the same `<type>/<name>` in
every repo), files, gates, and what it depends on. Then:

- **Independent items run in parallel.** Spawn one subagent per repo (Agent tool, `general-purpose` or
  `fork`), giving it the absolute repo path, the area skill to follow (`fullstack-task`, `infra-task`,
  `tools-task`, `docs-task`), the branch name, and the exact deliverable. Read-only investigation across
  repos is also parallel (`Explore` agents). The orchestrator keeps the plan, merges the reports, and does
  not edit files itself while subagents own a repo.
- **Dependent items run in order** (producers before consumers, § Step 3). A consumer item may start once
  the producer's *contract* is fixed (the port, the env var name, the image tag), not necessarily merged;
  say which assumption it is building on.
- **One change, one PR per repo**, shipped per `references/shipping.md`. Never mix repos in a commit, never
  leave a repo's gates unrun because another repo's work is more interesting.
- Small single-repo tasks skip the subagents: route, do, ship.

## Step 5 — report

Name the repo and the path for every change, in the repo's own terms (`store-pod/catalog/catalog-service/...`, `modules/store-pod/nlb.tf`). If a step was left to another repo, say so and which skill picks it up.
