# Releasing — runbook

Design: `docs/release-plan.md`. A release is a **compatibility record**: the same `vX.Y.Z` tag and a GitHub
release in every tagged repo, plus a manifest here. It deploys nothing.

## Release

```bash
gh workflow run release-product.yml -R cvhome-saas/orchestrator -f bump=auto      # or patch|minor|major
gh workflow run release-product.yml -R cvhome-saas/orchestrator -f version=2.1.0  # explicit
gh run watch -R cvhome-saas/orchestrator
```

What happens: version from cvhome's merged PR labels (or the input) → every tagged repo must be green on
`main` and must not already carry the tag → contract check → `vX.Y.Z` tag + GitHub release with generated
notes in every repo listed by `scripts/release.py tagged-repos` → `releases/vX.Y.Z.yaml` committed here.
Nothing to release (only `ignore-changelog` PRs since the last tag) stops the run.

Dry run: `scripts/release.py next-version --json` shows the last tag, the PRs and the bump it would pick.

## Deploying

Not here. Which version an environment runs is cvhome-platform's concern (`envs/<env>.tfvars` `image_tag`
and the bootstrap stack's `ImageTag`); see its README. `scripts/contract-check.py --only release` only
reports which released version each environment names.

## One-time setup

1. GitHub App "cvhome-release" on the org: Contents read/write, Pull requests read/write; installed on every
   repo with `tag: true` in `repos.yaml`. Secrets `RELEASE_APP_ID` and `RELEASE_APP_PRIVATE_KEY` on this repo.
2. Copy `cvhome/.github/release.yml` (labels → changelog sections) into the other tagged repos so the
   generated notes look the same.
