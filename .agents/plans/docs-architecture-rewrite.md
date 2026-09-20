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

- **Everything AWS is one phase, and it is the last one.** No fresh bootstrap: the captures come from the
  existing **dev** environment. The captures, the six legacy images and the check of the AWS pages against
  the live console all happen together, in one sitting, once a person has signed in. Every other phase can
  be written, verified and reviewed without an account, so nothing else waits on one.
- **`assets/fast-run` is retired.** lcl is the only documented local path; the script exits with a pointer.
- **Three repos are fixed**, not one: the site, the org profile, and the cvhome skill references the site is
  written from (`.claude/skills/project-structure/` is canonical at v3.3; the `.agents/skills` mirror lags in
  ~20 files and is resynced wholesale).
- **Mermaid flowcharts styled as C4**, not the beta `C4Context` grammar; one diagram per block; stroke-only
  `classDef` so dark mode stays legible. The stale `docs/digrams/aws-arch.drawio` is deleted, not redrawn.
- **Stub pages** at the five old sidebar URLs (VitePress has no redirects); unreachable pages deleted.
- **Screenshots come after the prose.** Every page carries an HTML comment where an image belongs, so the
  build and the image check stay green until a capture replaces it. The local captures are the last commit
  of the site PR; the AWS captures are work item 6.

## Work items

| # | Repo | Branch | Deliverable | Gate | Depends on |
|---|---|---|---|---|---|
| 1 | `cvhome` | `docs/architecture-rewrite` (worktree) | six stale statements fixed in `.claude/skills/project-structure/references/{gateways-and-local-domains,store-pod,store-core,multi-tenancy,frontends}.md`, SKILL.md 3.4, `.agents` mirror resynced | `extra/scripts/verify-before-push.sh` | — |
| 2 | `cvhome-saas.github.io` | same (worktree) | 12 commits: tooling, information architecture, C4 L1/L2, L3, deployment views, development, guides, operations, guide+home, lcl screenshots, the plan as built. Phases in that repo's `.agents/plans/architecture-rewrite.md` | `scripts/verify.sh` (+ new `check-images.sh`), `qa/site-qa.md` | 1 (content) |
| 3 | `dot-github` | same | `profile/README.md`: pitch, start-here links, repo table from `repos.yaml`; `qa/profile-qa.md` | `scripts/verify.sh` | 2 merged (links) |
| 4 | `assets` | same | `fast-run/fast-run.sh` prints the retirement notice and exits 1; README banner | `scripts/verify.sh` | — |
| 5 | orchestrator | same | this plan; after merges: `known-drift.md` and `repo-map.md` entries for the site and assets | — | 2, 4 merged |
| 6 | `cvhome-saas.github.io` | same branch as item 2 | **The AWS phase**, done: thirteen console captures plus two extra, five of the six `legacy-*` images replaced, the five AWS pages checked against a live dev environment, the QA case they earn | `scripts/verify.sh`, `qa/site-qa.md` | a signed-in console |

Order: 1 → 2 → (3 ∥ 4) → 5. PRs are opened, never merged, unless told. Item 6 needed an AWS account and was
held for one; the account arrived before item 2 merged, so it landed as commits on the same branch rather
than a separate pull request.

## Screenshot procedure

- Files `docs/images/lcl/<app>-<screen>.png` and `docs/images/aws/<service>-<what>.png`; 1440×900 window,
  light theme, `sips -Z 1600`, ≤300 KB each, ≤10 MB in the PR, no GIFs. Terminal output is a fenced code
  block, never an image.
- **lcl**: the stack is shared across sessions — check `lcl status` for an owner first. `lcl start -d`,
  test-stores logins from cvhome `references/qa-testing.md`. Console at http://gateway.com:8000, uaa admin at
  http://uaa.gateway.com:8001, storefront at http://org1-store1.spg-507f1f77.gateway.com.
- **AWS (work item 6, all of it in one sitting)**: the person signs in first; region `eu-central-1`, except
  the CloudFront certificate in `us-east-1`. Thirteen captures: the bootstrap stack's Outputs tab; the seven
  CodeBuild projects and the tail of a succeeded `3-apply` log; the ECS cluster list, the core services and
  one pod's services; the RDS instances; the hosted zone's records; the regional certificate; a pod's
  CloudFront distribution; Secrets Manager and Parameter Store as **names only**; the CloudWatch dashboard.
  Never open a secret's value tab. Crop or blur the account identifier before `git add`; look at every file.
  While the console is open, confirm the CloudFormation parameter list, the stack outputs, the CodeBuild
  project names, the log group naming and the dashboard sections against what the pages claim, and fix what
  the Terraform implied but the account does not show.

## Deviations, as built

- **The AWS work became its own work item (6)**, but landed on the same branch as item 2 rather than a
  separate pull request, because the account arrived before that branch merged. Grouping it still paid off:
  the console was opened once.
- **The dev environment had been destroyed**, so the phase began by rebuilding it through the pipeline. That
  rebuild doubles as evidence for the pipeline page, and it is the reason the phase took about an hour.
- **Identifiers are replaced in the page before each capture**, not blacked out. The repository text was
  grepped afterwards for the account number, the domain and the zone id: none present.
- **Four product screenshot slots were dropped** rather than filled: the pods, platform and identity admin
  screens need a platform-administrator session that would not complete, and the seeded stores carry no
  subscription, so the billing page is an empty state. The identity server's sign-in page was captured
  instead.
- **The cvhome work item became two commits**, the six corrections and then the mirror resync, because the
  `.agents` copy was already 21 files behind and a single commit would have buried the fix.
- **Two facts differed from the sources**: the storefront registers twelve themes, not thirteen, and the
  gateway's pod list comes from `pod-registry`, not tenancy.

## Verification

Per repo, the gate in the table. `scripts/impact.py` and `scripts/contract-check.py` before each PR: SAFE,
docs only, and the cvhome branch turns the standing `skill-map` warning into `OK`.

Open: cvhome#370, cvhome-saas.github.io#5, .github#3, assets#3, orchestrator#8. The site's new pull-request
build passed and correctly skipped the deploy job; cvhome's Checkstyle, unit and integration tests passed.
Site QA cases are written and `[not verified]`: they are a browser pass through `npm run docs:dev` before
merge, plus the deployed-site case after.
