# cvhome-saas orchestrator

Organisation checkout for [github.com/cvhome-saas](https://github.com/cvhome-saas): a multi-tenant
e-commerce SaaS (Java / Spring Boot, Angular, Next.js) on AWS ECS Fargate, plus the tools around it.

```
orchestrator/                this repo: manifest, scripts, agent routing skills
├── cvhome/                  application monorepo
├── cvhome-platform/         Terraform + CloudFormation bootstrap
├── lcl/                     @cvhome-saas/lcl local stack runner (npm)
├── load-testing/            k6 suite
├── e2e-testing/             Playwright browser regression suite
├── saas-gateway/            Caddy image behind the pod edge (spg)
├── caddy-domainlookup/      Caddy plugin: host → tenant headers
├── certmagic-s3/            Caddy plugin: certificates in S3
├── aws-otel-collector/      ADOT collector image for AWS
├── public-dkr/              mirror of base images into the org's public ECR
├── assets/                  fast-run.sh one-command evaluation install
├── cvhome-saas.github.io/   public docs site
├── dot-github/              org profile (.github repo)
└── ideation/                product backlog
```

Each subdirectory is its own git repository and is git-ignored here. `repos.yaml` lists every org repo
with its kind, what it is used for, and the files to open first.

```bash
scripts/clone.sh          # clone or fetch every org repo
scripts/clone.sh cvhome   # just one
scripts/status.sh         # branch, ahead/behind, dirty count per checkout
scripts/contract-check.py # do the copies of each cross-repo contract still agree? (nightly in CI too)
scripts/impact.py <repo>  # what a change in <repo> can break elsewhere, and which checks/questions apply
scripts/standard-check.py # which repos follow the org repo standard (templates/repo)
scripts/new-repo.sh       # create a new org repo from the standard and register it here
```

## Working with AI agents here

Start Claude Code in this directory and describe the task; you do not navigate into a sub-repo yourself.

`CLAUDE.md` and `.agents/skills/` make this directory usable as a Claude Code project root. The
`org-router` skill sends a task to the right repo and to that repo's own conventions; the per-area skills
(`fullstack-task`, `infra-task`, `tools-task`, `docs-task`, `cross-repo-change`) and `cross-repo-review` is
the reviewer that looks across repos before a PR and audits drift after merges say how to work there and what
must follow in the other repos. `.claude/hooks/subrepo-guard.mjs` re-applies cvhome's worktree and push
guards when editing from this root.

How the pieces fit:

```
caddy-domainlookup + certmagic-s3 ─► saas-gateway image ─► public-dkr mirror ─► cvhome/store-pod/spg ─┐
aws-otel-collector image ──────────────────────────────────────────────────────┤
cvhome (services, common-config.yml, images) ──────────────────────────────────┴─► cvhome-platform (services.yaml, Terraform, CodeBuild)
cvhome/lcl.yml ─► lcl runs the local stack ─► load-testing measures it
```
