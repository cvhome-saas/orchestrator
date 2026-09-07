---
name: tools-task
description: How to execute a task on the cvhome-saas developer tools - the lcl local stack runner CLI (@cvhome-saas/lcl - commands, lcl.yml schema, supervisor, ports, Compose, health checks, npm publishing), the load-testing k6 suite (scripts, clients, journeys, thresholds, fixtures, Prometheus/Grafana wiring, make targets, baselines) and the e2e-testing Playwright suite (browser regression tests). Use after org-router sends the task to tools, or when the task names lcl (the CLI, not a project's lcl.yml), k6, load/stress/soak/breakpoint tests, TESTID, thresholds, fixtures, the load dashboard, Playwright or e2e. Separates "bug in the tool" from "bug in cvhome's use of the tool".
---

# Tools task → `lcl/`, `load-testing/` or `e2e-testing/`

## First: is it the tool or the consumer?

| Symptom | Repo |
|---|---|
| `lcl` crashes, mis-allocates ports, leaves orphans, wrong `status`, schema rejects a valid key, a new command | `lcl/` |
| cvhome's stack fails a health check, a service is missing from `lcl.yml`, hosts entries, "which port is X on" | `cvhome/` (`lcl.yml`, `qa/lcl-qa.md`, `references/qa-testing.md`) → `fullstack-task` |
| A k6 script, client, journey, threshold, fixture, the run wrapper, Grafana annotation | `load-testing/` |
| A browser regression test (does the checkout flow still work?), Playwright config/CI | `e2e-testing/` |
| k6 finds a real defect or the app needs OTEL/Hikari/metrics changes to be measurable | `cvhome/` → `fullstack-task`; note it in `load-testing/README.md` prerequisites table |
| Sizing/RDS pool after a load finding | `cvhome-platform/` → `infra-task` |

## `lcl/` — public npm CLI

Read `AGENTS.md` (the whole contributor guide) before editing. Non-negotiables it states:
- **Language-neutral engine.** No Java/Node/cvhome assumptions in `src/`.
- Config field change = 7 files in one change: `schema/lcl.schema.json`, types + parsing in `src/config.ts`,
  semantic validation, runtime consumer, `README.md`, tests, examples/templates.
- Safety boundaries (process groups, PID fingerprints, never kill a foreign listener, `clean` only an exact
  `.lcl/<stack>` with a matching sentinel, Compose ops always with the recorded project name) are not to be
  weakened for convenience.
- Version equality `package.json` == `src/version.ts` (`test/lifecycle.test.ts`). `STATE_VERSION` /
  `CONTROL_PROTOCOL_VERSION` bump on incompatible change.

```bash
cd /Volumes/Disk/IdeaProjects/cvhome-saas/lcl
npm ci && npm run check && npm test      # Docker for compose/lifecycle suites; CI_NO_DOCKER=1 otherwise
npm run build && node bin/lcl.js validate --root ../cvhome     # exercise against the real consumer
npm pack --dry-run                        # file list must contain no .lcl state
```

Feature branch + PR. **Never** `npm publish`, tag, or create a release without the maintainer saying so;
publishing is a GitHub release → `publish.yml` (npm OIDC). Bump `CHANGELOG.md`. The `lcl-stack-builder`
skill is vendored in both `lcl/.agents/skills` and `cvhome/.agents/skills`; keep them identical.

## `load-testing/` — k6 suite

Read `AGENTS.md` (architecture rules) and load the `k6` skill (`.claude/skills/k6`). Rules:
- Imports one way: `lib/core ← lib/clients ← lib/journeys ← scripts`. HTTP only in clients via
  `request()` from `lib/core/http.js`, never `k6/http` elsewhere.
- One client per service, edge-agnostic; `name` tag `service:endpoint`, never an id; expected statuses listed.
- Every knob in `lib/core/env.js` `SCHEMA`; SLOs only in `k6/config/thresholds.js` (must agree with
  `cvhome/common-config.yml` SLO buckets); shapes in `profiles.js`; mix in `mix.js`.
- Fixtures declared via `build({needs: [...]})` + `withFixtures`; everything created is `k6-…`; `make clean`.
- Low-cardinality tags only. Line 1 of every `.js` is the generated-by comment. kebab-case scripts under
  `k6/scripts/<layer>/`, camelCase under `k6/lib/`.
- New endpoint coverage → a client method, a `docs/coverage.md` row, and a `make selftest` pass.

```bash
cd /Volumes/Disk/IdeaProjects/cvhome-saas/load-testing
make inspect                              # static validation, no traffic
(cd ../cvhome && lcl start -d --infra all && lcl urls)   # the target stack
make preflight && make selftest           # every client method against the live stack
PROFILE=smoke make <layer>-<name>         # one script; results/<TESTID>.json, Prometheus, Grafana annotation
npm test                                  # eslint, prettier, markdownlint, shellcheck, actionlint, inspect, build
```

Numbers go to `docs/baseline.md`; dashboards live in `cvhome/extra/monitoring/grafana/dashboards/load-testing`
(so a dashboard change is a `cvhome` PR). `make dash` opens `/d/cvhome-load-test-vs-app`.

## `e2e-testing/` — Playwright

A scaffold today: default `playwright.config.ts` (chromium only, html reporter, no `baseURL`), one example spec,
`.github/workflows/playwright.yml` on push/PR. When adding real journeys:
- Target the same stack as load-testing: `cd ../cvhome && lcl start -d`, read hosts/ports from `lcl urls`,
  demo logins from `cvhome/.claude/skills/project-structure/references/qa-testing.md`; set `baseURL` from
  env, never hardcode a port (stacks shift by +1000·k).
- One spec file per user-facing flow, named after the cvhome service that owns the entry point; keep the
  manual case in `cvhome/<service>/qa/<svc>-qa.md` and mark it **[verified]** by this spec.
- Never create data outside `e2e-…` prefixed names; reuse the seeded demo stores read-only.
- The CI workflow has no stack to run against; it passes vacuously until a `services:` job or an `lcl`-in-CI
  step exists. Say so rather than treating green as coverage.

```bash
cd /Volumes/Disk/IdeaProjects/cvhome-saas/e2e-testing
npm i && npx playwright install --with-deps && npx playwright test
```
