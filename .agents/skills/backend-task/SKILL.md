---
name: backend-task
description: How to execute an application task in the cvhome monorepo (Java 25 / Spring Boot services, Angular console-ui, Next.js landing-ui, uaa/cua auth, tenancy, catalog, checkout, payment, DDL, .http files, tests, Gradle/npm build, common-config / lcl-config / fargate-config slices, lcl.yml, docker-compose files, extra/monitoring, the spg Caddyfile, cvhome CI). Use after org-router has sent the task to cvhome/, or whenever the task names a cvhome service, module, endpoint, screen, theme or config slice. Enforces the worktree-per-change rule, the per-repo skills to load, the verification gates and the hand-offs back to infra/tools/docs.
---

# Backend / application task → `cvhome/`

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

## 2. Load the right in-repo skill

| Task shape | Skill in `cvhome/.claude/skills/` | Reference to open |
|---|---|---|
| Any navigation, new service/module, endpoint, DDL, secret, discovery, event | `project-structure` | `references/new-service.md`, `api-conventions.md`, `database-schemas.md`, `secrets-encryption.md`, `service-to-service.md`, `events-outbox.md` |
| Error handling | `project-structure` | `references/error-handling.md` (mandatory before touching exceptions) |
| Angular `console-ui`, `uaa-fe`, `ui-kit` | `angular-developer` | `references/frontends.md` |
| Next.js `landing-ui`, themes | `vercel-react-best-practices`, `shadcn` | `references/landing-ui.md`, `new-landing-ui-template.md` |
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
