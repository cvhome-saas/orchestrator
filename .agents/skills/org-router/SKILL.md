---
name: org-router
description: Routes any cvhome-saas task to the right repo(s) and the right per-repo skill. Use FIRST for every task started from the org root (/Volumes/Disk/IdeaProjects/cvhome-saas) before opening files - "add an endpoint", "change a port", "deploy", "why is prod 502", "add a k6 script", "lcl won't start", "update the docs", "new feature idea", or anything ambiguous between backend (cvhome), infra (cvhome-platform + saas-gateway/caddy-domainlookup/aws-otel-collector), tools (lcl, load-testing), and docs (cvhome-saas.github.io, ideation). Classifies the ask, names the owning repo(s), says which repo goes first when several are touched, then hands off to backend-task / infra-task / tools-task / docs-task / cross-repo-change. Also the place to ask "which repo owns X", "is repo Y deprecated", "what is the image chain for spg".
---

# cvhome-saas org router

This directory is the **org checkout**: nine sibling git repos, each with its own rules. Nothing here is
a Gradle module or a Terraform root; the org repo tracks only `repos.yaml`, the skills, `scripts/` and this
guidance. **Every real change lands in exactly one sub-repo per commit**, under that repo's own conventions.

Reference files (read on demand, not all at once):

| File | When |
|---|---|
| `references/repo-map.md` | You need the deep map of a repo: entry docs, layout, build/test, CI, what it publishes, who consumes it |
| `references/cross-repo-contracts.md` | The change touches two repos, or a "single fact" (port, service name, image, env var, SLO) that several repos copy |
| `references/known-drift.md` | Before trusting a repo's own CLAUDE.md/README, or when something "should exist but doesn't" |
| `references/deprecated-repos.md` | A task or doc names a repo not checked out here |
| `references/shipping.md` | You are about to branch, commit, push or open a PR in any repo, or a checkout is missing/behind |

## Step 0 — the checkouts

Every org repo, its URL, kind and status is in `repos.yaml` at the org root. The router owns the checkouts:

```bash
cd /Volumes/Disk/IdeaProjects/cvhome-saas
scripts/clone.sh <repo> [<repo> ...]   # clones from repos.yaml if the directory is missing, else fetches; prints behind/ahead
scripts/status.sh                      # branch, ahead/behind, dirty count for every checkout
```

Run it for each repo the task will touch **before** reading code there: a stale `main` produces a plan
against code that no longer exists. Fast-forward a clean, behind `main` with `git -C <repo> pull --ff-only`.
A repo with `status: deprecated` is cloned only on explicit request (`scripts/clone.sh <name>` works for any
status) and never edited.

## Step 1 — classify the ask

Match the **subject** of the task, not the words in it ("deploy the new endpoint" is two tasks).

| The task is about | Owner | Hand off to |
|---|---|---|
| Java/Spring service code, Angular `console-ui`, Next.js `landing-ui` + themes, `uaa`/`cua` auth, tenancy/pods/billing logic, DDL, `.http` files, unit/integration tests, Gradle/npm build, `common-config.yml` / `lcl-config.yml` / `fargate-config.yml`, `lcl.yml` **of cvhome**, `docker-compose-*.yml`, `extra/monitoring/` (local Prometheus/Grafana/Loki/Tempo), the `spg` **Caddyfile**, cvhome CI workflows, image publish to ECR | **`cvhome/`** | `backend-task` |
| Terraform, CloudFormation bootstrap, ECS/Fargate task defs, Cloud Map, ALB/NLB/Route53/ACM, RDS, S3/CloudFront, IAM for the platform, CodeBuild pipeline, flavours, hibernation, autoscaling, `services.yaml`, cost, "why is prod X", anything `aws` CLI | **`cvhome-platform/`** | `infra-task` |
| The Caddy **binary/image** (plugins, Go version, xcaddy), the `domain_lookup` middleware, the ADOT collector config that runs **on AWS** | `saas-gateway/`, `caddy-domainlookup/`, `aws-otel-collector/` | `infra-task` (§ helper images) |
| The `lcl` CLI itself (commands, schema, supervisor, ports, publishing to npm) | **`lcl/`** | `tools-task` |
| k6 scripts, clients, journeys, thresholds, fixtures, Prometheus/Grafana for load tests, `make` targets | **`load-testing/`** | `tools-task` |
| The public docs site (VitePress), org README, architecture pages | `cvhome-saas.github.io/` | `docs-task` |
| A product idea, missing feature, backlog entry, feature spec before any code | `ideation/` | `docs-task` |
| In-repo docs (`AGENTS.md`, a skill's `references/*.md`, `qa/*.md`, `docs/*.md`) | the repo that owns the code | the owner's skill, docs section |
| Two or more of the above, or a fact that is copied across repos | several | `cross-repo-change` |

Disambiguators that recur:

- **"Port" / "service name" / "new service"** → the fact lives in `cvhome/store-commons/autoconfigure/src/main/resources/common-config.yml`; `cvhome-platform/services.yaml`, `cvhome/lcl.yml`, `load-testing/k6/config/env/lcl.json` mirror it. Always `cross-repo-change`.
- **"Observability"** splits three ways: app instrumentation and local Grafana → `cvhome` (`common-config.yml` otel block, `extra/monitoring/`); the AWS collector image → `aws-otel-collector`; whether a flavour runs a collector and Container Insights → `cvhome-platform` (`flavours.yaml` `monitoring`, `services.yaml` `infra.otel-collector`).
- **"spg" / "gateway" / "custom domain / TLS"**: Caddyfile and routes → `cvhome/store-pod/spg`; the Caddy binary → `saas-gateway` (+ `caddy-domainlookup`); the NLB, cert bucket, `ASK_TLS_URL`/`CERT_BUCKET` env → `cvhome-platform/modules/store-pod`. The Spring `store-core-gateway` is plain `cvhome` code.
- **"Run the stack" / "lcl won't start"**: a bug in the runner → `lcl`; a bad `lcl.yml`, a service failing its health check, hosts entries → `cvhome` (`qa/lcl-qa.md`, `references/qa-testing.md`).
- **"Deploy"**: images are built by CodeBuild from the app repo and applied by Terraform; there is **no** deploy workflow in `cvhome`. Deploy questions go to `infra-task`; "my change is not in the image" starts in `cvhome` (`build.gradle` `imageName`, `bootBuildImage`) then `cvhome-platform` (`services.yaml` `image`, drift check).
- **"Secrets"**: app-side encryption of tenant secrets (`secret-crypto`) → `cvhome`; Secrets Manager entries, bootstrap-generated secrets, ECS secret bindings → `cvhome-platform`. Never read a secret value into context (`aws secretsmanager get-secret-value` is off-limits; see cvhome-platform `CLAUDE.md` § Secret Safety).
- **Load or perf numbers** → `load-testing` measures, `cvhome` fixes, `cvhome-platform` sizes. Start in `load-testing/docs/baseline.md`.

## Step 2 — before touching the repo

1. `cd` into the repo (or address it with absolute paths). Its own `CLAUDE.md`/`AGENTS.md` and `.claude/skills/` only apply there. **Read `AGENTS.md` yourself** in `cvhome`, `lcl`, `load-testing`: `CLAUDE.md` is one line (`@AGENTS.md`) and nested auto-loading is not guaranteed from the org root.
2. Check `references/known-drift.md` for that repo. `cvhome-platform/CLAUDE.md` in particular still says the repo is empty; it is not.
3. Check `git -C <repo> status` and `git -C <repo> log -5`. Sibling repos advance independently; the local checkout may be behind `origin/main` (`scripts/status.sh`).
4. Apply the repo's working mode: `cvhome` **requires a worktree** for any edit (`.claude/worktrees/<type>-<name>`, hook-enforced, and the org-level hook re-applies it from here); `lcl` and `load-testing` want a feature branch; `cvhome-platform` merges by PR; the helper image repos have no branch discipline but every push to `main` **publishes an image**.

## Step 3 — order when several repos are involved

Producers before consumers. The contract graph (details in `references/cross-repo-contracts.md`):

```
caddy-domainlookup ─┐
certmagic-s3 ───────┴─► saas-gateway (image) ─► cvhome/store-pod/spg (FROM sha-…) ─► cvhome-platform (pod.spg)
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
  `fork`), giving it the absolute repo path, the area skill to follow (`backend-task`, `infra-task`,
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
