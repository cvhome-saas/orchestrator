# Releasing — runbook

Design: `docs/release-plan.md`. One version for every repo; a tag and a GitHub release each; the platform
builds images from the tag.

## Release

```bash
gh workflow run release-product.yml -R cvhome-saas/orchestrator -f bump=auto      # or patch|minor|major
gh workflow run release-product.yml -R cvhome-saas/orchestrator -f version=2.0.0  # explicit (the cut-over)
gh run watch -R cvhome-saas/orchestrator
```

What happens: version from cvhome's merged PR labels (or the input) → every tagged repo must be green on
`main` and must not already carry the tag → contract check → `vX.Y.Z` tag + GitHub release with generated
notes in every repo listed by `scripts/release.py tagged-repos` → `releases/vX.Y.Z.yaml` committed here →
`promote: dev -> X.Y.Z` PR in cvhome-platform, auto-merged when green. Nothing to release (only
`ignore-changelog` PRs since the last tag) stops the run.

Dry run: `scripts/release.py next-version --json` shows the last tag, the PRs and the bump it would pick.

## Promote / roll back

```bash
gh workflow run promote.yml -R cvhome-saas/orchestrator -f version=2.1.0 -f env=staging   # a person merges the PR
gh workflow run promote.yml -R cvhome-saas/orchestrator -f version=2.0.3 -f env=prod      # rollback = older version
```

Merging changes `envs/<env>.tfvars image_tag`; the platform pipeline checks cvhome out at that tag, builds
the images with `-Pversion`, and applies.

## Hotfix

Merge the fix to `main`, release with `bump=patch`, promote. Staging keeps its version until promoted.

## One-time setup

1. GitHub App "cvhome-release" on the org: Contents read/write, Pull requests read/write; install on every
   repo with `tag: true` in `repos.yaml`. Store `RELEASE_APP_ID` and `RELEASE_APP_PRIVATE_KEY` in the
   orchestrator's Actions secrets.
2. Enable "Allow auto-merge" on `cvhome-platform` so the dev promotion PR merges itself.
3. Copy `cvhome/.github/release.yml` (labels → changelog sections) into the other tagged repos so the
   generated notes look the same.
4. Merge cvhome#334 and cvhome-platform#2, then release `version=2.0.0`.
