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
| OTLP endpoint and which signals/metrics survive | `aws-otel-collector/otel-config.yaml` (AWS) / `cvhome/extra/monitoring/logging-otel-collector-config.yml` (local) | `cvhome-platform/services.yaml` `infra.otel-collector` ports, `modules/*/main.tf` `OTEL_EXPORTER_OTLP_ENDPOINT`; `cvhome/common-config.yml` otel block (`disabled.keys`, protocol) | cvhome CI validates the **local** collector config only |
| Whether telemetry is on per environment | `cvhome-platform/flavours.yaml` `monitoring` | `OTEL_SDK_DISABLED`, `MANAGEMENT_OTLP_METRICS_EXPORT_ENABLED` computed in `modules/*/main.tf`; local default is off (`otel.sdk.disabled: true`), load overlay turns it on | no |
| HTTP latency SLO buckets | `cvhome/common-config.yml` `http.server.requests` SLO list | `load-testing/k6/config/thresholds.js`, `cvhome/extra/monitoring/grafana/dashboards/load-testing` | no |
| Local hostnames, demo stores, pod id `507f1f77` | `cvhome/lcl.yml`, `extra/scripts/configure-domain.sh`, `docker-compose-lcl.yml` | `load-testing/k6/config/env/lcl.json`, `k6/data/seed-org1-store1.json`, `docker-compose-load.yml` network aliases | `make selftest` fails loudly |
| `lcl.yml` schema (keys, `version: 1`) | `lcl/schema/lcl.schema.json` | `cvhome/lcl.yml`, the `lcl-stack-builder` skill copies in `lcl/` and `cvhome/`, `lcl/templates`, `lcl/examples` | `lcl validate`; `lcl/test/examples.test.ts` |
| Public architecture story | `cvhome/.claude/skills/project-structure/`, `cvhome-platform/docs/infra-target-architecture.html` | `cvhome-saas.github.io/docs/**`, `cvhome/README.md` | no — the docs site is a year stale |
| Rate limits, paging, sort conventions, trial caps | `cvhome` service code | `load-testing/AGENTS.md` "facts that shaped the suite" | no |

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

**Change what telemetry reaches CloudWatch**: `aws-otel-collector/otel-config.yaml` → push main (`:latest`
moves) → force a new ECS deployment of `otel-collector` in `cvhome-platform` (no Terraform diff on `:latest`;
say so). Local dashboards are a separate `cvhome/extra/monitoring` change.

**A perf finding**: `load-testing` (`docs/baseline.md`, a script) → fix in `cvhome` → resize in
`cvhome-platform` (`flavours.yaml` sizes / `services.yaml` `size`, rds `db_pool_size`) → re-measure.
