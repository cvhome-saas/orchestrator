# Cross-repo contracts — one fact, several copies

Each row is a fact that lives in one place and is copied elsewhere. Change the owner first, then every
copy, in separate PRs per repo, producers before consumers. CI catches only the rows marked *checked*.

| Fact | Owner (edit first) | Copies to update | Checked? |
|---|---|---|---|
| Service exists, its name, port, namespace, which edge fronts it | `cvhome/store-commons/autoconfigure/src/main/resources/common-config.yml` | `cvhome/.../lcl-config.yml`, `.../fargate-config.yml` (`service-ports`, `eager-load.clients`), `cvhome/settings.gradle`, `cvhome/lcl.yml`, edge route (`GatewayRouteLocatorImpl` `backendServices` or `store-pod/spg/Caddyfile`), `cvhome-platform/services.yaml`, `load-testing/k6/config/env/lcl.json` + a client in `k6/lib/clients/`, `cvhome/.claude/skills/project-structure/SKILL.md` table, `configure-domain.sh` hosts | services.yaml ↔ app: **yes** (`scripts/check-catalog-drift.py`, CI job `catalog-drift`). Others: no |
| Image name a service is built as | `cvhome/<service>/build.gradle` `imageName = createImageName("…")` | `cvhome-platform/services.yaml` `image:` | yes (drift check) |
| Runtime env a service needs on Fargate (`SPRING_CLOUD_ECS_DISCOVERY_NAMESPACE[_ID]`, `UAA_*`, `CUA_*`, `MANAGEMENT_*`, spg's `NAMESPACE`/`ASK_TLS_URL`/`DOMAIN_LOOKUP_URL`/`CERT_BUCKET*`/`ACME_CA_URL`, crypto keys) | `cvhome` (`fargate-config.yml`, `application-fargate.yml`, Caddyfile `{$VAR}`) | `cvhome-platform/services.yaml` `extra_env`/`secrets`, `modules/store-core/main.tf`, `modules/store-pod/main.tf` | no |
| Secret keys (`/{project}/{env}/sso` json keys etc.) | `cvhome-platform/bootstrap/bootstrap.yaml` (`SsoSecretsFunction`) | `services.yaml` `secrets:` `arn:json-key::` bindings; the app env var names above | no |
| Caddy binary features (plugins, Go/Caddy version) | `saas-gateway/Dockerfile` (+ `caddy-domainlookup`, `certmagic-s3`) | `public-dkr` matrix entry (what exists in public ECR), `cvhome/store-pod/spg/Dockerfile` + `spg/compose.yml` FROM pin, `cvhome/docker-compose-lcl.yml` image pin | `contract-check.py spg-image` — pins are manual and currently differ (`sha-8eed986` on AWS/mirror vs `sha-4a6d381` local) |
| Which images exist at `public.ecr.aws/b2i4h4k9` | `public-dkr/.github/workflows/push-images.yml` matrix | every `FROM public.ecr.aws/b2i4h4k9/...` in `cvhome` (console-ui, landing-ui, spg), buildpack run images | `contract-check.py public-ecr` |
| Caddy `storage s3` options | `certmagic-s3/storage.go` (`bucket`, `region`, `prefix`, `endpoint`) | `cvhome/store-pod/spg/Caddyfile` storage block, `cvhome-platform/modules/store-pod/storage.tf` bucket + task IAM | no |
| Caddyfile directives the plugin understands (`domain_lookup`, `lookup_url`, `cache_ttl`) | `caddy-domainlookup/domainlookup.go` | `cvhome/store-pod/spg/Caddyfile` | no |
| Domain → store lookup and TLS ask endpoints | `cvhome/store-pod/merchant/.../RouterController.java` | Caddyfile `ask {$ASK_TLS_URL}` and `domain_lookup lookup_url`; platform env values | no |
| OTLP endpoint and which signals/metrics survive | `aws-otel-collector/otel-config.yaml` (AWS) / `load-testing/stack/monitoring/otel-collector.yml` (local) | `cvhome-platform/services.yaml` `infra.otel-collector` ports, `modules/*/main.tf` `OTEL_EXPORTER_OTLP_ENDPOINT`; `cvhome/common-config.yml` otel block (`disabled.keys`, protocol); `load-testing/stack/docker-compose.yml` collector ports | load-testing CI validates the **local** collector config (`make monitoring-check`) |
| Whether telemetry is on per environment | `cvhome-platform/flavours.yaml` `monitoring` | `OTEL_SDK_DISABLED`, `MANAGEMENT_OTLP_METRICS_EXPORT_ENABLED` computed in `modules/*/main.tf`; cvhome dev default is off (`otel.sdk.disabled: true`); `load-testing/stack/docker-compose.yml` turns it on | no |
| HTTP latency SLO buckets | `cvhome/common-config.yml` `http.server.requests` SLO list | `load-testing/k6/config/thresholds.js`, `load-testing/stack/monitoring/scripts/dashboards.spec.mjs` (load-testing dashboard) | `contract-check.py slo` |
| Local hostnames, demo stores, pod id `507f1f77`, service ports | `cvhome/common-config.yml`, `lcl.yml`, `extra/scripts/configure-domain.sh` | `load-testing/stack/docker-compose.yml` (network aliases, ports, `SPRING_APPLICATION_JSON`), `load-testing/stack/stack.sh hosts`, `k6/config/env/local.json`, `k6/data/seed-org1-store1.json` | `contract-check.py catalog` (ports) · `make selftest` fails loudly |
| `lcl.yml` schema (keys, `version: 1`) | `lcl/schema/lcl.schema.json` | `cvhome/lcl.yml`, the `lcl-stack-builder` skill copies in `lcl/` and `cvhome/`, `lcl/templates`, `lcl/examples` | `lcl validate`; `lcl/test/examples.test.ts` |
| Public architecture story | `cvhome/.claude/skills/project-structure/`, `cvhome-platform/docs/infra-target-architecture.html` | `cvhome-saas.github.io/docs/**`, `cvhome/README.md` | no — the docs site is a year stale |
| Rate limits, paging, sort conventions, trial caps | `cvhome` service code | `load-testing/AGENTS.md` "facts that shaped the suite" | no |
| Local infra images (`postgres`, `minio`) and the registry they come from | `cvhome/docker-compose-lcl.yml` | `cvhome/store-commons/test-support/.../containers/{Postgres,Minio}TestConfiguration.java` `IMAGE` (CI's Testcontainers), `load-testing/stack/docker-compose.yml`; `assets/fast-run/docker-compose.yml` is 1.0.x drift | `contract-check.py infra-images` — the pins agree, and none is on a registry that stopped serving it (`DEAD_IMAGES`: Docker Hub `minio/minio` since 2026-09, `bitnami/*` since 2025-09). A cached image hides a dead registry locally; the first clean pull (CI, a new laptop) finds it |
| The sku format (`^[A-Za-z0-9_-]{1,255}$`, case kept, never trimmed) | `cvhome/store-commons/commons/.../domain/Sku.java` `Sku.FORMAT`, enforced at every catalog, inventory and checkout edge | `cvhome/store-core/console-ui` `SKU_PATTERN` (product form, variants step), `load-testing/k6/data/*.json` seed skus, `load-testing/k6/lib/fixtures` + `journeys/admin` generators (`K6-SKU-…`, `K6-EDIT-…`) | `contract-check.py sku-format` (console-ui patterns and seed skus; the generators are proved by `make selftest`) |

## Recipes

**New backend service** (the full list is `cvhome/.claude/skills/project-structure/references/new-service.md`):
1. `cvhome` worktree: module + `settings.gradle`, `common-config.yml` + `lcl-config.yml` + `fargate-config.yml`,
   `lcl.yml`, edge route, permissions, `.http`, `qa/<svc>-qa.md`, tests, `imageName`. PR.
2. `cvhome-platform`: `services.yaml` entry (port, image, database, runtime, size, edge, secrets), run
   `python3 scripts/check-catalog-drift.py`, `terraform fmt/validate`, PR. ECR repo comes from `prereq/`.
3. `load-testing`: client in `k6/lib/clients/`, `lcl.json` if a new host, `docs/coverage.md` row, `make selftest`.
4. Docs: project-structure table (cvhome), docs site if public-facing.

**Change a port**: same list, owner first; the drift check will block the platform PR until the app PR is on
the compared branch (`APP_REF`), so land the app side first or point `APP_REF` at the branch.

**New env var or secret for a service**: `cvhome` reads it (config slice) → `cvhome-platform` supplies it
(`services.yaml` `extra_env`/`secrets`, bootstrap if a new secret key). Never a value in git.

**Rebuild the Caddy edge**: `caddy-domainlookup` / `certmagic-s3` (if plugin change) → push `saas-gateway`
main (publishes `sha-<short>` to Docker Hub) → add that tag to the `public-dkr` matrix and push main (mirrors to
public ECR) → bump the pins in `cvhome` (`store-pod/spg/Dockerfile`, `store-pod/spg/compose.yml`,
`docker-compose-lcl.yml`) → QA `spg` locally (`qa/lcl-qa.md`, custom-domain flow) → nothing to do in
`cvhome-platform` (the spg image is built from the app repo by CodeBuild).

**Bump a base image** (node, postgres, otel-contrib, paketo): `public-dkr` matrix first, then the `FROM` /
compose line in `cvhome`, then `e2e-testing`/`load-testing` if they pin the same tag.

**Move a local infra image** (postgres, minio; a new tag or a registry that stopped serving it): `cvhome`
`docker-compose-lcl.yml` and the matching Testcontainers `*TestConfiguration.IMAGE` in one commit (a non-Docker
Hub name for a Testcontainers module needs `asCompatibleSubstituteFor`), then `load-testing/stack/docker-compose.yml`.
Prove the pull on a clean registry fetch, not a cached image; `contract-check.py infra-images` confirms the three
agree. The 2026-09-12 MinIO move (cvhome#351, load-testing#10) is the worked example.

**Change what telemetry reaches CloudWatch**: `aws-otel-collector/otel-config.yaml` → push main (`:latest`
moves) → force a new ECS deployment of `otel-collector` in `cvhome-platform` (no Terraform diff on `:latest`;
say so). The local collector and the dashboards are a separate `load-testing/stack/monitoring` change.

**A perf finding**: `load-testing` (`docs/baseline.md`, a script, run on `make stack-up`) → fix in `cvhome` → resize in
`cvhome-platform` (`flavours.yaml` sizes / `services.yaml` `size`, rds `db_pool_size`) → re-measure on the same stack.
