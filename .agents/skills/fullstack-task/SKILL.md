---
name: fullstack-task
description: How to execute a full-stack application task in the cvhome monorepo - Java 25 / Spring Boot services, Angular 20 console-ui and uaa-fe, Next.js 16 landing-ui and its themes, uaa/cua auth, tenancy, catalog, checkout, payment, DDL, .http files, tests, Gradle/npm build, common-config / lcl-config / fargate-config slices, lcl.yml, docker-compose files, extra/monitoring, the spg Caddyfile, cvhome CI. Use after org-router sends the task to cvhome/, or whenever the task names a cvhome service, module, endpoint, screen, page, component, theme or config slice. Enforces the worktree-per-change rule, the plan-as-phases rule, the design gate (a new screen starts in the design portal and needs an approved record before any Angular/Next.js page file), the QA file rule, the per-repo skills to load, the verification gates and the hand-offs back to infra/tools/docs.
---

# Full-stack application task → `cvhome/` (Java + Angular + Next.js)

Repo: `/Volumes/Disk/IdeaProjects/cvhome-saas/cvhome`. Its rules are **`AGENTS.md`** (enforcement) and the
**`project-structure`** skill at `.claude/skills/project-structure/SKILL.md` (rulebook + `references/`). Read
`AGENTS.md` now if it is not in context; `CLAUDE.md` there is only `@AGENTS.md`.

## 1. Cut the worktree before the first edit

```bash
cd /Volumes/Disk/IdeaProjects/cvhome-saas/cvhome
git fetch origin
git worktree add --no-track .claude/worktrees/<type>-<short-name> -b <type>/<short-name> origin/main
cd .claude/worktrees/<type>-<short-name>
```

`type` ∈ `feat|fix|chore|docs|refactor`. Every file, build, stack and QA lives in that worktree. The
primary checkout stays on a clean `main`. This is enforced by `cvhome/.claude/hooks/worktree-guard.mjs`,
and the org-level hook re-applies it when you edit from the org root. Plans are the exception: write
`.agents/plans/<kebab-name>.md` in the primary checkout first, then cut the worktree.

## 1b. Plan = phases, phase = PR

Anything bigger than one PR starts as `cvhome/.agents/plans/<kebab-name>.md` (written in the primary
checkout before the worktree exists; the guard allows it): context with file:line evidence, why the design
is what it is, then `## Phase N — <area> (PR N)` sections, an *Other repos* section the orchestrator picks
up, deviations as built, verification. Each phase is committed and shipped as its own PR from the same
worktree before the next starts (stack them if a later phase needs an earlier one). Reference plans:
`.agents/plans/user-impersonation.md` (four phases, four PRs), `checkout-rewrite.md` (§ 11 Phasing).

## 1c. Design gate — a new screen starts in the design portal

Before creating any **new** page or screen (an Angular feature component under `console-ui/src/app/features/`
or `uaa-fe`, a Next.js `page.tsx` in `landing-ui`), and before a plan phase that adds a route is
implemented:

1. Produce the design with the orchestrator's **`design` skill** (Claude Design canvas): every state the
   screen has — empty, loading, error, populated — and the interactions, in the console's or storefront's
   existing design system (`console-ui/src/theme`, `ui-kit`, `landing-ui/libs/theme`).
2. The person reviews it in the artifact and says yes (or edits it there).
3. Write `.agents/designs/<slug>.md` in the worktree: `artifact:` URL, `approved: true`, `approved_by`,
   `date`, the states and decisions. `<slug>` is the feature directory name (`orders`, `store-management`)
   or the Next.js route directory; one record may `covers: [a, b]` several screens.
4. Only then implement. The `design-guard.mjs` hook refuses a new page file without the record
   (`SKIP_DESIGN_GATE=1` is the person's escape hatch). Editing an existing screen is not gated, but a
   redesign of one goes through the same portal step.
5. The QA case for the screen (`<service>/qa/<svc>-qa.md`, or `console-ui/qa/console-ui-qa.md`) tests the
   states the record names.

## 1d. QA is a file that travels with the change

Every user-visible or operator-visible behaviour gets a case in the owning service's `qa/<svc>-qa.md`
(entry point of the flow; cross-reference the others by path), tagged `[verified]` with what verified it
(date + stack, or an `e2e-testing` spec) or `[not verified]`. Copy the structure of
`store-core/billing/billing-service/qa/billing-qa.md`; the rules are `references/qa-testing.md` § 7. QA
proves tenant isolation and the permission gate, not just the happy path. Say in the PR body which cases
are `[not verified]`; never imply coverage. Cross-repo QA and release QA: orchestrator
`org-router/references/qa.md`.

## 2. Load the right in-repo skill

| Task shape | Skill in `cvhome/.claude/skills/` | Reference to open |
|---|---|---|
| Any navigation, new service/module, endpoint, DDL, secret, discovery, event | `project-structure` | `references/new-service.md`, `api-conventions.md`, `database-schemas.md`, `secrets-encryption.md`, `service-to-service.md`, `events-outbox.md` |
| Error handling | `project-structure` | `references/error-handling.md` (mandatory before touching exceptions) |
| Angular `console-ui`, `uaa-fe`, `ui-kit` | `angular-developer` | `references/frontends.md` |
| Next.js `landing-ui`, themes | `vercel-react-best-practices`, `shadcn` | `references/landing-ui.md`, `new-landing-ui-template.md` |
| A new screen or page, a redesign | orchestrator `design` skill (§ 1c), then `angular-developer` / `vercel-react-best-practices`, `impeccable` for polish | `.agents/designs/README.md` |
| Running / QA / reproducing | `project-structure` | `references/qa-testing.md`, `qa/lcl-qa.md`, `<service>/qa/<svc>-qa.md`, `<service>/http/*.http` |
| `lcl.yml` changes | `lcl-stack-builder` | `references/gateways-and-local-domains.md` |
| Observability, dashboards | — | `extra/monitoring/docs/`, `.agents/plans/observability-dashboards.md`, `common-config.yml` otel block |

Known gaps in the skill (see org `known-drift.md`): `billing` 8021 and `pod-registry` 8022 are missing from its
store-core table; trust `settings.gradle` and `common-config.yml`.

## 3. What every change must satisfy (from `AGENTS.md`)

- Endpoint: `StoreMerchantId` + `LanguageCode` params, `@PreAuthorize("hasPermission(...)")`, a `case` in
  `CustomPermissionEvaluator`, a block in `<service>/http/<api-class>.http` addressed through the gateway,
  a case in `<service>/qa/<svc>-qa.md`, i18n keys in every locale.
- Persistence: `schema.sql`/`init-sql` edited with the entity; enum values in the `CHECK`; store-scoped queries.
- Config: ports/hosts only from `common-config.yml`; versions only from `gradle/libs.versions.toml`; a new
  service registered in `settings.gradle`, `common-config.yml`, `lcl-config.yml`, `fargate-config.yml`,
  `lcl.yml`, and its edge route.
- Errors: condition-named exceptions, `ProblemDetailFactory`, one `@ControllerAdvice`, us/peer/provider split.
- No `TODO`, no star import, no 140+ char line, no hardcoded URL, no plaintext secret.

## 4. Verify, then ship

```bash
./gradlew checkstyleMain checkstyleTest checkstyleIntegrationTest
./gradlew build -x test -x check
./gradlew test                       # or :path:to:module:test
./gradlew integrationTest            # Docker; if wiring/SQL/HTTP/security touched
cd store-core/console-ui && npm run build && npm run lint   # for a touched -ui module
lcl start -d --stack <short-name> && lcl urls --stack <short-name>   # exercise the change end to end
extra/scripts/verify-before-push.sh  # writes the receipt the push hook demands
```

Then `/go` (commit → push → PR into `main` with the template and a `type/*` label). Never push to `main`,
never `--no-verify`. After merge: `lcl stop --stack <short-name>`, `git worktree remove`, delete the branch.

## 5. Hand-offs you must announce, not do here

- New/renamed service, port, image name, env var, secret → `cvhome-platform/services.yaml` (+ bootstrap for a
  new secret key). Use `cross-repo-change`.
- A new endpoint that matters under load → `load-testing` client + `docs/coverage.md`.
- `lcl` misbehaving (not your `lcl.yml`) → `tools-task`.
- Anything user-facing in the public docs site → `docs-task`.
