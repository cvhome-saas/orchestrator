# Known drift — where a repo's own docs disagree with its code (as of 2026-09-07)

Verify against the file before acting on any of these; fix the doc in its owning repo when you are there
anyway.

## cvhome-platform
- `CLAUDE.md` says the repo is empty, not a git repo, and that the architecture proposal is unwritten. All
  false: ~6,200 lines of HCL/YAML/Python, ~30 commits, `docs/infra-target-architecture.html` exists, the stack
  has been applied and is being debugged against live failures (Sept 6 commits).
- `CLAUDE.md` decision 2 says `cvhome-common-ecs-service` stays external and tag-pinned. It was absorbed as
  `modules/ecs-service/` (`.claude/plans/infra-implementation-plan.md` §2).
- `CLAUDE.md` "known routing bugs" (seller-ui vs console-ui host, Stripe webhook path, Stripe key in tenancy)
  are already fixed in `services.yaml` and `scripts/register-stripe-webhook.sh`.
- Target layout omits `modules/ecs-service`, `prereq/`, `flavours.yaml`, `bootstrap/guard-rules/`,
  `scripts/`, `docs/`. Runtimes are three (`spring`, `node`, `caddy`), not two.
- `variables.tf` default `postgres_version = "18.4"` is flagged unverified in its own comment.

## cvhome
- `project-structure` skill (both `.claude/skills` v3.3 and `.agents/skills` v3.2) omits `billing` 8021 and
  `pod-registry` 8022 from the store-core table and still says tenancy owns subscriptions/Stripe. Truth:
  `settings.gradle`, `common-config.yml`, `GatewayRouteLocatorImpl`.
- `.claude/skills/project-structure` is a **copy**, not a symlink like the other skills; the two versions
  differ. Edit the `.claude` one (newer) and re-sync, or make it a symlink.
- `AGENTS.md` refers to `.AGENTS/commands/` and `.AGENTS/skills/`; the real dirs are `.claude/commands/` and
  `.agents/skills/` (+ `.claude/skills` symlinks). `.agents/requirments/` is misspelled on disk; keep the path.
- `.github/workflows/release.yml` still assumes a `develop` branch; origin has only `main`.
- `.github/workflows/.env` holds masked-looking AWS placeholders; not real config.
- `store-pod/spg/Dockerfile` pins `saas-gateway:sha-8eed986` (public ECR) while `docker-compose-lcl.yml` pins
  `sha-4a6d381` (Docker Hub). `saas-gateway` HEAD is `4a6d381`. Local and AWS run different Caddy builds.
- Untracked plans on `main` (`.agents/plans/*.md`, `.claude/plans/*.md`) as of today; they are allow-listed by
  the worktree guard, but decide whether to commit them.

## lcl
- `CHANGELOG.md` has an *Unreleased* section (project `.env` defaults) above 0.1.0; `package.json` is still
  0.1.0. A release needs the bump in both `package.json` and `src/version.ts`.

## load-testing
- `results/` has 14 local JSON summaries, gitignored; `docs/baseline.md` is the committed record.

## saas-gateway
- `README.md` documents `github.com/techknowlogick/certmagic-s3`; `Dockerfile` builds the org fork
  `github.com/cvhome-saas/certmagic-s3`.
- Workflow pushes to Docker Hub, but the app's Dockerfile pulls from `public.ecr.aws/b2i4h4k9/...`; the mirror
  step is undocumented.

## caddy-domainlookup
- CI uses Go 1.21; `go.mod` says `go 1.23.0`, toolchain 1.24.2; the real build happens in `saas-gateway` on
  Go 1.25. Caddy pinned at 2.7.6.

## aws-otel-collector
- `README.md` is 0 bytes. Consumed by mutable `:latest`. One uncommitted local change in the working tree.
- Workflow sets up buildx/QEMU but `build.sh` does a plain single-arch `docker build`.

## cvhome-saas.github.io
- Entire deployment section and the architecture page describe the retired repos and services; see
  `deprecated-repos.md`. Do not "fix a typo" here without deciding whether the page should exist.

## ideation
- Feature docs reference `seller-ui`, `catalog-service`, `analytics-service`, `search-service`; map to
  `console-ui`, `store-pod/catalog`, and services that do not exist yet.
