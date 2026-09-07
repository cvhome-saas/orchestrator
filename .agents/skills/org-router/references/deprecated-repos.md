# Deprecated and reference-only repos in github.com/cvhome-saas

Never extend these. Clone one only to read history (`scripts/clone.sh --all`). If a doc or a plan still
points at one, the fix is to repoint it at the replacement below, in the repo that owns the doc.

| Repo | Was | Replaced by | Notes |
|---|---|---|---|
| `cvhome-infra` | Terraform for the core cluster | `cvhome-platform` (`modules/store-core`, `modules/network`) | Knew 11 of 15 services, four under stale names |
| `cvhome-bootstrap` | CloudFormation bootstrap (1275 lines) | `cvhome-platform/bootstrap/bootstrap.yaml` | Random 4-char project id was the root of the image-path mismatch |
| `cvhome-store-pod`, `cvhome-store-pod-infra` | Per-pod Terraform | `cvhome-platform/modules/store-pod` | |
| `cvhome-secrets` | Secrets Terraform | bootstrap CFN + Secrets Manager (`/{project}/{env}/{stripe,uaa,sso}`) | Dropped entirely |
| `cvhome-common-ecs-service` | Shared ECS service module | `cvhome-platform/modules/ecs-service` | Plan said "keep external, tag-pinned"; reality absorbed it. `cvhome-platform/CLAUDE.md` still says the former |
| `cvhome-ecs-fargate-infra` | Named in the docs site | `cvhome-platform` | Does not exist in the org any more; docs site is wrong |
| `eureka-peers`, `aws-consul` | Discovery experiments | Cloud Map + `ecs-service-discoveryclient` (`cvhome/store-commons/ecs-commons`) | Private repos |
| `load-testing-x` | First k6 attempt | `load-testing` | |
| `e2e-testing` | TypeScript e2e suite (2026-01) | nothing yet | Not wired to the current stack. Browser QA today is manual (`cvhome` `references/qa-testing.md`) and k6 browser scripts (`load-testing/k6/scripts/browser/`) |
| `certmagic-s3` | Fork of the certmagic S3 storage plugin | still used | Built into `saas-gateway`; `saas-gateway/README.md` wrongly names the upstream `techknowlogick/certmagic-s3` |
| `public-dkr` | Public image mirroring | unknown | Probably the missing Docker Hub → public ECR step for `saas-gateway`; unverified |
| `assets` | Static assets, `fast-run.sh` | | Referenced by the docs site's local-setup page |
| `shopizer` | Upstream fork | | History only |

Services that no longer exist but appear in old docs/plans: `seller-ui` (→ `console-ui` :8011),
`store-ui`, `welcome-ui`, `merchant-ui`, `control-plane` (→ `tenancy` :8020, with subscriptions split into
`billing` :8021 and pods into `pod-registry` :8022), `content-deprecated`.
