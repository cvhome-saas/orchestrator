# Repo map — the sixteen org repos

Paths are relative to the org root `/Volumes/Disk/IdeaProjects/cvhome-saas/`. All of them are cloned by
`scripts/clone.sh` (`repos.yaml` is the list). Each repo's own
`AGENTS.md`/`CLAUDE.md` is authoritative for how to work *inside* it; this file is the cross-repo view.

## cvhome — the application (kind: app)

- **What**: multi-tenant e-commerce SaaS. Java 25, Spring Boot 4, Angular 20 (`console-ui`, SSR), Next.js 16
  (`landing-ui` + theme packages), Postgres. One Gradle 9.2 composite build drives Java *and* npm.
  Package root `com.asrevo.cvhome.*`. Version in `gradle.properties`.
- **Entry docs**: `AGENTS.md` (enforcement layer: build, worktree rule, push receipt, review gates, error rules,
  QA rules). `.claude/skills/project-structure/SKILL.md` (the rulebook, 25 reference files under
  `references/`: `new-service.md`, `api-conventions.md`, `qa-testing.md`, `gateways-and-local-domains.md`,
  `multi-tenancy.md`, `service-discovery.md`, `error-handling.md`, `landing-ui.md`, ...). `README.md` public.
- **Three trees**: `store-commons/` libraries only (`commons` value objects, `errors`, `autoconfigure` shared
  YAML slices, `test-support`, `uaa-client`, `secret-crypto`, `sso`, `ecs-commons`, `ui-kit`). `store-core/` one
  shared platform instance. `store-pod/` deployed once per pod. Plus `build-logic/` and
  `gradle/libs.versions.toml`.
- **Service catalog** (source of truth `store-commons/autoconfigure/src/main/resources/common-config.yml`):
  store-core: `store-core-gateway` 8000, `uaa` 8001, `console-ui` 8011, `tenancy` 8020, `billing` 8021,
  `pod-registry` 8022. store-pod: `spg` 80/443 (Caddy), `landing-ui` 8110, `merchant` 8120, `content` 8121,
  `catalog` 8122, `checkout` 8123, `cua` 8124, `payment` 8125, `inventory` 8126.
- **Tenancy**: store = logical tenant, pod = physical deployment with its own DB hosting many stores;
  `ManagerStoreEntity.podId` is the routing table. Every endpoint takes `StoreMerchantId` + `LanguageCode` and
  `@PreAuthorize("hasPermission(...,'LAYER.DOMAIN.ACTION')")`; `CustomPermissionEvaluator` denies by default.
- **Two auth servers**: `uaa` (staff) and `cua` (shoppers, headless), one SSO codebase deployed twice.
- **Edges**: `store-core-gateway` (`gateway.com:8000`, `GatewayRouteLocatorImpl`, `/spg/**?store=&pod=` built
  from `PodClient` every minute) and `spg` (`store-pod/spg/Caddyfile`: strips `/merchant*`, `/catalog*`, ...;
  keeps `/cua*`; falls through to `landing-ui`; on-demand TLS + `domain_lookup`).
- **Local run**: `lcl start -d` from the repo root (`lcl.yml`); infra in Docker via `docker-compose-lcl.yml`
  (postgres, minio, spg, otel-collector-contrib, loki, tempo, prometheus, grafana), Java on the host. One stack
  per worktree with `--stack <name>`. `sudo ./extra/scripts/configure-domain.sh` once for `/etc/hosts`.
  `docker-compose-load.yml` is an overlay that runs every service as its built image (for `load-testing`).
- **Build/verify**: `./gradlew build -x test -x check`, `test`, `integrationTest` (Docker), `check`
  (checkstyle, warnings = errors, `TODO` fails). `extra/scripts/verify-before-push.sh` writes the receipt the
  push hooks demand. Frontends: `npm run build` **and** `npm run lint` in the `-ui` module.
- **Working mode**: never edit the primary checkout. `git worktree add --no-track
  .claude/worktrees/<type>-<name> -b <type>/<name> origin/main`, work there, `/go` ships a PR into `main`,
  `/reset` cleans up. Hooks: `.claude/hooks/worktree-guard.mjs`, `push-guard.mjs`.
- **CI** (`.github/workflows/`): build, quality (checkstyle + monitoring dashboards/promtool/otel config
  checks), tests (unit, integration, coverage). Image publish to private/public ECR on release or dispatch via
  `bootBuildImage --publishImage`. **No deploy workflow**; deployment is `cvhome-platform`'s CodeBuild.
- **Skills**: `project-structure`, `angular-developer`, `vercel-react-best-practices`, `shadcn`,
  `lcl-stack-builder`. Commands `/go`, `/reset`. Plans in `.agents/plans/` (35, named), requirements in
  `.agents/requirments/`.
- **Consumes**: `saas-gateway` image (`store-pod/spg/Dockerfile` FROM), `lcl` CLI. **Feeds**:
  `cvhome-platform` (catalog + images), `load-testing` (targets it), docs.

## cvhome-platform — AWS infrastructure (kind: infra)

- **What**: Terraform ≥1.10 (pinned 1.14.6), AWS provider ~>6.62. ECS Fargate + Cloud Map, per-pod NLB + RDS +
  CloudFront, shared ALB + RDS for store-core, one VPC. One-click CloudFormation bootstrap that creates state
  bucket, deploy role, three CodeBuild projects and starts the pipeline.
- **Entry docs**: `README.md` (launch button, layout), `CLAUDE.md` (rationale and locked decisions; **status
  claims stale**, see `known-drift.md`), `.claude/plans/infra-implementation-plan.md`,
  `docs/infra-target-architecture.html`.
- **Layout**: `main.tf` env root (reads `/{project}/{env}/config` and `/prereq` from SSM, layers
  `flavours.yaml < SSM < tfvars`, guards), `variables.tf` (14 vars), `outputs.tf`, `backend.tf` (S3,
  `use_lockfile`), `services.yaml` (6 core + 9 pod + `infra.otel-collector`), `flavours.yaml` (`dev`,
  `staging`, `prod`, `ephemeral`), `envs/{dev,staging,prod}.tfvars`, `prereq/` (ECR repos + ACM certs, own
  state), `modules/network`, `modules/ecs-service` (the workhorse: SG, log group, task def, Cloud Map, ECS
  service, autoscaling, scoped IAM), `modules/store-core` (ALB, RDS, otel-collector), `modules/store-pod`
  (NLB, RDS, CDN + cert buckets, CloudFront), `bootstrap/bootstrap.yaml` + `guard-rules/`, `scripts/`
  (`check-catalog-drift.py`, `hibernate.sh`, `wake.sh`, `register-stripe-webhook.sh`).
- **Pipeline**: CodeBuild `<project>-<env>-1-prereq` (this repo) → `-2-images` (clones **cvhome**, runs
  `./gradlew bootBuildImage --publishImage`) → `-3-apply` (this repo, then Stripe webhook). Chained by
  EventBridge. Also `-destroy`, `-hibernate`, `-wake`, and a daily hibernation-keeper Lambda.
- **CI**: `terraform-validate.yml` (fmt, validate matrix, tflint, **catalog-drift** against the app repo,
  cfn-lint + cfn-guard, plan on dev via OIDC). `publish-bootstrap.yml` uploads the template to
  `s3://cvhome-saas/platform/bootstrap.yaml` on push to main.
- **Secrets**: bootstrap creates `/{project}/{env}/{stripe,uaa,sso}` in Secrets Manager; Terraform binds
  `arn:json-key::` refs from `services.yaml`; RDS uses `manage_master_user_password`. Never fetch values.
- **Observability**: one standalone `otel-collector` ECS service per environment in the core cluster, gated by
  `flavour.monitoring`; image `ashraf1abdelrasool/aws-otel-collector:latest` (external). Off → sets
  `OTEL_SDK_DISABLED=true` and `MANAGEMENT_OTLP_METRICS_EXPORT_ENABLED=false`.
- **Working mode**: PRs into `main`; `terraform fmt`/`validate`; use the installed HashiCorp skills
  (`terraform-style-guide`, `terraform-test`, ...) and `aws-cloudformation` for the bootstrap. Cost numbers
  from the pricing MCP, never memory. Region is never in tfvars (CodeBuild passes it).
- **Consumes**: `cvhome` catalog/images, `aws-otel-collector` image, `saas-gateway` indirectly (via spg image).

## lcl — local stack runner CLI (kind: tool, public npm)

- **What**: `@cvhome-saas/lcl` 0.1.0, TypeScript ESM, Node ≥22, deps `ajv` + `yaml` only. One `lcl.yml` per
  project; validates, allocates whole-stack port offsets, starts dependency-ordered processes + Compose,
  supervises named stacks (`--stack`), health checks, logs, events, control socket.
- **Entry docs**: `AGENTS.md` (project-structure table, invariants, 7-step config-field checklist, gates),
  `README.md`, `schema/lcl.schema.json`, `CHANGELOG.md`, `docs/release-checklist.md`, `CONTRIBUTING.md`.
- **Layout**: `bin/lcl.js` → `dist/src/main.js`; `src/{config,catalog,ports,instance,supervisor,control,proc,
  compose,health,render,logs,events,ui,version}.ts`; `src/commands/{start,stop,status,logs,doctor,init}.ts`;
  `test/*.test.ts` (node:test); `templates/`, `examples/`.
- **Commands**: `start`, `stop [--hard]`, `restart`, `status|ps`, `urls`, `ports`, `logs`, `events`, `why`,
  `doctor`, `validate`, `list`, `clean`, `init`. State `.lcl/<stack>/`, registry `~/.lcl/instances`.
- **Verify**: `npm run check`, `npm test` (Docker for Compose tests; `CI_NO_DOCKER=1` otherwise),
  `npm pack --dry-run`. Version must match in `package.json` and `src/version.ts`.
- **Release**: GitHub release `v<version>` → `publish.yml` via npm OIDC. Never publish/tag without the
  maintainer's explicit say-so.
- **Skill**: `lcl-stack-builder` (also vendored into cvhome). Language-neutral: never leak cvhome assumptions
  into the engine.
- **Consumers**: `cvhome/lcl.yml`, `load-testing` (reads live ports from `lcl urls`).

## load-testing — k6 suite (kind: tool, private)

- **What**: k6 v2.2.0 scripts for cvhome: smoke, selftest, storefront, shopper, admin, platform, browser,
  mixed (24 scripts). Import direction `lib/core ← lib/clients ← lib/journeys ← scripts`. One client per
  service, edge-agnostic; every knob declared in `k6/lib/core/env.js`; SLOs only in
  `k6/config/thresholds.js`; fixtures declared (`k6-<RUN_ID>` orgs/stores) and removed by `make clean`.
- **Entry docs**: `AGENTS.md`, `README.md` (map), `docs/coverage.md` (endpoint → client → script audit),
  `docs/prometheus.md`, `docs/baseline.md` (measured numbers).
- **Run**: `bin/k6run` wrapper (TESTID, tags, Prometheus remote-write, Grafana annotations);
  `make inspect` (no traffic), `make selftest`, `PROFILE=smoke make <layer>-<name>`, `make dash`.
  Target files `k6/config/env/<TARGET>.json`; only `lcl.json` and `aws.example.json` committed.
- **CI**: `check.yml` (lint stack + `make inspect` + archives), `run-k6.yml` (manual, self-hosted runner).
- **Skill**: `k6` (`.agents/skills/k6`).
- **Depends on**: a running cvhome stack (`lcl start -d --infra all` in `../cvhome`, or the
  `docker-compose-load.yml` overlay), Prometheus/Grafana from `cvhome/extra/monitoring`. App-side prerequisites
  (OTEL on, Hikari sizing) are cvhome changes, flagged in the README's table, never made here.

## saas-gateway — the Caddy image (kind: image)

- **What**: two-stage Dockerfile: `golang:1.25-alpine` + `xcaddy build --with github.com/cvhome-saas/certmagic-s3
  --with github.com/cvhome-saas/caddy-domainlookup`; `alpine:3.19` runtime with `cap_net_bind_service`.
- **Publish**: `.github/workflows/docker-publish.yml` on push to main → Docker Hub
  `${DOCKERHUB_USERNAME}/saas-gateway:latest` + `sha-<short>`, multi-arch.
- **Consumer**: `cvhome/store-pod/spg/Dockerfile` and `spg/compose.yml` (`FROM public.ecr.aws/b2i4h4k9/ashraf1abdelrasool/saas-gateway:sha-8eed986`)
  and `cvhome/docker-compose-lcl.yml` (`ashraf1abdelrasool/saas-gateway:sha-4a6d381` from Docker Hub). The
  Docker Hub → public ECR step is `public-dkr`'s matrix, which currently carries `sha-8eed986`.
- **Rule**: bump the pin in cvhome deliberately after a rebuild; a push to main here changes nothing until the
  pin moves. `README.md` names the wrong certmagic-s3 upstream.

## caddy-domainlookup — Caddy middleware (kind: plugin, Go)

- **What**: Caddy v2 module `http.handlers.domain_lookup`, directive `domain_lookup { lookup_url, cache_ttl }`.
  Per request: `GET {lookup_url}?domain=<host>` → JSON map → set as request headers (`Store-Id`, `Theme`,
  ...). Fails open. It does **not** do on-demand TLS; Caddy's `on_demand_tls { ask }` does, both against
  `merchant`'s `RouterController` (`public/ask-for-tls`, `public/lookup-by-domain`).
- **Build**: CI only `go build`; no artifact. Consumed by source path from `saas-gateway`'s xcaddy build, so a
  change here needs a `saas-gateway` rebuild and a cvhome pin bump to reach anything.
- **State**: frozen since 2025-06; `go.mod` pins caddy 2.7.6 / Go 1.23 while CI sets up Go 1.21.

## aws-otel-collector — ADOT collector image (kind: image)

- **What**: `public.ecr.aws/aws-observability/aws-otel-collector:latest` + `otel-config.yaml`: OTLP
  4317/4318 in; `memory_limiter`, per-signal `batch`, `filter/drop_metrics` (drops `spring.*`, `jdbc.*`,
  `hikaricp.*`, `tomcat.*`, `nodejs.*`, ...); `awsxray`, `awsemf`, `awscloudwatchlogs` out; health on 13133.
- **Publish**: push to main → Docker Hub `${DOCKERHUB_USERNAME}/aws-otel-collector:latest` + `sha-` tag.
- **Consumer**: `cvhome-platform/services.yaml` `infra.otel-collector` by mutable `:latest`. Local dev uses a
  different collector (`otel-collector-contrib`, `cvhome/extra/monitoring/logging-otel-collector-config.yml`).
  `cvhome/extra/monitoring/docs/porting.md` describes carrying the local dashboards to CloudWatch.
- **State**: current; `README.md` is empty; one uncommitted change in the working tree.

## cvhome-saas.github.io — public docs site (kind: docs)

- **What**: VitePress 1.6 + Mermaid, GitHub Pages via `.github/workflows/deploy.yml`. Pages under `docs/`:
  `guide/{introduction,core-concepts,architecture-overview}.md`, `development/{local-setup,contributing}.md`,
  `deployment/{overview,aws-deployment-guide,aws-architecture,cleanup-guide}.md`, `images/`, `digrams/` (sic).
- **State**: last commit 2025-06, **actively wrong**: names `cvhome-bootstrap`/`cvhome-ecs-fargate-infra`
  (now `cvhome-platform`), services `store-ui`/`welcome-ui`/`merchant-ui` (now `console-ui`, `billing`,
  `pod-registry`, ...), ALB TLS termination (now NLB passthrough to Caddy). A rewrite should source from
  `cvhome/.claude/skills/project-structure/` and `cvhome-platform/docs/infra-target-architecture.html`.

## ideation — product backlog (kind: ideas)

- **What**: `README.md` (empty checklists + 8-row backlog table + idea template) and
  `features/F-001..F-008` (customer reviews, dynamic landing page, secure social-login keys, customer profile
  update, seller customer management, product search, dynamic recommendations, store traffic usage).
- **State**: 2 commits, nothing started; module names (`seller-ui`, `search-service`, `analytics-service`)
  are aspirational. When an idea becomes work, the plan goes to `cvhome/.agents/plans/<name>.md` and the
  ideation row gets a link and status, not the other way round.

## public-dkr — public ECR mirror (kind: mirror)

- **What**: one workflow, `.github/workflows/push-images.yml`: a matrix of `registry/image:tag` pulled from Docker
  Hub or gcr.io and pushed to `public.ecr.aws/<alias>/<image>:<tag>` (alias `b2i4h4k9`), creating the ECR
  public repo if needed. Runs on push to `main` and manually. Needs the repo's `AWS_ACCESS_KEY_ID` /
  `AWS_SECRET_ACCESS_KEY` secrets (us-east-1).
- **Matrix today**: `node:20.15.0-alpine`, `node:20-slim`, `postgres:15-alpine`,
  `ashraf1abdelrasool/saas-gateway:sha-8eed986`, `otel/opentelemetry-collector-contrib:0.139.0`,
  `openzipkin/zipkin:3`, `paketobuildpacks/ubuntu-noble-run-tiny:0.0.67`,
  `paketobuildpacks/builder-noble-java-tiny:latest`, `gcr.io/distroless/nodejs20:latest`.
- **Consumers**: `cvhome/store-core/console-ui/Dockerfile` (node alpine), `cvhome/store-pod/landing-ui/Dockerfile`
  (distroless nodejs20), `cvhome/store-pod/spg/{Dockerfile,compose.yml}` (saas-gateway), buildpack run/builder
  images via `bootBuildImage`. `contract-check.py public-ecr` verifies every `FROM public.ecr.aws/...` in cvhome
  is in the matrix.
- **Rule**: the matrix is the only record of what the public registry holds. `README.md` lists two images; trust the
  workflow.

## certmagic-s3 — Caddy certificate storage plugin (kind: plugin, Go)

- **What**: org fork of the certmagic generic-S3 storage backend, moved to `aws-sdk-go-v2`. Registers Caddy
  `storage s3 { bucket region prefix endpoint }` (`storage.go` `UnmarshalCaddyfile`; default prefix
  `certmagic`), with `io.go`/`s3.go` doing get/put/list/stat/delete and locking. Optional client-side
  secretbox encryption per the README.
- **Consumer**: compiled into `saas-gateway` (`xcaddy build --with github.com/cvhome-saas/certmagic-s3`); used by
  `cvhome/store-pod/spg/Caddyfile` `storage s3 { bucket {$CERT_BUCKET} region {$CERT_BUCKET_REGION} }` so every
  spg task in a pod shares on-demand certificates through the per-pod cert bucket that
  `cvhome-platform/modules/store-pod/storage.tf` creates and grants.
- **Build**: `.github/workflows/go-build.yml` builds only. `go.mod` pins caddy 2.7.6, Go 1.23 (toolchain
  1.24.2); the real build is saas-gateway's Go 1.25.

## e2e-testing — Playwright suite (kind: tool)

- **What**: Playwright ≥1.57 scaffold: `playwright.config.ts` (chromium project, html reporter, retries on CI,
  no `baseURL`), `tests/example.spec.ts` (hits playwright.dev), `.github/workflows/playwright.yml` (push/PR,
  `npx playwright test`, uploads the report). No app journeys yet.
- **Role**: browser **correctness** regression for cvhome flows (login, storefront, checkout, console). Performance
  and web vitals stay in `load-testing/k6/scripts/browser/`; human QA scripts stay in `cvhome/<service>/qa/`.
- **Run**: `npm i && npx playwright install --with-deps && npx playwright test`, against `lcl start -d` in
  `cvhome` with `baseURL` from env / `lcl urls`.

## assets — evaluation install (kind: docs)

- **What**: `fast-run/fast-run.sh` (root-only: writes `/etc/hosts`, pulls images, runs the compose file) and
  `fast-run/docker-compose.yml`, served raw from GitHub and linked by the docs site as the quick start.
- **State**: describes the 1.0.x layout (`core-auth`, `store-ui`, `welcome-ui`, `merchant-ui`, `order`, RabbitMQ,
  MinIO, registry `public.ecr.aws/g0a5h6c1/1691275173`) — hosts and services that the current catalog does not
  have. A refresh must be generated from `common-config.yml`, `configure-domain.sh`, `docker-compose-lcl.yml`
  and the images cvhome's public-ECR workflow publishes, and tested on a clean Docker host.

## dot-github — org profile (`.github` repo, kind: docs)

- **What**: `profile/README.md`, the text shown on github.com/cvhome-saas (what cvhome is, what the org holds,
  link to the docs site). Checked out as `dot-github/` because a dotfile directory would be invisible in listings.
- **Rule**: keep its claims consistent with `repos.yaml` and the docs site; community-health defaults for all
  repos (issue templates, CODEOWNERS) would live here if introduced.

## shopizer — upstream (kind: upstream, read-only)

- **What**: Shopizer 3.2.7 (Java 17, Maven; `sm-core`, `sm-core-model`, `sm-core-modules`, `sm-shop`,
  `sm-shop-model`), the codebase cvhome evolved from. Branch `3.2.7`.
- **Use**: reference for domain concepts and legacy behaviour when a cvhome module still mirrors it (merchant store,
  catalog, order, customer). Nothing is built, tested or deployed from it, and it is never edited.
