# QA across the organisation — what the orchestrator owns

cvhome established the model: **tests prove a unit; QA proves the path a person takes**, and the QA
script is a Markdown file that lives beside the code, is reviewed in the PR, and tags every case
`[verified]` or `[not verified]`. The orchestrator generalises it to every repo and adds the parts no
single repo can do: QA that crosses repos, QA at a release, and the audit that the files exist and are
honest.

## What QA means per repo

| Repo | QA artefact | How it runs | Stack |
|---|---|---|---|
| `cvhome` | `<service>/qa/<svc>-qa.md`, one per runnable app (13 Java services, `console-ui`, `landing-ui`) + `qa/lcl-qa.md` for the stack; `.http` blocks per endpoint | browser through the gateway, `.http` files, `lcl logs/why`; rules in `references/qa-testing.md` § 7 | `lcl start -d --stack <name>` in the worktree |
| `cvhome-platform` | `qa/platform-qa.md` (to add): a deploy to `dev` from a tag, hibernate/wake, a promotion PR, rollback | `terraform plan` on the PR (CI), CodeBuild run, `outputs.json`, console URL reachable | a real AWS env |
| `load-testing` | `make selftest` (every client method, `expect.soft`) and `PROFILE=smoke make <layer>-<name>`; `docs/baseline.md` is the record; `qa/load-testing-qa.md` § 05 for the stack | against `local` (its own compose stack, `make stack-up`) or `aws` | `make stack-up` in load-testing, on prebuilt images |
| `e2e-testing` | Playwright specs, one per user flow, named after the owning cvhome service; the cvhome QA case it automates gets `[verified] by e2e-testing/<spec>` | `npx playwright test` | cvhome `lcl` stack or load-testing's compose stack |
| `lcl` | `test/*.test.ts` (lifecycle, compose, safety are integration-style) + `qa/lcl-qa.md`: start/stop/ports/clean against a real project | Docker | its own examples, then `lcl validate --root ../cvhome` |
| `saas-gateway`, `caddy-domainlookup`, `certmagic-s3` | `qa/edge-qa.md` (to add): custom-domain TLS issuance, `domain_lookup` headers, cert sharing via S3 | run the built image as `spg` in cvhome's compose with the pin bumped | cvhome stack |
| `aws-otel-collector` | `qa/collector-qa.md` (to add): OTLP in → X-Ray trace, EMF metric, log group | a dev env with `monitoring: true` | AWS |
| `public-dkr`, `assets`, docs, `dot-github`, `ideation` | the artefact itself renders / the image exists / `fast-run.sh` runs on a clean host | manual | — |

## Duties the orchestrator performs

1. **Gate on the file.** `cross-repo-review` (via `impact.py`) asks, for any change to a controller, API,
   page, Caddyfile route or CLI flag: was the QA case added or updated? `contract-check.py --only qa`
   verifies every cvhome runnable app has its QA file and reports how many cases are `[not verified]`.
2. **Route QA to the right stack.** A cvhome change is QA'd in its worktree's own `lcl --stack`; a
   load-testing or e2e-testing change against a cvhome stack; an edge change by bumping the pin in a
   cvhome worktree and running the custom-domain cases; a platform change in `dev`.
3. **Cross-repo QA after a release.** `Release` tags everything; the promotion PR deploys `dev`. The
   orchestrator then runs, in order: `load-testing` `make selftest` and `PROFILE=smoke make all-smoke`
   against the deployed dev (TARGET=aws once `k6/config/env/aws.json` exists), the `[verified]` cases of the
   cvhome services the release touched (from the release notes), and records the outcome in
   `releases/vX.Y.Z.yaml` under `validated_by`. A failure blocks the staging promotion.
4. **Keep the tags honest.** A case marked `[verified]` names what verified it (a date and a stack, or an
   e2e spec). A PR that adds a feature with only `[not verified]` cases is merged only with that fact in
   its body; the reviewer says so rather than implying coverage.
5. **Write missing QA files** as part of `repo-standard` adoption, from the skeleton in
   `templates/repo/qa/README.md`, populated from the repo's real flows.

## The design gate is QA's front door

A new screen goes portal → review → record → implementation → QA case. The design record
(`.agents/designs/<slug>.md`) names the states the screen must show (empty, loading, error, populated);
the QA case for the screen tests exactly those states. `fullstack-task` § Design gate has the procedure.
