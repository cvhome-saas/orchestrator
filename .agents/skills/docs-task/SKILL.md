---
name: docs-task
description: How to execute a documentation or product-idea task for cvhome-saas - the public VitePress site (cvhome-saas.github.io), the ideation backlog (feature docs F-001..), org-level docs (this repo's README, repos.yaml), and where in-repo docs belong (AGENTS.md, skill references, qa/*.md, docs/*.md in each repo). Use after org-router sends the task to docs, or when the task is "document", "write up", "update the site", "add an idea / feature request", "the docs are wrong", or a README change. Decides which repo owns the words and which source of truth to write from.
---

# Docs / ideas task

## Who owns the words

| Doc | Repo and path | Source of truth to write from |
|---|---|---|
| Public site (guides, architecture, deployment) | `cvhome-saas.github.io/docs/**` (VitePress; sidebar in `docs/.vitepress/config.mts`) | `cvhome/.claude/skills/project-structure/SKILL.md` + `references/`, `cvhome-platform/README.md` + `docs/infra-target-architecture.html`, `cvhome-platform/services.yaml` |
| How to run locally | `cvhome/README.md`, `cvhome/qa/lcl-qa.md`, `references/qa-testing.md`; the site's `development/local-setup.md` mirrors it | `cvhome/lcl.yml`, `lcl/README.md` |
| Per-service behaviour, endpoints, QA | `cvhome/<service>/qa/<svc>-qa.md`, `<service>/http/*.http`, the skill references | the service code |
| Agent rules for a repo | that repo's `AGENTS.md` / `CLAUDE.md` / `.agents/skills/*` | the repo's own scripts, hooks, CI |
| Infra design and decisions | `cvhome-platform/CLAUDE.md` (decisions), `docs/infra-target-architecture.html`, `.claude/plans/*` | `main.tf`, modules, bootstrap |
| Load numbers and coverage | `load-testing/docs/{baseline,coverage,prometheus}.md`, `README.md` | `results/`, `k6/lib/clients` |
| Product ideas, missing features | `ideation/README.md` table + `features/F-NNN-<slug>.md` | the existing F-docs template |
| Org overview, repo list, routing | this repo: `README.md`, `repos.yaml`, `.agents/skills/org-router/references/*` | `gh repo list cvhome-saas`, each repo's entry docs |
| Org profile on github.com/cvhome-saas | `dot-github/profile/README.md` | the docs site and `repos.yaml` |
| One-command evaluation install | `assets/fast-run/{fast-run.sh,docker-compose.yml}` (served raw from GitHub, linked by the site) | `cvhome/docker-compose-lcl.yml`, `common-config.yml`, `public-dkr` matrix for image names |

## Rules

- **Write from the code, not from older docs.** The public site is a year stale and names retired repos and
  services (`known-drift.md` in `org-router`). Before editing a page, decide
  whether it should exist; deleting a wrong deployment guide beats polishing it.
- **In-repo docs travel with the code**: a change to behaviour updates the doc in the same PR in the same
  repo. Never document a cvhome behaviour in the org repo or the site only.
- **Skill references are docs too.** If `project-structure` lags (e.g. missing `billing`/`pod-registry`),
  fix it in `cvhome/.claude/skills/project-structure/` and mirror `.agents/skills/project-structure/`.
- **Ideation → work**: when an idea is picked up, write the plan at `cvhome/.agents/plans/<name>.md` (or the
  owning repo), then update the ideation row (status, link). Map its aspirational names to real modules
  (`seller-ui` → `console-ui`, `catalog-service` → `store-pod/catalog`).
- Diagrams: Mermaid in Markdown for the site (`vitepress-plugin-mermaid`); the platform's draw.io source is
  `cvhome-saas.github.io/docs/digrams/aws-arch.drawio` (misspelled dir, keep the path or move it with a redirect).

## assets / fast-run

`fast-run.sh` is what a stranger runs first. It must only name services, hosts and images that exist today
(`common-config.yml`, `configure-domain.sh`, images published by cvhome's public-ECR workflow). Test it on a
clean Docker host before pushing; the raw URL is live the moment `main` moves.

## Public site workflow

```bash
cd /Volumes/Disk/IdeaProjects/cvhome-saas/cvhome-saas.github.io
npm ci && npm run docs:dev        # http://localhost:5173
npm run docs:build                # what deploy.yml runs on push to main → GitHub Pages
```

Push to `main` deploys. Use a branch + PR; a broken build takes the site down.

## Ideation workflow

Copy the template from `ideation/README.md` ("Submit an idea") into `features/F-<next>-<slug>.md`, add the
table row, keep Ticket/Assignee `TBD` until a plan exists. Two commits in this repo's history; no CI.
