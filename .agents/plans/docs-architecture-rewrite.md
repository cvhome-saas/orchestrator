# Public documentation rewrite — full C4 architecture, deployment, usage, lcl, with screenshots

This is the one plan for this change, in every repo. Every work item is one PR in one repo, on the same branch
name, `docs/architecture-rewrite`. In the site repo each phase is one commit on one PR, easiest first. QA cases
live in `cvhome-saas.github.io/qa/site-qa.md` and `dot-github/qa/profile-qa.md`, never here.

## What is wrong (2026-09-20)

The public site `cvhome-saas.github.io` last had content changed 2026-05-07; most pages date from 2025-06 and
describe a layout that no longer exists: services `Control-Plane`, `StoreUI`, `Order`, `CoreGateway`; repos
`cvhome-bootstrap` and `cvhome-infra`; ALB TLS termination for stores; a local setup with no `lcl`. It never
names `cvhome-platform`, `store-core-gateway`, `console-ui`, `billing`, `pod-registry`, `tenancy`, `checkout`,
`payment`, `cua`, `inventory`, `content` or `lcl`. There is no C4 model at any level, no product screenshot,
no AWS console screenshot, and `deploy.yml` has no PR check. `assets/fast-run` is a 1.0.x compose stack
whose MinIO image 404s. The `org-router` references record the site as still linking fast-run; it does not
(the only mention is unlinked bold text on an unreachable page).

The system today: 15 services in `cvhome/store-commons/autoconfigure/src/main/resources/common-config.yml`,
two layers (store-core once: gateway 8000, uaa 8001, console-ui 8011, tenancy 8020, billing 8021, pod-registry
8022; store-pod per pod: spg 80/443, landing-ui 8110, merchant 8120, content 8121, catalog 8122, checkout 8123,
cua 8124, payment 8125, inventory 8126); ECS Fargate through `cvhome-platform` (one-click CloudFormation
bootstrap → CodeBuild `1-prereq` → `2-images` → `3-apply`); local run with `lcl start` in a cvhome checkout.

## Decisions

- **AWS screenshots come from the existing dev environment.** No fresh bootstrap; the Launch Stack and
  parameter steps are documented in prose with the legacy shots where still accurate.
- **`assets/fast-run` is retired.** lcl is the only documented local path; the script exits with a pointer.
- **Three repos are fixed**, not one: the site, the org profile, and the cvhome skill references the site is
  written from (`.claude/skills/project-structure/` is canonical at v3.3; the `.agents/skills` mirror lags in
  ~20 files and is resynced wholesale).
- **Mermaid flowcharts styled as C4**, not the beta `C4Context` grammar; one diagram per block; stroke-only
  `classDef` so dark mode stays legible. The stale `docs/digrams/aws-arch.drawio` is deleted, not redrawn.
- **Stub pages** at the five old sidebar URLs (VitePress has no redirects); unreachable pages deleted.
- **Screenshots are the last two commits**; every prose page carries an HTML comment where an image goes.

## Work items

| # | Repo | Branch | Deliverable | Gate | Depends on |
|---|---|---|---|---|---|
| 1 | `cvhome` | `docs/architecture-rewrite` (worktree) | six stale statements fixed in `.claude/skills/project-structure/references/{gateways-and-local-domains,store-pod,store-core,multi-tenancy,frontends}.md`, SKILL.md 3.4, `.agents` mirror resynced | `extra/scripts/verify-before-push.sh` | — |
| 2 | `cvhome-saas.github.io` | same (worktree) | 11 commits: tooling, information architecture, C4 L1/L2, L3, deployment views, development, guides, operations, guide+home, lcl screenshots, AWS screenshots. Phases in that repo's `.agents/plans/architecture-rewrite.md` | `scripts/verify.sh` (+ new `check-images.sh`), `qa/site-qa.md` | 1 (content) |
| 3 | `dot-github` | same | `profile/README.md`: pitch, start-here links, repo table from `repos.yaml`; `qa/profile-qa.md` | `scripts/verify.sh` | 2 merged (links) |
| 4 | `assets` | same | `fast-run/fast-run.sh` prints the retirement notice and exits 1; README banner | `scripts/verify.sh` | — |
| 5 | orchestrator | same | this plan; after merges: `known-drift.md` and `repo-map.md` entries for the site and assets | — | 2, 4 merged |

Order: 1 → 2 → (3 ∥ 4) → 5. PRs are opened, never merged, unless told.

## Screenshot procedure

- Files `docs/images/lcl/<app>-<screen>.png` and `docs/images/aws/<service>-<what>.png`; 1440×900 window,
  light theme, `sips -Z 1600`, ≤300 KB each, ≤10 MB in the PR, no GIFs. Terminal output is a fenced code
  block, never an image.
- **lcl**: the stack is shared across sessions — check `lcl status` for an owner first. `lcl start -d`,
  test-stores logins from cvhome `references/qa-testing.md`. Console at http://gateway.com:8000, uaa admin at
  http://uaa.gateway.com:8001, storefront at http://org1-store1.spg-507f1f77.gateway.com.
- **AWS**: the person signs in first; region eu-central-1. Secrets Manager and SSM are captured as lists only;
  never "Retrieve secret value". Crop or blur the account id before `git add`; look at every file.

## Deviations, as built
_Filled in while implementing._

## Verification
Per repo, the gate in the table. Site QA cases run in `npm run docs:dev` before the PR; the deployed-site case
after merge. `scripts/impact.py` and `scripts/contract-check.py` before each PR (expected SAFE: docs only).
