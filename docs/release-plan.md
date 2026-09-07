# Release and versioning plan for cvhome-saas

Status: **approved 2026-09-07**, simplified the same day: one version everywhere, a git tag and a GitHub
release per repo, images built by the platform from the tag. Replaces cvhome's old `release.yml` /
`suggested-version.sh` / `develop`-branch process entirely.

## What was wrong

| Fact | Where | Consequence |
|---|---|---|
| Environments deployed image tag **`latest`** (`"image_tag": "latest"` from the bootstrap; `main.tf` fell back to it) | `cvhome-platform/bootstrap/bootstrap.yaml`, `main.tf` | No environment could say which version it ran; a re-deploy picked up whatever `main` built last |
| CodeBuild `2-images` built the app's **branch** and Gradle tagged images **only `latest`** | `bootstrap.yaml` ImagesProject, `cvhome/build-logic/.../docker-conventions.gradle` | The version in `gradle.properties` never reached an image name |
| cvhome's release workflow bumped `gradle.properties`, cut release branches and PR'd into a `develop` branch that no longer exists | `cvhome/.github/workflows/release.yml` | Releases were manual, rare, and the process was broken |
| `cvhome-platform` had no tags; the image/plugin repos published `latest` or `sha-<short>` | `git tag` in each | Nothing recorded which platform, gateway binary or collector a given app version ran with |

## The model

1. **One version everywhere.** SemVer `X.Y.Z`. Every repo with `tag: true` in `repos.yaml` (`cvhome`,
   `cvhome-platform`, `lcl`, `saas-gateway`, `caddy-domainlookup`, `certmagic-s3`, `aws-otel-collector`)
   gets the **same** tag `vX.Y.Z` on `main` on the same day, whether or not it changed. Compatibility is
   then a tautology: version X of anything works with version X of everything else.
2. **The tag is the version; no file carries it.** `gradle.properties` is `0.0.0-SNAPSHOT` forever; the
   platform's CodeBuild checks cvhome out at `vX.Y.Z` and passes `-Pversion=X.Y.Z`, and Gradle tags images
   `X.Y.Z`, `X.Y`, `latest`. A snapshot build tags only `latest`, so a branch build can never overwrite a
   release.
3. **A release is one button** in the orchestrator: version decided from cvhome's merged PR labels
   (`warn/*` → major, `type/enhancement` / `feat:` → minor, else patch) or given explicitly; every repo must
   be green on `main`; the cross-repo contract check must pass; then tag + GitHub release (generated notes)
   in every repo, a manifest `releases/vX.Y.Z.yaml` here, and the dev promotion PR.
4. **Promotion is a diff.** `envs/<env>.tfvars` `image_tag = "X.Y.Z"` in cvhome-platform is what an
   environment runs; the platform pipeline builds the app at that tag and applies. Dev is promoted
   automatically by the release; staging and prod by a PR a person merges. Rollback is the same PR with the
   older version. `latest` is refused on protected flavours.
5. **Nothing publishes from GitHub Actions in cvhome.** `saas-gateway` and `aws-otel-collector` keep pushing
   `sha-<short>` on `main` for testing; on a `vX.Y.Z` tag their existing workflow also pushes `X.Y.Z` (a
   `type=semver` line in `docker/metadata-action`). `public-dkr` mirrors the released `X.Y.Z` to public ECR;
   cvhome pins `saas-gateway:X.Y.Z`.
6. **First aligned version: `2.0.0`**, then normal bumps.

Rolling repos (`load-testing`, `e2e-testing`, `public-dkr`, `assets`, `cvhome-saas.github.io`,
`dot-github`, `ideation`, `orchestrator`) are not tagged; `main` is the release. The manifest records the
`load-testing` / `e2e-testing` commits the version was validated with.

## Release day

```
gh workflow run release-product.yml -R cvhome-saas/orchestrator -f bump=auto      # or -f version=2.0.0
```

Output: tags and releases in seven repos, `releases/v2.1.0.yaml`, the dev promotion PR merged. Then
`gh workflow run promote.yml -f version=2.1.0 -f env=staging`, and prod the same way. Hotfix: merge the fix,
run with `bump=patch`.

## Migration

| # | Repo | Change | State |
|---|---|---|---|
| 1 | `cvhome` | version from the tag; `createImageTags` → `X.Y.Z`, `X.Y`, `latest`; old release and publish workflows and `suggested-version.sh` deleted; no publish workflow | [cvhome#334](https://github.com/cvhome-saas/cvhome/pull/334) merged |
| 2 | `cvhome-platform` | `image_tag` in every `envs/*.tfvars`, no `latest` fallback, guard on protected flavours; bootstrap `ImageTag` parameter, CodeBuild builds the app at `v<ImageTag>` with `-Pversion`; CI compares against cvhome at the same tag | [cvhome-platform#2](https://github.com/cvhome-saas/cvhome-platform/pull/2) merged |
| 3 | `orchestrator` | `release-product.yml`, `promote.yml`, `scripts/release.py`, `releases/`, `docs/releasing.md`, `contract-check release`; GitHub App secrets | on `main`; App secrets pending |
| 4 | all tagged repos | first release `2.0.0`; promote dev → staging → prod | after 1–3 merge |
| 5 | `saas-gateway`, `aws-otel-collector` | `type=semver` tags in the existing docker-publish workflow so a `vX.Y.Z` tag also pushes `X.Y.Z` | small PRs |
| 6 | `public-dkr` | mirror `saas-gateway:X.Y.Z` (matrix entry per release, or a `repository_dispatch` handler) | small PR |
| 7 | `cvhome`, `cvhome-platform` | pin `saas-gateway:X.Y.Z` in `spg/Dockerfile`, `spg/compose.yml`, `docker-compose-lcl.yml`; `services.yaml` collector `aws-otel-collector:X.Y.Z`; `saas-gateway/Dockerfile` plugin pins `@vX.Y.Z` | removes the last `latest` / `sha-` pins |
| 8 | `lcl` | `publish.yml` sets the npm version from the tag; `package.json` → `0.0.0`; version test rewritten | last hand-bumped file |
| 9 | `cvhome-platform` | `envs/ephemeral.tfvars` (or flavour fallback) so ephemeral envs do not inherit dev's pin; ECR `image_tag_mutability = IMMUTABLE` for `X.Y.Z` | follow-ups flagged in #2 |

## Decisions taken

- Lockstep tags on every tagged repo, including no-op tags. Simplicity over per-repo cadence.
- `2.0.0` as the first aligned version.
- A GitHub App (not a PAT) for the cross-repo tagging.
- Dev promotion auto-merged; staging and prod by hand.
