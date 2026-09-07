---
name: cross-repo-change
description: Executes a cvhome-saas change that spans two or more repos - a new or renamed service, a port change, a new env var or secret a service needs on AWS, a Caddy/spg image rebuild and pin bump, a telemetry change that touches app + collector + platform, a load-test finding that needs app and infra fixes, or a feature that needs code, infra, k6 coverage and docs. Use when org-router classifies the task as "both" / several, or when a single fact (service catalog, image name, SLO, hostname, lcl.yml schema) is copied across repos. Produces an ordered per-repo plan, one PR per repo, producers before consumers, with the CI drift check accounted for.
---

# Cross-repo change

Sub-repos are independent git repositories. There is no atomic multi-repo commit; the deliverable is an
**ordered sequence of PRs, one per repo**, each valid on its own once its predecessor merges. Read
`org-router/references/cross-repo-contracts.md` for the contract table and recipes.

## Procedure

1. **Name the fact and its owner.** Which single file is the source of truth (`common-config.yml`,
   `build.gradle` `imageName`, `saas-gateway/Dockerfile`, `otel-config.yaml`, `flavours.yaml`,
   `lcl.schema.json`, `thresholds.js` ...)? That repo goes first.
2. **List every copy** from the contracts table and grep the org to confirm:
   ```bash
   cd /Volumes/Disk/IdeaProjects/cvhome-saas
   grep -rn --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=build --exclude-dir=dist '<fact>' cvhome cvhome-platform lcl load-testing saas-gateway caddy-domainlookup aws-otel-collector cvhome-saas.github.io ideation
   ```
3. **Write the sequence** before editing, as a checklist in your reply and (for a feature) in
   `cvhome/.agents/plans/<name>.md` § "Other repos":
   ```
   1. cvhome        feat/<name>      files … gates: checkstyle, build, test, integrationTest, lcl QA, verify-before-push
   2. cvhome-platform feat/<name>    services.yaml … gates: fmt, validate, tflint, check-catalog-drift.py (APP_REF=feat/<name> until 1 merges)
   3. load-testing  feat/<name>      client, coverage.md … gates: make inspect, make selftest
   4. docs          …                
   ```
4. **Execute per repo with that repo's skill**: `backend-task`, `infra-task`, `tools-task`, `docs-task`.
   Each repo's own worktree/branch rules apply (cvhome: worktree; others: branch). Do not leave a repo
   half-done to start the next one; finish its gates, open its PR, then move on.
5. **Account for the drift check.** `cvhome-platform` CI compares `services.yaml` against the app on
   `APP_REF` (same-named branch if it exists, else trunk). Either land the app PR first, or name the platform
   branch identically to the app branch so CI compares against it, and say which you chose.
6. **Pins and mutable tags** are part of the change, not an afterthought: `spg` image `sha-` in two cvhome
   files; `otel-collector:latest` needs a forced ECS deployment; `lcl` version bump if the schema moved.
7. **Report** per repo: branch, PR link or "not opened", gates run, what remains and in which repo.

## Common sequences

- **New service**: cvhome → cvhome-platform → load-testing → docs (recipe in the contracts file).
- **Port / rename**: cvhome (config slices, `lcl.yml`, edge, skill table) → cvhome-platform → load-testing
  `lcl.json`.
- **New env var / secret**: cvhome reads it → cvhome-platform supplies it (`services.yaml`, and the bootstrap
  secret generator for a new key).
- **Edge (Caddy) change**: caddy-domainlookup → saas-gateway → (mirror) → cvhome pins + Caddyfile → QA locally.
- **Telemetry**: cvhome `common-config.yml`/`extra/monitoring` (local) ↔ aws-otel-collector (AWS filter) ↔
  cvhome-platform (`flavours.yaml` `monitoring`, collector env). Keep the local and AWS collectors' kept
  metrics in agreement or say why not.
- **Perf**: load-testing measures → cvhome fixes → cvhome-platform resizes → load-testing re-measures and
  updates `docs/baseline.md`.
- **Runner**: lcl schema change → lcl release → cvhome `lcl.yml` + vendored `lcl-stack-builder` skill.
