# cvhome-saas — org checkout

This directory is the **organisation root** for https://github.com/cvhome-saas, not a project. Each
subdirectory is an independent git repository with its own rules. This repo tracks only `repos.yaml`,
`scripts/`, the routing skills under `.agents/skills/` (linked from `.claude/skills/`) and this file.

**Start every task with the `org-router` skill.** It classifies the ask, names the owning repo(s) and hands
off to `backend-task` (cvhome), `infra-task` (cvhome-platform + saas-gateway / caddy-domainlookup /
aws-otel-collector), `tools-task` (lcl, load-testing), `docs-task` (cvhome-saas.github.io, ideation) or
`cross-repo-change` (several). Its `references/` hold the deep repo map, the cross-repo contract table, the
known documentation drift and the deprecated-repo list.

| Repo | Kind | One line |
|---|---|---|
| `cvhome/` | app | Spring Boot services + Angular console + Next.js storefront; source of truth for services and ports (`common-config.yml`) |
| `cvhome-platform/` | infra | Terraform + CloudFormation bootstrap for ECS Fargate; `services.yaml` mirrors the app catalog |
| `lcl/` | tool | Public npm CLI that runs the local stack from `lcl.yml` |
| `load-testing/` | tool | k6 suite against an lcl stack or AWS |
| `saas-gateway/` | image | Caddy binary/image that `cvhome/store-pod/spg` builds FROM |
| `caddy-domainlookup/` | plugin | Caddy middleware compiled into saas-gateway |
| `aws-otel-collector/` | image | ADOT collector config for AWS environments |
| `cvhome-saas.github.io/` | docs | Public VitePress site (stale) |
| `ideation/` | ideas | Product backlog as Markdown |

Rules that hold everywhere:

- **One repo per commit.** A change that spans repos is an ordered series of PRs (`cross-repo-change`).
- **Read the target repo's `AGENTS.md`/`CLAUDE.md` before editing it.** `cvhome`, `lcl` and `load-testing`
  keep their rules in `AGENTS.md`; auto-loading from this root is not guaranteed.
- **`cvhome` edits go in a worktree**, never its primary checkout. `.claude/hooks/subrepo-guard.mjs` here
  re-applies cvhome's own worktree and push guards when you work from this root.
- **Nothing is deployed from `cvhome`'s CI**; images build in CodeBuild and Terraform applies. Do not add
  deploy steps to the app repo.
- **Never read secret values** (`aws secretsmanager get-secret-value`, `.env` files with real keys).
- **Do not extend deprecated repos** (`cvhome-infra`, `cvhome-bootstrap`, `cvhome-secrets`,
  `cvhome-store-pod*`, `cvhome-common-ecs-service`, `eureka-peers`, `aws-consul`, `load-testing-x`).
- `scripts/status.sh` shows branch and dirtiness across checkouts; `scripts/clone.sh` bootstraps a new
  machine from `repos.yaml`. Check whether a checkout is behind `origin/main` before reasoning about it.
