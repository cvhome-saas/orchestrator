# cvhome-saas orchestrator

Organisation checkout for [github.com/cvhome-saas](https://github.com/cvhome-saas): a multi-tenant
e-commerce SaaS (Java / Spring Boot, Angular, Next.js) on AWS ECS Fargate, plus the tools around it.

```
orchestrator/                this repo: manifest, scripts, agent routing skills
├── cvhome/                  application monorepo
├── cvhome-platform/         Terraform + CloudFormation bootstrap
├── lcl/                     @cvhome-saas/lcl local stack runner (npm)
├── load-testing/            k6 suite
├── saas-gateway/            Caddy image behind the pod edge (spg)
├── caddy-domainlookup/      Caddy plugin used by saas-gateway
├── aws-otel-collector/      ADOT collector image for AWS
├── cvhome-saas.github.io/   public docs site
└── ideation/                product backlog
```

Each subdirectory is its own git repository and is git-ignored here. `repos.yaml` lists every org repo
with kind, status (`active` / `deprecated` / `reference`) and entry docs.

```bash
scripts/clone.sh          # clone or fetch every active repo
scripts/clone.sh --all    # also deprecated/reference repos, for history
scripts/status.sh         # branch, ahead/behind, dirty count per checkout
```

## Working with AI agents here

Start Claude Code in this directory and describe the task; you do not navigate into a sub-repo yourself.

`CLAUDE.md` and `.agents/skills/` make this directory usable as a Claude Code project root. The
`org-router` skill sends a task to the right repo and to that repo's own conventions; the per-area skills
(`backend-task`, `infra-task`, `tools-task`, `docs-task`, `cross-repo-change`) say how to work there and what
must follow in the other repos. `.claude/hooks/subrepo-guard.mjs` re-applies cvhome's worktree and push
guards when editing from this root.

How the pieces fit:

```
caddy-domainlookup + certmagic-s3 ─► saas-gateway image ─► cvhome/store-pod/spg ─┐
aws-otel-collector image ──────────────────────────────────────────────────────┤
cvhome (services, common-config.yml, images) ──────────────────────────────────┴─► cvhome-platform (services.yaml, Terraform, CodeBuild)
cvhome/lcl.yml ─► lcl runs the local stack ─► load-testing measures it
```
