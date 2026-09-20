# Known drift — where a repo's own docs disagree with its code (as of 2026-09-07)

Verify against the file before acting on any of these; fix the doc in its owning repo when you are there
anyway.

## cvhome-platform
- **v2.0.0 pair is not self-consistent**: cvhome v2.0.0 (PR #330) needs `UAA_IMPERSONATION_SECRET` bound to
  `uaa` and `store-core-gateway`; cvhome-platform v2.0.0 does not generate or bind it (fix: cvhome-platform#6,
  lands in the next release). Deploying v2.0.0 to an environment needs that fix plus a stack update.
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
- `scripts/cleanup.sql` (the SQL pass of `make clean`) is stale against the current cvhome schema: it deletes from
  `tenancy.organization` (gone since the tenancy / pod-registry split) and hits the `merchant_language` foreign key
  when deleting `merchant_store`. The API pass works; the SQL pass errors. Until fixed, a full wipe is
  `make stack-down-hard` (drops the stack's volumes). Found 2026-09-08.
- Since 2026-09-08 the load stack and all monitoring configuration live here (`stack/`, `docs/monitoring/`); until
  the cvhome PR that removes `extra/monitoring` merges, both repos carry a copy and load-testing's is the one to edit.
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
- Its local twin is `load-testing/stack/monitoring/otel-collector.yml` (since 2026-09-08); the two filter lists are not kept in sync by any check.
- Workflow sets up buildx/QEMU but `build.sh` does a plain single-arch `docker build`.

## cvhome-saas.github.io
- **Rewritten 2026-09-20 and no longer drifting** (PR #5). The site is written from the code: C4 levels 1 to 3,
  an AWS and a local deployment view, the three user journeys, local development with lcl, a configuration
  reference, and the operator pages. Every page ends with the file it was written from; start a correction by
  diffing that file. Screenshots come from a real lcl stack and a real dev environment.
- What it no longer says, in case an old link or memory suggests otherwise: `cvhome-bootstrap`,
  `cvhome-ecs-fargate-infra`, `store-ui`, `welcome-ui`, `merchant-ui`, ALB TLS termination for stores. The
  five old sidebar URLs are one-line stubs pointing at their successors.
- Two live-account corrections landed with it and are worth not re-breaking: the bootstrap stack's Outputs tab
  shows ten entries, not eleven, because `StripeWebhookPath` is conditional on a `StripeKey`; and the apply
  stage skips the Stripe webhook registration, with a line in its log, when no key was given.
- **Production-only trap** (cost one broken deploy on 2026-09-20): VitePress rewrites image paths it finds in
  markdown, but a path named anywhere else, such as `themeConfig.logo` or a `head` favicon tag, is served
  exactly as written and must live under `docs/public`. The dev server hides this because Vite serves `docs/`
  as the root. `scripts/check-images.sh` enforces both rules now.

## public-dkr
- The matrix mirrors `saas-gateway:sha-8eed986` — the same sha `cvhome/store-pod/spg/Dockerfile` pins, so AWS
  is consistent, but `docker-compose-lcl.yml` runs `sha-4a6d381` straight from Docker Hub. Mirrors
  `otel/opentelemetry-collector-contrib:0.139.0` while `docker-compose-lcl.yml` runs `0.150.1`.
- README lists two images; the workflow matrix has nine. The matrix is the truth.

## assets
- **Retired 2026-09-20** (PR #3). `fast-run/fast-run.sh` now prints a notice and exits 1 before touching
  `/etc/hosts` or Docker, pointing at the site's local development guide. lcl is the only documented local
  path.
- The compose file stays as the only record of the 1.0.x layout (`core-auth`, `store-ui`, `welcome-ui`,
  `merchant-ui`, `order`, RabbitMQ, registry `public.ecr.aws/g0a5h6c1/1691275173`) and is not runnable: its
  MinIO tag `bitnami/minio:2025.4.22` is gone from Docker Hub. `contract-check.py infra-images` still WARNs on
  that tag; the warning is expected and is not a reason to "fix" a retired script.
- The docs site never actually linked fast-run as its quick start, contrary to what this file used to say: the
  only mention was unlinked bold text on a page that was not in the sidebar.

## e2e-testing
- Playwright scaffold only: `tests/example.spec.ts` hits playwright.dev, no `baseURL`, no cvhome journey. The
  CI workflow runs on every push and passes vacuously.

## certmagic-s3
- `go.mod` pins caddy 2.7.6 like `caddy-domainlookup`; both are compiled by `saas-gateway` on Go 1.25.

## ideation
- Feature docs reference `seller-ui`, `catalog-service`, `analytics-service`, `search-service`; map to
  `console-ui`, `store-pod/catalog`, and services that do not exist yet.
