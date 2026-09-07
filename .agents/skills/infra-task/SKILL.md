---
name: infra-task
description: How to execute an infrastructure or platform task for cvhome-saas - Terraform and CloudFormation in cvhome-platform (ECS Fargate, Cloud Map, ALB/NLB, Route53/ACM, RDS, CloudFront/S3, IAM, CodeBuild pipeline, flavours, hibernation, autoscaling, services.yaml catalog, cost, "why is dev/prod failing"), plus the three helper image/plugin repos (saas-gateway Caddy image, caddy-domainlookup middleware, aws-otel-collector ADOT config). Use after org-router sends the task to infra, or when the task names AWS, Terraform, a flavour, an env, a pod NLB, the bootstrap, or the collector. Covers the stale CLAUDE.md caveat, the drift check against the app, the deploy pipeline, secret safety and the hand-offs to cvhome.
---

# Infra task → `cvhome-platform/` (+ helper images)

Repo: `/Volumes/Disk/IdeaProjects/cvhome-saas/cvhome-platform`. Read `README.md` and `CLAUDE.md`, but know
that **`CLAUDE.md`'s status claims are stale** (it says the repo is empty; it is a ~6k-line applied stack).
Use it for the locked decisions and design rules only. The implementation record is
`.claude/plans/infra-implementation-plan.md`; the architecture is `docs/infra-target-architecture.html`.

## 1. Orient (five minutes, every time)

```bash
cd /Volumes/Disk/IdeaProjects/cvhome-saas/cvhome-platform
git status && git log --oneline -10          # the stack is being debugged live; recent commits are the context
sed -n 1,80p services.yaml                   # the catalog: core/pod/infra blocks
cat flavours.yaml                            # dev/staging/prod/ephemeral bundles
python3 scripts/check-catalog-drift.py       # does the catalog still match ../cvhome?
```

Where things live: env root `main.tf` (SSM config + prereq, flavour layering, guards) · `modules/network`
(VPC, subnets, optional NAT) · `modules/ecs-service` (SG, logs, task def, Cloud Map, ECS service,
autoscaling, scoped IAM — the one to touch for "every service gets X") · `modules/store-core` (`alb.tf`,
`rds.tf`, otel-collector) · `modules/store-pod` (`nlb.tf`, `rds.tf`, `storage.tf` CDN/certs/CloudFront) ·
`prereq/` (ECR repos + ACM, own state) · `bootstrap/bootstrap.yaml` (CFN: state bucket, deploy role, three
CodeBuild projects, secrets, hibernation keeper) + `guard-rules/` · `scripts/` (`hibernate.sh`, `wake.sh`,
`register-stripe-webhook.sh`, drift check) · `envs/*.tfvars` (never `region`).

## 2. Rules that bind every change

- **`services.yaml` is the catalog** and is drift-checked in CI against the app's `common-config.yml`,
  `fargate-config.yml` and every `build.gradle` `imageName`. A port, name or image change starts in `cvhome`.
- **Flavours, not flags.** A new knob goes into `flavours.yaml` with a value for all four flavours, is read
  through `local.flavour`, and is overridable via `flavour_overrides`.
- **Every variable is consumed.** Every module source is a local path. Nothing `?ref=main`.
- **Secure by default**: per-service SG on the declared port, RDS not public, IAM on real ARNs, no
  `PowerUserAccess`/`iam:*` (cfn-guard enforces it on the bootstrap).
- **Secrets**: never `get-secret-value`; bind by `arn:json-key::` from `services.yaml`; a new key is added
  to the bootstrap's secret generator, never typed into Terraform or tfvars.
- **Cost**: figures come from the AWS pricing MCP tools for one named region, never memory.
- Use the installed skills before writing HCL: `terraform-style-guide`, `terraform-test`; for the bootstrap
  `aws-cloudformation` + `validate_cloudformation_template` / `check_cloudformation_template_compliance`.
  AWS service questions: `aws-containers`, `aws-networking`, `aws-observability`, `aws-iam`, `aws-database`.

## 3. Verify

```bash
terraform fmt -recursive -check
for d in . prereq modules/network modules/ecs-service modules/store-core modules/store-pod; do (cd $d && terraform init -backend=false -input=false >/dev/null && terraform validate); done
tflint --recursive
python3 scripts/check-catalog-drift.py
cfn-lint bootstrap/bootstrap.yaml && cfn-guard validate -r bootstrap/guard-rules -d bootstrap/bootstrap.yaml   # if bootstrap touched
```

A plan against a real env needs credentials (`signing-in-to-aws`) and `-backend-config` for the state bucket;
prefer reading the PR plan comment from `terraform-validate.yml`'s `plan (dev)` job. Anything touching
`prod`/`protected` flavours, IAM, networking or deletion is confirm-first.

## 4. Deploying

There is **no** deploy in `cvhome`'s CI. The pipeline is CodeBuild, created by the bootstrap:
`1-prereq` (this repo) → `2-images` (clones `cvhome`, `bootBuildImage --publishImage`) → `3-apply` (this
repo, then Stripe webhook registration). "My change is not live" = check which stage ran, then whether the
image tag in `services.yaml` matches what `2-images` pushed. Hibernate/wake with `scripts/*.sh`. Bootstrap
edits publish to `s3://cvhome-saas/platform/bootstrap.yaml` on merge to `main`.

## 5. Helper image repos (same skill, different repo)

| Repo | Change here when | After merging to `main` |
|---|---|---|
| `saas-gateway/` | Caddy version, Go version, plugin list, runtime image | Docker Hub `sha-<short>` is published; mirror to public ECR (outside these repos) and **bump the pin** in `cvhome/store-pod/spg/Dockerfile` and `cvhome/docker-compose-lcl.yml` (a `backend-task`) |
| `caddy-domainlookup/` | The `domain_lookup` directive, cache, lookup contract with `merchant`'s `RouterController` | Rebuild `saas-gateway` (it builds the plugin from source path), then the pin bump above. Fix the Go 1.21 CI vs `go 1.23` mismatch when you are there |
| `aws-otel-collector/` | Which signals/metrics reach X-Ray/EMF/CloudWatch Logs, batch/memory limits | `:latest` moves; force a new deployment of the `otel-collector` ECS service in the env (no Terraform diff). Local dashboards are `cvhome/extra/monitoring`, a separate change |

None of the three has branch protection or a worktree rule, but every push to `main` publishes. Work on a
branch, open a PR, and say which pin/deployment must follow.

## 6. Hand back to `cvhome` when

The fix is `fargate-config.yml` defaults, `application-fargate.yml`, an env var the app reads, a health
endpoint, JVM flags in `build.gradle`, or the Caddyfile. Flag it, do not silently do it here.
