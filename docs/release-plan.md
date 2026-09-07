# Release and versioning plan for cvhome-saas

Status: **approved 2026-09-07** (lockstep product ring, first aligned version 2.0.0, GitHub App for cross-repo tagging, dev promotion auto-merged); implementation tracked in the migration table. Replaces cvhome's current `release.yml` / `suggested-version.sh` /
`develop`-branch process entirely; nothing below assumes it.

## What is wrong today (the facts the plan answers)

| Fact | Where | Consequence |
|---|---|---|
| Environments deploy image tag **`latest`** (`"image_tag": "latest"` written to SSM by the bootstrap; `main.tf` falls back to it) | `cvhome-platform/bootstrap/bootstrap.yaml:325`, `main.tf:62` | No environment can say which cvhome version it runs; a re-deploy silently picks up whatever `main` built last; rollback is "rebuild an older commit" |
| CodeBuild `2-images` builds the app repo's **branch** and Gradle tags images **only `latest`** (`createImageTags` returns `[latest]`) | `bootstrap.yaml` ImagesProject, `cvhome/build-logic/.../docker-conventions.gradle:48` | Same as above; the version in `gradle.properties` (1.0.16) never reaches an image name |
| cvhome's GitHub releases exist (1.0.14 … 1.0.16) but the workflow that makes them bumps `gradle.properties`, cuts a release branch, and PRs into a `develop` branch that no longer exists | `cvhome/.github/workflows/release.yml` | Releases are manual, occasional (Apr, Apr, Aug), and the process is broken |
| `cvhome-platform` has **no tags at all**; `saas-gateway`, `aws-otel-collector`, `caddy-domainlookup`, `certmagic-s3` publish/consume by **`latest`** or **`sha-<short>`**, never a version | `git tag` in each; `services.yaml:261` (`:latest`); `spg/Dockerfile` (`sha-8eed986`) | Nothing records which platform, gateway binary or collector config a given app version was validated with; the collector changes production on the next task restart with no diff |
| `lcl` is the only repo with a real release: tag `v<version>` → npm OIDC publish, version duplicated in `package.json` + `src/version.ts` | `lcl/.github/workflows/publish.yml` | Fine, but a bump is a hand-edited commit in two files |
| PR titles already follow `<type>: …` and cvhome's `.github/release.yml` builds notes from `type/*` labels | `cvhome/AGENTS.md`, `.github/release.yml` | The inputs for automatic version bumps and changelogs already exist |

## Goals

1. **One version scheme, one source.** SemVer `X.Y.Z`; the git tag `vX.Y.Z` on `main` is the version. No
   commit exists only to bump a number; build files read the tag.
2. **Immutable, traceable artifacts.** Every image is tagged with its version and a digest is recorded.
   No environment deploys `latest`.
3. **One button.** A product release is one `workflow_dispatch` in the orchestrator; everything else is
   triggered by the tag it creates. The bump (major/minor/patch) is computed from the merged PRs' labels
   and can be overridden.
4. **Aligned by construction.** The two repos that must match (`cvhome`, `cvhome-platform`) carry the
   *same* version and are tagged together, after the contract check passes at that pair. Everything
   else is pinned in a release manifest the orchestrator writes.
5. **Promotion is a diff.** Which version an environment runs is a line in `envs/<env>.tfvars`, changed
   by a PR (auto for dev, human-merged for staging/prod).

## The version model

Three rings, by how tightly a repo is coupled to the product.

| Ring | Repos | Versioning | Tagged by |
|---|---|---|---|
| **Product** | `cvhome`, `cvhome-platform` | **Lockstep.** One product version `X.Y.Z`; both repos get the same tag on the same day, even when one has no changes (a no-op tag is cheaper than a compatibility matrix) | the orchestrator release workflow |
| **Component** | `lcl`, `saas-gateway`, `caddy-domainlookup`, `certmagic-s3`, `aws-otel-collector` | **Independent SemVer.** Each releases on its own cadence; the product manifest pins the version it was validated with | each repo's own `release` workflow (same shape) |
| **Rolling** | `load-testing`, `e2e-testing`, `public-dkr`, `assets`, `cvhome-saas.github.io`, `dot-github`, `ideation`, `orchestrator` | **`main` is the release.** No tags; `load-testing` and `e2e-testing` record in the product manifest the commit they validated the release with | nobody |

Bump rules, identical in every tagged repo, derived from the PRs merged since the last tag:

| Merged PR carries | Bump |
|---|---|
| label `warn/api-change`, `warn/behavior-change`, or title `<type>!:` | **major** |
| label `type/enhancement`, or title `feat:` | **minor** |
| anything else (`fix:`, `chore:`, `docs:`, `type/bug`, …) | **patch** |
| only `ignore-changelog` PRs, or no PRs | no release (workflow says so and stops) |

The label set is cvhome's existing `.github/release.yml`; the same file is copied to every tagged repo
so GitHub's auto-generated release notes look the same everywhere. Until 1.0 of the product ring, `major`
is downgraded to `minor` (SemVer 0.x rules) — but the product is past 1.0 already (`1.0.16`), so the first
aligned release is **`2.0.0`**: a clean break from the old scheme, and `cvhome-platform` gets its first tag
at the same number.

## Where the version lives in each repo (no bump commits)

| Repo | Today | After |
|---|---|---|
| `cvhome` | `gradle.properties` `version=1.0.16`, hand-bumped | `gradle.properties` says `version=0.0.0-SNAPSHOT` forever. CI and CodeBuild pass `-Pversion=<tag without v>`; local builds stay `0.0.0-SNAPSHOT`. `createImageTags` returns `[X.Y.Z, X.Y, latest]` when the version is not a SNAPSHOT, `[latest]` otherwise |
| `cvhome-platform` | none | Nothing in files. The tag is the version; `envs/<env>.tfvars` `image_tag = "X.Y.Z"` is *which product version the env runs*, not the repo's own version |
| `lcl` | `package.json` + `src/version.ts`, hand-bumped, test enforces equality | `package.json` stays `0.0.0`; `publish.yml` runs `npm version <tag> --no-git-tag-version` and generates `src/version.ts` from it before `npm publish`. The equality test moves to "version.ts is generated, never edited" |
| `saas-gateway`, `aws-otel-collector` | Docker Hub `latest` + `sha-<short>` on every push to `main` | Push to `main` keeps publishing `sha-<short>` (for testing). A tag `vX.Y.Z` publishes `X.Y.Z`, `X.Y` and `latest`. Consumers pin `X.Y.Z` |
| `caddy-domainlookup`, `certmagic-s3` | Go modules consumed at `@latest` of `main` by `xcaddy` | Tag `vX.Y.Z` (Go modules are tag-versioned natively). `saas-gateway/Dockerfile` pins `--with github.com/cvhome-saas/caddy-domainlookup@vX.Y.Z` |

## The release manifest

The orchestrator repo gains `releases/vX.Y.Z.yaml`, written by the release workflow and committed:

```yaml
product: 2.0.0
date: 2026-09-14
cvhome:            { tag: v2.0.0, commit: bc1bc44b }
cvhome-platform:   { tag: v2.0.0, commit: f52c1338 }
images:                                    # what CodeBuild / CI pushed for this tag
  store-core/uaa:      { tag: 2.0.0, digest: sha256:… }
  store-pod/spg:       { tag: 2.0.0, digest: sha256:…, base: saas-gateway:1.4.0 }
  …
components:                                # pinned versions the product was validated with
  saas-gateway:        1.4.0
  caddy-domainlookup:  0.3.0
  certmagic-s3:        0.2.1
  aws-otel-collector:  1.1.0
  lcl:                 0.2.0
validated_by:
  load-testing:  { commit: 5b1c…, profile: smoke, baseline: docs/baseline.md }   # filled by the k6 run
  e2e-testing:   { commit: null }                                                # until it has journeys
contract_check: pass                        # scripts/contract-check.py at the tag pair
```

The manifest is the only place where "what does version 2.0.0 consist of" is answered, and
`scripts/contract-check.py` gains a `release` check: every pin in the newest manifest exists as a tag /
image, every `envs/*.tfvars` `image_tag` names a manifest that exists, and cvhome's `spg` FROM pin and
`services.yaml`'s collector image match the manifest's component versions (no more `latest`, no more
`sha-`).

## The one button: `orchestrator` → `Release product`

`.github/workflows/release-product.yml`, `workflow_dispatch` with inputs `bump` (`auto` | `patch` | `minor`
| `major`) and `version` (optional explicit override, e.g. the `2.0.0` cut-over).

```
 1. clone cvhome + cvhome-platform at main               scripts/clone.sh
 2. compute next version                                   last tag of cvhome  +  bump from merged PR labels since it
 3. gate: contract check at the pair                       scripts/contract-check.py  → any FAIL aborts the release
 4. gate: both repos' CI green on main                     gh run list --branch main --status success
 5. tag cvhome vX.Y.Z, tag cvhome-platform vX.Y.Z          via a GitHub App token (GITHUB_TOKEN cannot trigger other repos)
 6. create both GitHub releases                            gh release create --generate-notes
 7. wait for cvhome's on-tag workflow                      builds + pushes images X.Y.Z to ECR (private and public), records digests as a release asset
 8. write releases/vX.Y.Z.yaml, commit to orchestrator     components = latest tag of each component repo, or explicit inputs
 9. open PR in cvhome-platform: envs/dev.tfvars image_tag = "X.Y.Z"   auto-merge on green (dev is the canary)
10. post a summary: versions, digests, links, and the staging/prod promotion PRs still to open
```

Promotion to staging / prod is the same PR shape against `envs/staging.tfvars` / `envs/prod.tfvars`, opened
by a second small workflow (`Promote` with inputs `version`, `env`) or by hand, and merged by a person. The
`3-apply` CodeBuild stage (already triggered by the platform pipeline) deploys the pinned tag. Rollback is the
same PR with the previous version.

What the app's on-tag workflow does (replaces `on-tag-publishing-to-private-ecr.yml` and the public one):
checkout the tag → `./gradlew bootBuildImage --publishImage -Pversion=X.Y.Z -x test -x check` to private ECR
and public ECR → `docker buildx imagetools inspect` each image → upload `images.json` (name, tag, digest) as a
release asset. CodeBuild `2-images` stays for environments that build from a branch (ephemeral flavour), but
gets `-Pversion=$IMAGE_TAG` too so a branch build never overwrites a released tag.

## Component releases: the same shape, five times

One reusable workflow in the orchestrator (`.github/workflows/release-component.yml`, `workflow_call`), used
by every component repo's `release.yml` with a `workflow_dispatch: bump` input:

```
compute next version from labels  →  tag vX.Y.Z  →  gh release --generate-notes  →  publish:
   saas-gateway / aws-otel-collector : docker build, push X.Y.Z + X.Y + latest to Docker Hub
                                       → repository_dispatch to public-dkr { image, tag }   (mirror without editing the matrix by hand)
   caddy-domainlookup / certmagic-s3  : nothing to publish (Go module = tag); the workflow only checks `go build` at the tag
   lcl                                : existing npm OIDC publish, version from the tag
```

`public-dkr` gains a `repository_dispatch` handler that appends the `{image, tag}` to the matrix (a bot
commit) and runs the mirror. The matrix stays the record of what public ECR holds; the bot commit keeps it
true without a human editing YAML.

After a component release the orchestrator's **standing audit** (nightly `contract-check.yml`) reports
"component X released 1.5.0, product manifest pins 1.4.0" as a WARN. Picking it up is a normal PR in the
consumer (`cvhome` spg pin; `cvhome-platform` collector image; `saas-gateway` plugin pins) reviewed by
`cross-repo-review`, and the next product release records the new pin.

## What a release day looks like

```
gh workflow run release-product.yml -R cvhome-saas/orchestrator -f bump=auto
   → "2.1.0: 3 features, 5 fixes. Tagged cvhome v2.1.0, cvhome-platform v2.1.0. Images pushed (15). Manifest
      releases/v2.1.0.yaml committed. Dev promotion PR cvhome-saas/cvhome-platform#41 merged. To promote:
      gh workflow run promote.yml -f version=2.1.0 -f env=staging"
```

Hotfix: merge the fix PR to `main`, run the same button with `bump=patch`. Because images are immutable and
promotion is per-env, staging can sit on 2.1.0 while dev runs 2.1.1.

## Migration, in order (each step is one PR, each leaves things working)

| # | Repo | Change | Why first |
|---|---|---|---|
| 1 | `cvhome` | `createImageTags` → `[version, major.minor, latest]` unless SNAPSHOT; `gradle.properties` → `0.0.0-SNAPSHOT`; `-Pversion` accepted; delete `release.yml`, `suggested-version.sh`, the two ECR publish workflows; add `on-tag` publish workflow with digest asset; copy nothing else | Everything downstream needs versioned images |
| 2 | `cvhome-platform` | `bootstrap.yaml`: `image_tag` in SSM defaults to the newest product tag, not `latest`; `envs/*.tfvars` gain `image_tag`; `2-images` passes `-Pversion=$IMAGE_TAG`; `contract-check`'s drift job also runs at tag pairs | Environments become pinnable |
| 3 | `orchestrator` | GitHub App (or fine-grained PAT) with `contents: write` on the product + component repos; `release-product.yml`; `releases/` dir; `contract-check.py release` check; `docs/releasing.md` runbook | The button |
| 4 | `orchestrator` + `cvhome` + `cvhome-platform` | Cut **v2.0.0** with `version=2.0.0`. Promote dev, then staging, then prod by PR | First aligned release; proves the whole path |
| 5 | `orchestrator` | `release-component.yml` (reusable) | Shared shape for the five component repos |
| 6 | `saas-gateway`, `aws-otel-collector` | `release.yml` calling the reusable workflow; docker-publish keeps `sha-` on push; `.github/release.yml` labels copied | Versioned images |
| 7 | `public-dkr` | `repository_dispatch` handler that appends to the matrix and mirrors | Mirror without hand edits |
| 8 | `caddy-domainlookup`, `certmagic-s3` | First tags `v0.1.0`; `saas-gateway/Dockerfile` pins `@v0.1.0`; fix the Go 1.21 CI mismatch while there | Reproducible Caddy binary |
| 9 | `cvhome` | Replace `spg` pins (`sha-8eed986` / `sha-4a6d381`) with `saas-gateway:1.0.0` from public ECR in Dockerfile, `spg/compose.yml` and `docker-compose-lcl.yml`; `services.yaml` collector image → `aws-otel-collector:1.0.0` | Kills the last `latest` / `sha-` in production paths |
| 10 | `lcl` | `publish.yml` sets version from the tag; `package.json` → `0.0.0`; version test rewritten | Last hand-bumped file gone |
| 11 | `load-testing` | `bin/k6run` stamps the product version (`gh release view` on cvhome, or `lcl`'s image tag) into the `TESTID` tags; the release workflow triggers a smoke run and writes `validated_by` | Baselines become per-version |
| 12 | `cvhome-saas.github.io`, `dot-github` | A "Releases" page that renders `releases/*.yaml` from the orchestrator | People can see what 2.1.0 is |

Steps 1–4 are the minimum that delivers the goals; 5–10 remove the remaining mutable pins; 11–12 are
visibility.

## Decisions to confirm

- **Lockstep for the product ring** (a no-op platform tag per release) versus letting the platform version
  drift and pinning it in the manifest. Lockstep is proposed: it makes "does platform X work with app X"
  a tautology and keeps the promotion PR a single number.
- **First aligned version `2.0.0`** versus continuing at `1.0.17`. `2.0.0` is proposed because the scheme,
  the platform, and the image naming all change at once.
- **Auth for cross-repo tagging**: a GitHub App owned by the org (recommended, scoped, no personal token)
  versus a fine-grained PAT in the orchestrator's secrets.
- **Auto-merge the dev promotion PR** (proposed) or require a click even for dev.
