#!/usr/bin/env python3
"""
Map a change in one repo to what it can break in the others.

    scripts/impact.py cvhome                          # working tree + branch vs origin/main
    scripts/impact.py cvhome --base origin/main --head feat/x
    scripts/impact.py cvhome-platform --pr 12         # a GitHub PR (uses gh)
    scripts/impact.py lcl --files src/config.ts schema/lcl.schema.json   # no git, just paths
    scripts/impact.py cvhome --json

Prints, per changed file that matches a contract surface: the consumers in other repos, the
contract-check.py checks to run, and the review questions a human or the orchestrator must answer.
Files that match no rule are listed once as "local to the repo" — they still get the repo's own
review, just not a cross-repo one.

The rules are the executable form of .agents/skills/org-router/references/cross-repo-contracts.md;
keep the two in step.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ORG = Path(__file__).resolve().parent.parent

# (repo, path regex, consumers, checks, questions)
RULES: list[tuple[str, str, list[str], list[str], list[str]]] = [
    # ---------------------------------------------------------------- cvhome: the catalog and its slices
    ("cvhome", r"store-commons/autoconfigure/src/main/resources/common-config\.yml$",
     ["cvhome-platform/services.yaml", "cvhome/lcl.yml", "cvhome/.../fargate-config.yml", "cvhome/.../lcl-config.yml",
      "load-testing/k6/config/env/lcl.json", "load-testing/k6/config/thresholds.js", "cvhome/store-pod/spg/Caddyfile",
      "cvhome/.../GatewayRouteLocatorImpl.java", "cvhome/.claude/skills/project-structure/SKILL.md"],
     ["catalog", "edges", "slo", "load-testing", "skill-map"],
     ["Did a service, port, namespace, domain or gateway-service-name change? Every copy above must follow.",
      "Did the otel block change (sdk.disabled, exporter protocol, disabled.keys, SLO buckets)? The AWS collector filter and k6 thresholds assume the old values.",
      "Did a security/issuer/jwk URL change? cvhome-platform derives uaa's edge address from the catalog."]),
    ("cvhome", r"store-commons/autoconfigure/src/main/resources/.*fargate.*\.yml$|.*/application-fargate\.yml$",
     ["cvhome-platform/services.yaml (extra_env, secrets)", "cvhome-platform/modules/*/main.tf", "cvhome-platform/bootstrap/bootstrap.yaml"],
     ["catalog", "env"],
     ["Every new ${ENV_VAR} must be supplied by the platform (extra_env, secrets or module-computed).",
      "service-ports / eager-load.clients must list every service; the platform drift check compares them.",
      "A new secret key needs the bootstrap's generator before any env can bind it."]),
    ("cvhome", r"settings\.gradle$|.*/build\.gradle$",
     ["cvhome-platform/services.yaml (image path)", "cvhome-platform/prereq (ECR repo)", "cvhome-platform/bootstrap (2-images CodeBuild)"],
     ["catalog"],
     ["New/renamed module: is it in settings.gradle AND common-config AND services.yaml AND lcl.yml?",
      "imageName/imageGroup changed? ECR does not create repos on push: services.yaml `image` and prereq must match.",
      "JVM flags / memory in bootBuildImage env? The platform gives every Spring service a container memory limit; keep them consistent."]),
    ("cvhome", r"^lcl\.yml$",
     ["lcl (schema)", "load-testing/k6/config/env/lcl.json", "load-testing/bin/k6run (host resolver)", "cvhome/qa/lcl-qa.md"],
     ["catalog", "lcl-schema", "load-testing"],
     ["Ports/hosts/env changed? load-testing's lcl.json and hosts map must match.",
      "Does `lcl validate` pass with the lcl version the org ships (package.json version), not just the global one?",
      "New service or health check? qa/lcl-qa.md describes what `lcl status` should show."]),
    ("cvhome", r"docker-compose-lcl\.yml$|extra/scripts/configure-domain\.sh$",
     ["load-testing/stack/docker-compose.yml (aliases, ports, spg env)", "load-testing/k6/config/env/local.json + k6/data seed", "saas-gateway (image pin)"],
     ["spg-image", "load-testing", "catalog"],
     ["Hostnames/aliases/store ids/spg env changed? load-testing's compose stack and local.json must follow.",
      "spg image tag changed here? The Dockerfile pin is the one AWS runs; keep both on the same sha or say why not.",
      "Adding a monitoring service here is wrong: the monitoring stack lives in load-testing/stack (decision 2026-09-08)."]),
    ("cvhome", r"store-pod/spg/(Caddyfile|Dockerfile)$",
     ["cvhome-platform/services.yaml pod.spg (ports, health check :2019, extra_env)", "cvhome-platform/modules/store-pod/{nlb,storage}.tf", "saas-gateway", "caddy-domainlookup", "load-testing (storefront/spg journeys)"],
     ["edges", "env", "spg-image"],
     ["Every {$VAR} in the Caddyfile is set by the platform (extra_env) and by docker-compose-lcl.",
      "A new route/prefix strips or keeps the prefix consistently with the service's context-path; cua must keep /cua.",
      "New Caddy directive? It must exist in the pinned saas-gateway build (plugins are compiled in).",
      "Listen ports or admin API changed? The NLB target groups and health check in cvhome-platform assume 80/443/2019."]),
    ("cvhome", r"store-core/gateway/.*/GatewayRouteLocatorImpl\.java$|store-core/gateway/.*/(SecurityConfig|PodClient).*\.java$",
     ["cvhome-platform/modules/store-core/alb.tf (host rules)", "cvhome-platform/services.yaml core.* edge.hosts", "load-testing/k6/lib/core/edges.js"],
     ["edges"],
     ["A new backend prefix must be in backendServices or it is served console HTML.",
      "Host names the gateway accepts must match the ALB host rules and Route53 records in the platform.",
      "Route/prefix changes break load-testing's platformEdge/sellerEdge URL builders."]),
    ("cvhome", r".*/(CustomPermissionEvaluator|.*Api|.*Controller)\.java$|.*/http/.*\.http$",
     ["load-testing/k6/lib/clients/*.js + docs/coverage.md", "cvhome/<service>/qa/*-qa.md", "cvhome-saas.github.io (if public API)"],
     ["load-testing"],
     ["Changed path, method, params, status codes or permission token? k6 clients assert on them; update the client and coverage.md.",
      "Public/storefront endpoint changed? landing-ui and the storefront k6 journeys call it without auth.",
      "Rate limit, paging (page+count), sort casing, trial caps changed? load-testing/AGENTS.md lists these as assumptions."]),
    ("cvhome", r".*/schema\.sql$|.*/init-sql/.*\.sql$",
     ["cvhome-platform/modules/*/rds.tf (postgres version, db_pool_size)", "load-testing/scripts/cleanup.sql"],
     [],
     ["Uses a feature of a Postgres version newer than the platform's `postgres_version`?",
      "New table created by the k6 fixtures? load-testing's cleanup.sql must delete k6-… rows from it.",
      "Migration on an existing prod table: ddl-auto is a safety net only; is the DDL forward-compatible with the running image during a rolling deploy?"]),
    ("cvhome", r"store-commons/(secret-crypto|sso|ecs-commons)/.*|.*/(MultiIssuerJwtDecoder|.*Issuer.*)\.java$",
     ["cvhome-platform (crypto keys, issuer URLs, SPRING_CLOUD_ECS_DISCOVERY_*)", "cvhome-platform/bootstrap (sso secret keys)"],
     ["env"],
     ["A new key or issuer realm needs a platform-supplied value; rotating the crypto key re-encrypts nothing automatically.",
      "Discovery client changes must keep resolving Cloud Map names of the form <service>.<namespace>."]),
    ("cvhome", r"extra/monitoring/.*|docker-compose-load\.yml$|extra/scripts/load-stack\.sh$",
     ["load-testing/stack (the only home for monitoring and the load stack since 2026-09-08)"],
     [],
     ["These paths must not come back: monitoring configuration and the load stack live in load-testing/stack; add there, not here."]),
    ("cvhome", r"\.github/workflows/.*\.ya?ml$",
     ["cvhome-platform/bootstrap (CodeBuild is the deployer; app CI only publishes images)"],
     [],
     ["Does the workflow try to deploy? Deployment belongs to CodeBuild in cvhome-platform.",
      "Image tag/registry naming must match what services.yaml and prereq expect."]),
    ("cvhome", r"\.claude/skills/project-structure/.*|\.agents/skills/project-structure/.*",
     ["cvhome-saas.github.io", "orchestrator org-router references"],
     ["skill-map"],
     ["Both copies (.claude and .agents) updated? They have diverged before."]),
    # ---------------------------------------------------------------- cvhome-platform
    ("cvhome-platform", r"^services\.yaml$",
     ["cvhome common-config.yml / fargate-config.yml / build.gradle (drift check)", "cvhome Caddyfile + application-fargate.yml (env names)", "aws-otel-collector (infra block)"],
     ["catalog", "env", "edges"],
     ["Every port/name/image agrees with the app on the branch CI will compare against (APP_REF).",
      "Removed or renamed an env/secret? grep the app for readers before removing.",
      "Edge hosts/priorities changed? The Spring gateway and Caddy must accept those hosts."]),
    ("cvhome-platform", r"^flavours\.yaml$|^envs/.*\.tfvars$",
     ["cvhome (memory/CPU sizing vs JVM settings, Hikari pool vs rds db_pool_size)", "load-testing/docs/baseline.md"],
     [],
     ["Size or db_pool_size changed? The app's Hikari sizing derives from it; baselines were measured at the old values.",
      "monitoring flag changed? OTEL_SDK_DISABLED and MANAGEMENT_OTLP_METRICS_EXPORT_ENABLED flip with it."]),
    ("cvhome-platform", r"^modules/(store-core|store-pod|ecs-service)/.*\.tf$",
     ["cvhome fargate-config.yml + application-fargate.yml (env names)", "cvhome Caddyfile {$VAR}", "cvhome health endpoints (/actuator/health, :2019/config/)"],
     ["env", "catalog"],
     ["Renamed/removed a computed env var? grep the app for it.",
      "Health check path/port/grace changed? Spring Boot startup time and Caddy admin API must fit.",
      "Security group or namespace naming changed? lb:// resolution and cross-namespace otel-collector address depend on <service>.<namespace>."]),
    ("cvhome-platform", r"^modules/network/.*\.tf$|^modules/store-pod/(nlb|storage)\.tf$|^modules/store-core/alb\.tf$",
     ["cvhome spg (TLS termination, cert bucket, CDN env)", "cvhome landing-ui (STATIC_ASSETS_*)", "cvhome-saas.github.io deployment pages"],
     ["env"],
     ["TLS still terminates in Caddy (NLB passthrough)? An ALB in front of spg breaks on-demand certs.",
      "Bucket names/regions the Caddyfile and landing-ui read still supplied?"]),
    ("cvhome-platform", r"^bootstrap/.*",
     ["cvhome-platform/services.yaml secrets bindings", "cvhome (env var names the secrets map to)", "cvhome .github (image publish naming)"],
     ["env"],
     ["New/renamed secret json key? services.yaml bindings and app readers.",
      "CodeBuild 2-images buildspec still matches the app's gradle invocation and REGISTRY layout?",
      "publish-bootstrap.yml uploads on merge: the launch button changes for everyone."]),
    ("cvhome-platform", r"^prereq/.*|^scripts/.*",
     ["cvhome build.gradle image names (ECR repos)", "cvhome billing Stripe webhook path"],
     ["catalog"],
     ["ECR repo names derive from services.yaml image paths; removing one deletes images.",
      "register-stripe-webhook.sh path must match billing's StripeWebhookController."]),
    # ---------------------------------------------------------------- lcl
    ("lcl", r"^schema/lcl\.schema\.json$|^src/config\.ts$|^src/catalog\.ts$|^src/ports\.ts$|^src/render\.ts$",
     ["cvhome/lcl.yml", "cvhome + lcl .agents/skills/lcl-stack-builder", "load-testing (reads `lcl urls`/ports)", "lcl/templates, lcl/examples"],
     ["lcl-schema"],
     ["Does cvhome/lcl.yml still validate and start? Run `lcl validate --root ../cvhome`.",
      "Port-offset or LCL_PORT_* export semantics changed? The Caddyfile and load-testing depend on them.",
      "Breaking YAML change requires a new top-level version and a migration story."]),
    ("lcl", r"^src/(supervisor|control|proc|compose|instance|version)\.ts$|^src/commands/.*",
     ["cvhome AGENTS.md + qa/lcl-qa.md (documented commands and flags)", "load-testing README/AGENTS (lcl status/why/urls usage)"],
     [],
     ["Command names, flags, output formats (`--json`) changed? Docs in cvhome and load-testing quote them.",
      "State/control protocol version bumped with compatibility tests?"]),
    ("lcl", r"^package\.json$|^CHANGELOG\.md$|^\.github/workflows/publish\.yml$",
     ["cvhome (global install instructions, skills-lock.json)", "orchestrator workflow (installs @cvhome-saas/lcl)"],
     ["lcl-schema"],
     ["Version identical in package.json and src/version.ts? Is a release intended (never publish without the maintainer)?"]),
    # ---------------------------------------------------------------- load-testing
    ("load-testing", r"^stack/docker-compose\.yml$|^stack/stack\.sh$",
     ["cvhome common-config.yml (ports, hostnames, pod id the compose copies)", "cvhome store-pod/spg Caddyfile ({$VAR} env the compose sets)", "cvhome-platform services.yaml (the same services, the same secrets/env shape)", "aws-otel-collector (the AWS twin of the local collector)"],
     ["catalog", "env", "public-ecr"],
     ["Every service/port/alias still matches common-config.yml; a new service in cvhome needs a container here.",
      "spg env keys still match what the Caddyfile reads; SPRING_APPLICATION_JSON keys still exist in the app.",
      "Images are prebuilt: no build:, no cvhome path; LOAD_TAG/LOAD_REGISTRY stay the only inputs."]),
    ("load-testing", r"^stack/monitoring/.*|^docs/monitoring/.*",
     ["aws-otel-collector/otel-config.yaml (kept/dropped metrics should agree or the difference is documented)", "cvhome common-config.yml otel block (metric names, SLO buckets the dashboards assume)", "cvhome-platform flavours.yaml monitoring"],
     ["slo"],
     ["Dashboard JSON regenerated from dashboards.spec.mjs and docs/monitoring/dashboards.md regenerated (make monitoring-check).",
      "Recording rules/alerts renamed? load-testing's own Load-test-vs-app panels and cvhome QA docs quote them.",
      "Collector filter changed locally? Mirror in aws-otel-collector or note the deliberate difference."]),
    ("load-testing", r"^k6/config/thresholds\.js$",
     ["cvhome common-config.yml SLO buckets", "cvhome extra/monitoring dashboards", "load-testing/docs/baseline.md"],
     ["slo"],
     ["New p95 value must be a bucket boundary in the app's histogram or percentiles are interpolated."]),
    ("load-testing", r"^k6/config/env/.*\.json$|^k6/data/.*",
     ["cvhome lcl.yml / configure-domain.sh / docker-compose-load.yml (hosts, store ids)"],
     ["load-testing"],
     ["Store ids, hosts, accounts must exist in the app's seed data; only lcl.json and aws.example.json are committed."]),
    ("load-testing", r"^k6/lib/clients/.*|^k6/lib/core/(edges|http)\.js$",
     ["cvhome <service>/http/*.http (the contract the client encodes)", "load-testing/docs/coverage.md"],
     ["load-testing"],
     ["Does the request shape match the current .http block and controller? Run make selftest against a live stack.",
      "Tag names stay low-cardinality (service:endpoint)."]),
    ("load-testing", r"^bin/k6run$|^scripts/.*|^Makefile$",
     ["cvhome extra/monitoring (Prometheus remote-write, Grafana annotations)", "cvhome docker-compose-load.yml"],
     [],
     ["prometheusUrl/grafanaUrl and dashboard uid still match cvhome/extra/monitoring."]),
    # ---------------------------------------------------------------- image / plugin repos
    ("saas-gateway", r"^Dockerfile$|^\.github/workflows/.*",
     ["cvhome/store-pod/spg/Dockerfile (pin)", "cvhome/docker-compose-lcl.yml (pin)", "public ECR mirror", "cvhome Caddyfile (directives available)"],
     ["spg-image", "edges"],
     ["Plugins removed or Caddy major bumped? Every Caddyfile directive must still exist.",
      "After merge: publish → mirror → bump both pins in cvhome → QA spg locally.",
      "Runtime image changed (alpine version, capabilities)? Port 80/443 binding needs cap_net_bind_service."]),
    ("caddy-domainlookup", r".*\.go$|^go\.mod$",
     ["saas-gateway (xcaddy build from source path)", "cvhome Caddyfile `domain_lookup` blocks", "cvhome merchant RouterController (lookup contract)"],
     ["spg-image"],
     ["Directive/option names changed? Caddyfile breaks at load.",
      "Response contract (JSON map → headers) still what merchant returns and landing-ui expects (Store-Id, Theme)?",
      "Fail-open behaviour changed? Storefront availability during merchant outages depends on it.",
      "Caddy version in go.mod must be compatible with saas-gateway's xcaddy/Go."]),
    ("aws-otel-collector", r"^otel-config\.yaml$|^Dockerfile$",
     ["cvhome-platform services.yaml infra.otel-collector (ports 4317/4318, memory size)", "cvhome common-config.yml otel block (protocol, kept metrics)", "load-testing/stack/monitoring/otel-collector.yml (local counterpart)", "load-testing/docs/prometheus.md"],
     ["env"],
     ["Receivers still on 4317 gRPC + 4318 HTTP? Spring uses HTTP, node/caddy gRPC.",
      "memory_limiter vs the task size the platform gives the collector.",
      "Dropped metric prefixes: dashboards/alarms that use them go blank silently.",
      ":latest is mutable: a merge changes production on the next task restart with no Terraform diff."]),
    # ---------------------------------------------------------------- docs / ideas
    ("cvhome-saas.github.io", r"^docs/.*",
     ["cvhome project-structure skill", "cvhome-platform README/docs (what the page claims)"],
     [],
     ["Every service, repo and URL named on the page exists today (see org-router known-drift.md)."]),
    ("assets", r"^fast-run/.*",
     ["cvhome-saas.github.io development/local-setup.md (links the raw URL)", "cvhome common-config.yml + configure-domain.sh (hosts)", "public-dkr / cvhome public-ECR workflow (image names)"],
     [],
     ["Every image, host and service in the script exists today; the raw URL goes live on merge."]),
    ("dot-github", r".*",
     ["cvhome-saas.github.io (links)", "orchestrator README"],
     [],
     ["Links resolve; claims match the current repo set."]),
    ("public-dkr", r"^\.github/workflows/push-images\.yml$",
     ["cvhome Dockerfiles FROM public.ecr.aws/b2i4h4k9/* (console-ui, landing-ui, spg)", "cvhome store-pod/spg/compose.yml", "buildpack run images in cvhome build.gradle"],
     ["public-ecr", "spg-image"],
     ["Removing a matrix entry does not delete the image, but nothing will refresh it; bumping a tag needs the consumer FROM lines bumped too.",
      "The saas-gateway tag here is what AWS runs; keep it equal to cvhome's spg pin."]),
    ("certmagic-s3", r".*\.go$|^go\.mod$",
     ["saas-gateway (xcaddy build)", "cvhome Caddyfile `storage s3` block", "cvhome-platform modules/store-pod storage.tf + task IAM"],
     ["spg-image"],
     ["Caddyfile option names (bucket, region, prefix, endpoint) unchanged or Caddyfile updated?",
      "New S3 calls need IAM actions in the pod task role.",
      "Caddy version in go.mod compatible with caddy-domainlookup's and saas-gateway's Go."]),
    ("e2e-testing", r".*",
     ["cvhome <service>/qa/*-qa.md ([verified] tags)", "cvhome lcl.yml (hosts/ports the specs assume)"],
     [],
     ["baseURL/hosts read from env or `lcl urls`, never hardcoded ports.", "Data created is e2e-… prefixed; demo stores read-only."]),
    ("ideation", r".*",
     ["cvhome/.agents/plans (when picked up)"],
     [],
     ["Module names map to real ones (console-ui, store-pod/catalog, ...)? Status row updated?"]),
]

# Paths that are noise for cross-repo purposes.
IGNORE = re.compile(r"(^|/)(\.DS_Store|node_modules/|dist/|build/|results/|\.idea/)")


def changed_files(repo: Path, base: str | None, head: str | None, pr: int | None, files: list[str]) -> list[str]:
    if files:
        return files
    if pr is not None:
        out = subprocess.run(["gh", "pr", "diff", str(pr), "--name-only", "-R", f"cvhome-saas/{repo.name}"],
                             capture_output=True, text=True, check=True).stdout
        return out.split()
    base = base or "origin/main"
    args = ["git", "-C", str(repo), "diff", "--name-only"]
    if head:
        args += [f"{base}...{head}"]
    else:
        args += [base]  # working tree + index vs base
    tracked = subprocess.run(args, capture_output=True, text=True, check=True).stdout.split()
    untracked = [] if head else subprocess.run(["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard"],
                                                capture_output=True, text=True).stdout.split()
    return sorted(set(tracked) | set(untracked))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", help="directory name under the org root, e.g. cvhome")
    ap.add_argument("--base", help="git ref to diff against (default origin/main)")
    ap.add_argument("--head", help="branch/ref with the change (default: working tree)")
    ap.add_argument("--pr", type=int, help="GitHub PR number in cvhome-saas/<repo> (uses gh)")
    ap.add_argument("--files", nargs="*", default=[], help="explicit paths instead of git")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    repo = ORG / args.repo
    if not args.files and not (repo / ".git").exists() and args.pr is None:
        print(f"{repo} is not a checkout; run scripts/clone.sh {args.repo}", file=sys.stderr)
        return 2
    files = [f for f in changed_files(repo, args.base, args.head, args.pr, args.files) if not IGNORE.search(f)]

    hits: list[dict] = []
    local: list[str] = []
    by_rule: dict[int, dict] = {}
    for f in files:
        matched = False
        for i, (rrepo, pattern, consumers, checks, questions) in enumerate(RULES):
            if rrepo == args.repo and re.search(pattern, f):
                matched = True
                by_rule.setdefault(i, {"files": [], "consumers": consumers, "checks": checks, "questions": questions})["files"].append(f)
        if not matched:
            local.append(f)
    hits = list(by_rule.values())

    checks = sorted({c for h in hits for c in h["checks"]})
    consumers = sorted({c for h in hits for c in h["consumers"]})
    if args.json:
        print(json.dumps({"repo": args.repo, "files": files, "impacts": hits, "checks": checks,
                          "consumers": consumers, "local_only": local}, indent=2))
        return 0

    print(f"# Impact of changes in {args.repo} ({len(files)} files)\n")
    if not hits:
        print("No contract surface touched. Repo-local review only.\n")
    for h in hits:
        print("## " + ", ".join(h["files"][:6]) + (f" (+{len(h['files']) - 6} more)" if len(h["files"]) > 6 else ""))
        print("consumers: " + "; ".join(h["consumers"]))
        if h["checks"]:
            print("checks:    " + ", ".join(h["checks"]))
        for q in h["questions"]:
            print(f"  - {q}")
        print()
    if checks:
        print(f"Run: scripts/contract-check.py --only {','.join(checks)} --{args.repo} <path-to-branch-checkout>")
    if local:
        print(f"\nLocal to {args.repo} (no cross-repo rule): {len(local)} files")
        for f in local[:40]:
            print(f"  {f}")
        if len(local) > 40:
            print(f"  … and {len(local) - 40} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
