# Releasing — runbook

The design is `docs/release-plan.md`. This is what to type.

## Product release (cvhome + cvhome-platform, lockstep)

```bash
gh workflow run release-product.yml -R cvhome-saas/orchestrator -f bump=auto      # or patch|minor|major
gh workflow run release-product.yml -R cvhome-saas/orchestrator -f version=2.0.0  # explicit (the cut-over)
gh run watch -R cvhome-saas/orchestrator
```

What happens: version decided from merged PR labels → both repos must be green on `main` → contract check →
tags `vX.Y.Z` + GitHub releases in both repos → cvhome's `release-images.yml` publishes `X.Y.Z` images and an
`images.json` asset → `releases/vX.Y.Z.yaml` committed here → `promote: dev -> X.Y.Z` PR in cvhome-platform,
auto-merged when green. Nothing to release (only `ignore-changelog` PRs) stops the run with exit 3.

Dry run locally: `scripts/release.py next-version --json` shows the last tag, the PRs and the bump it would pick.

## Promote / roll back

```bash
gh workflow run promote.yml -R cvhome-saas/orchestrator -f version=2.1.0 -f env=staging   # opens the PR; a person merges
gh workflow run promote.yml -R cvhome-saas/orchestrator -f version=2.0.3 -f env=prod      # rollback = older version
```

Merging the PR changes `envs/<env>.tfvars image_tag`; the platform pipeline applies it.

## Component release (saas-gateway, aws-otel-collector, caddy-domainlookup, certmagic-s3, lcl)

```bash
gh workflow run release.yml -R cvhome-saas/saas-gateway -f bump=auto
```

Each repo's `release.yml` calls the reusable `release-component.yml` here. Docker components publish
`X.Y.Z`, `X.Y`, `latest` to Docker Hub and dispatch `public-dkr` to mirror `X.Y.Z`. Go plugins only get the
tag. lcl's own `publish.yml` runs on the release event. Consumers pick the new version up by PR
(`cross-repo-review` will flag the pin), and the next product release records it.

## Hotfix

Merge the fix to `main`, run the product release with `bump=patch`, promote. Images are immutable and
promotion is per environment, so staging keeps its version until promoted.

## One-time setup (before the first run)

1. GitHub App "cvhome-release" on the org: permissions Contents read/write, Pull requests read/write,
   Workflows read/write (tags must trigger `release-images.yml`); install on `cvhome`, `cvhome-platform`,
   `public-dkr`. Store `RELEASE_APP_ID`, `RELEASE_APP_PRIVATE_KEY` in the orchestrator's Actions secrets.
   The same App token works as `MIRROR_DISPATCH_TOKEN` for the component repos.
2. Enable "Allow auto-merge" on `cvhome-platform` (Settings → General) so the dev promotion PR merges itself.
3. Copy `cvhome/.github/release.yml` (label → changelog section) into every tagged repo.
4. Merge migration steps 1 and 2 (cvhome `chore/release-by-tag`, cvhome-platform `chore/release-by-tag`).
5. Run the product release with `version=2.0.0`.
