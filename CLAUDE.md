# cvhome-saas orchestrator

This directory is the **organisation root** for https://github.com/cvhome-saas (repo
`cvhome-saas/orchestrator`), not a project. Sessions start here and stay here: the agent never needs to
be re-launched inside a sub-repo. It routes each task to the right checkout and works there by absolute
path (`cd <repo> && …` inside one Bash call, `git -C <repo> …`). Each
subdirectory is an independent git repository with its own rules. This repo tracks only `repos.yaml`,
`scripts/`, the routing skills under `.agents/skills/` (linked from `.claude/skills/`) and this file.

**Start every task with the `org-router` skill.** It classifies the ask, names the owning repo(s) and hands
off to `backend-task` (cvhome), `infra-task` (cvhome-platform + saas-gateway / caddy-domainlookup /
aws-otel-collector), `tools-task` (lcl, load-testing), `docs-task` (cvhome-saas.github.io, ideation) or
`cross-repo-change` (several), and acts as **reviewer** through `cross-repo-review` for any change in any repo
(`scripts/impact.py` + `scripts/contract-check.py`). Its `references/` hold the deep repo map, the cross-repo contract table, the
known documentation drift and the shipping recipe.

| Repo | Kind | One line |
|---|---|---|
| `cvhome/` | app | Spring Boot services + Angular console + Next.js storefront; source of truth for services and ports (`common-config.yml`) |
| `cvhome-platform/` | infra | Terraform + CloudFormation bootstrap for ECS Fargate; `services.yaml` mirrors the app catalog |
| `lcl/` | tool | Public npm CLI that runs the local stack from `lcl.yml` |
| `load-testing/` | tool | k6 suite against an lcl stack or AWS |
| `saas-gateway/` | image | Caddy binary/image that `cvhome/store-pod/spg` builds FROM (via public-dkr) |
| `caddy-domainlookup/` | plugin | Caddy middleware compiled into saas-gateway |
| `aws-otel-collector/` | image | ADOT collector config for AWS environments |
| `cvhome-saas.github.io/` | docs | Public VitePress site (stale) |
| `e2e-testing/` | tool | Playwright browser regression suite (scaffold) |
| `certmagic-s3/` | plugin | Caddy S3 certificate storage compiled into saas-gateway |
| `public-dkr/` | mirror | Pushes Docker Hub / gcr images to the org's public ECR; the allow-list of base images |
| `assets/` | docs | `fast-run.sh` one-command evaluation install, served raw from GitHub |
| `dot-github/` | docs | Org profile README (`.github` repo) |
| `ideation/` | ideas | Product backlog as Markdown |

Rules that hold everywhere:

- **One repo per commit.** A change that spans repos is an ordered series of PRs (`cross-repo-change`).
- **Read the target repo's `AGENTS.md`/`CLAUDE.md` before editing it.** `cvhome`, `lcl` and `load-testing`
  keep their rules in `AGENTS.md`; auto-loading from this root is not guaranteed.
- **Sub-repo skills are reachable from here.** Claude Code lists them directory-scoped
  (`cvhome/.claude/skills/project-structure`, `load-testing/.claude/skills/k6`,
  `cvhome-platform/.claude/skills/terraform-*`); invoke them with the Skill tool when working under that path.
- **`cvhome` edits go in a worktree**, never its primary checkout. `.claude/hooks/subrepo-guard.mjs` here
  re-applies cvhome's own worktree and push guards when you work from this root.
- **Nothing is deployed from `cvhome`'s CI**; images build in CodeBuild and Terraform applies. Do not add
  deploy steps to the app repo.
- **Never read secret values** (`aws secretsmanager get-secret-value`, `.env` files with real keys).
- **Every repo is live.** A push to `main` in the image and mirror repos publishes; `assets/` is served raw
  from GitHub the moment it moves.
- **Checkouts are managed, not assumed.** `repos.yaml` holds every repo URL; `scripts/clone.sh <repo>`
  clones a missing one or fetches and reports behind/ahead. Run it for each repo a task touches before
  reading code there. `scripts/status.sh` shows all of them.
- **Every change is reviewed across repos before its PR** (`cross-repo-review`): what a cvhome port, env,
  route, image pin or SLO change does to cvhome-platform, load-testing, lcl, the image repos, and vice
  versa. `scripts/contract-check.py` alone is the standing audit; it also runs nightly in this repo's CI.
- **Multi-repo work is split into one work item per repo**, independent ones in parallel subagents, and
  shipped as one PR per repo (`org-router` step 4, `references/shipping.md`). PRs are opened, never merged,
  unless the user says so.
