#!/usr/bin/env python3
"""
Cross-repo contract check for the cvhome-saas organisation.

One fact, several copies: the service catalog, ports, edge routes, env/secret names, image pins,
SLO buckets and local hostnames each live in one repo and are copied into others. This script reads
every copy and reports where they disagree. It is what the orchestrator runs as a reviewer before
and after any change in any repo, and what a PR in one repo cannot see about the others.

    scripts/contract-check.py                # every check, human-readable
    scripts/contract-check.py --json         # machine-readable
    scripts/contract-check.py --only edges,env
    scripts/contract-check.py --cvhome /path/to/cvhome/.claude/worktrees/feat-x   # review a branch/PR worktree
    scripts/contract-check.py --cvhome-platform /path/to/platform-worktree

Any repo path can be overridden (--cvhome, --cvhome-platform, --load-testing, --lcl, --saas-gateway, --public-dkr) so the
reviewer can evaluate a proposed change (a worktree, a `gh pr checkout`) against the other repos' main.

Exit 0 = no failures (warnings allowed), 1 = at least one FAIL, 2 = a required checkout is missing.

Dependency-free on purpose (no PyYAML): the YAML it reads is regular enough for indentation parsing,
and the script must run on any machine that has git and python3.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ORG = Path(__file__).resolve().parent.parent
APP = PLATFORM = LOAD = LCL = GATEWAY_IMG = MIRROR = Path()
COMMON_CONFIG = FARGATE_CONFIG = LCL_YML = CADDYFILE = SPG_DOCKERFILE = COMPOSE_LCL = GATEWAY_ROUTES = Path()
SERVICES_YAML = BOOTSTRAP = DRIFT_SCRIPT = LCL_JSON = THRESHOLDS = K6_CLIENTS = K6_LIB = Path()


def bind_paths(overrides: dict[str, str]) -> None:
    """Resolve every file the checks read, honouring --<repo> path overrides."""
    global APP, PLATFORM, LOAD, LCL, GATEWAY_IMG, MIRROR
    global COMMON_CONFIG, FARGATE_CONFIG, LCL_YML, CADDYFILE, SPG_DOCKERFILE, COMPOSE_LCL, GATEWAY_ROUTES
    global SERVICES_YAML, BOOTSTRAP, DRIFT_SCRIPT, LCL_JSON, THRESHOLDS, K6_CLIENTS, K6_LIB
    pick = lambda name: Path(overrides.get(name) or overrides.get(name.replace("-", "_")) or ORG / name).resolve()
    APP, PLATFORM, LOAD, LCL, GATEWAY_IMG, MIRROR = (pick(n) for n in ("cvhome", "cvhome-platform", "load-testing", "lcl", "saas-gateway", "public-dkr"))
    COMMON_CONFIG = APP / "store-commons/autoconfigure/src/main/resources/common-config.yml"
    FARGATE_CONFIG = APP / "store-commons/autoconfigure/src/main/resources/fargate-config.yml"
    LCL_YML = APP / "lcl.yml"
    CADDYFILE = APP / "store-pod/spg/Caddyfile"
    SPG_DOCKERFILE = APP / "store-pod/spg/Dockerfile"
    COMPOSE_LCL = APP / "docker-compose-lcl.yml"
    GATEWAY_ROUTES = APP / "store-core/gateway/gateway-service/src/main/java/com/asrevo/cvhome/gateway/config/GatewayRouteLocatorImpl.java"
    SERVICES_YAML = PLATFORM / "services.yaml"
    BOOTSTRAP = PLATFORM / "bootstrap/bootstrap.yaml"
    DRIFT_SCRIPT = PLATFORM / "scripts/check-catalog-drift.py"
    LCL_JSON = LOAD / "k6/config/env/local.json"
    THRESHOLDS = LOAD / "k6/config/thresholds.js"
    K6_CLIENTS = LOAD / "k6/lib/clients"
    K6_LIB = LOAD / "k6/lib"

results: list[dict] = []


def report(check: str, status: str, msg: str, fix: str = "") -> None:
    results.append({"check": check, "status": status, "message": msg, "fix": fix})


def need(path: Path, check: str) -> bool:
    if path.exists():
        return True
    report(check, "SKIP", f"missing: {path} (run scripts/clone.sh)")
    return False


# ----------------------------------------------------------------------------- parsers

def parse_common_config() -> dict[str, dict]:
    """com.asrevo.cvhome.services.<name>: {port, namespace, gateway-service-name}."""
    services: dict[str, dict] = {}
    current = None
    in_services = False
    for line in COMMON_CONFIG.read_text().splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped == "services:" and indent == 6:
            in_services = True
            continue
        if in_services and indent <= 6 and stripped and not stripped.startswith("#"):
            in_services = False
        if not in_services:
            continue
        if indent == 8 and stripped.endswith(":"):
            current = stripped[:-1]
            services[current] = {}
        elif indent == 10 and current and ":" in stripped:
            k, v = stripped.split(":", 1)
            services[current][k.strip()] = v.strip()
    return services


def parse_common_config_scalar(dotted: str) -> str | None:
    """Very small dotted lookup for com.asrevo.cvhome.{app.domain, pod.domain}."""
    keys = dotted.split(".")
    stack: list[tuple[int, str]] = []
    for line in COMMON_CONFIG.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if ":" in stripped:
            k, v = stripped.split(":", 1)
            path = [s[1] for s in stack] + [k.strip()]
            if path == keys:
                return v.strip()
            stack.append((indent, k.strip()))
    return None


def parse_slo_buckets() -> list[int]:
    m = re.search(r"http\.server\.requests:\s*([0-9a-z,]+)", COMMON_CONFIG.read_text())
    if not m:
        return []
    out = []
    for tok in m.group(1).split(","):
        n = re.match(r"(\d+)(ms|s)", tok)
        if n:
            out.append(int(n.group(1)) * (1000 if n.group(2) == "s" else 1))
    return out


def parse_lcl_yml_ports() -> dict[str, int]:
    """services.<name>.ports: { http: N } (also multi-line form)."""
    ports: dict[str, int] = {}
    current = None
    in_services = False
    for line in LCL_YML.read_text().splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if indent == 0 and stripped == "services:":
            in_services = True
            continue
        if indent == 0 and stripped:
            in_services = False
        if not in_services:
            continue
        if indent == 2 and stripped.endswith(":") and not stripped.startswith("#"):
            current = stripped[:-1]
        elif current and stripped.startswith("ports:"):
            m = re.search(r"http:\s*(\d+)", stripped)
            if m:
                ports[current] = int(m.group(1))
        elif current and indent == 6 and re.match(r"http:\s*\d+", stripped):
            ports[current] = int(stripped.split(":")[1])
    return ports


def parse_fargate_service_ports() -> dict[str, int]:
    text = FARGATE_CONFIG.read_text()
    m = re.search(r"service-ports:\n((?:\s+\"?[a-z0-9-]+\"?:\s*\d+\n)+)", text)
    if not m:
        return {}
    return {k.strip('"'): int(v) for k, v in re.findall(r"\"?([a-z0-9-]+)\"?:\s*(\d+)", m.group(1))}


def parse_services_yaml() -> dict[str, dict]:
    """<layer>.<name>: {port, image, runtime, secrets{ENV: 'secret:key'}, extra_env{...}, layer}."""
    services: dict[str, dict] = {}
    layer = None
    svc = None
    block = None
    for line in SERVICES_YAML.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0 and stripped.endswith(":"):
            layer = stripped[:-1]
            svc = None
            continue
        if indent == 2 and stripped.endswith(":"):
            svc = stripped[:-1]
            services[svc] = {"layer": layer, "secrets": {}, "extra_env": {}}
            block = None
            continue
        if svc is None:
            continue
        if indent == 4:
            if stripped in ("secrets:", "extra_env:"):
                block = stripped[:-1]
                continue
            block = None
            if ":" in stripped:
                k, v = stripped.split(":", 1)
                services[svc][k.strip()] = v.strip().strip('"')
        elif indent == 6 and block and ":" in stripped:
            k, v = stripped.split(":", 1)
            services[svc][block][k.strip()] = v.strip().strip('"')
    return services


def parse_bootstrap_secret_keys() -> dict[str, set[str]]:
    """secret name -> json keys the bootstrap creates or generates."""
    text = BOOTSTRAP.read_text()
    keys: dict[str, set[str]] = {"stripe": set(), "uaa": set(), "sso": set()}
    m = re.search(r'\{"STRIPE_KEY"[^\n]*\}', text)
    if m:
        keys["stripe"] |= set(re.findall(r'"([A-Z_\-]+)":', m.group(0)))
    m = re.search(r"SecretStringTemplate: '(\{[^']*\})'\n\s+GenerateStringKey: (\S+)", text)
    if m:
        keys["uaa"] |= set(re.findall(r'"([a-zA-Z_]+)":', m.group(1))) | {m.group(2)}
    keys["sso"] |= set(re.findall(r'"([A-Z_]+)":\s*lambda', text))
    return keys


def platform_env_supplied() -> set[str]:
    """Env names the platform sets: services.yaml extra_env/secrets, plus every UPPER = / "UPPER" = in modules."""
    supplied: set[str] = set()
    for svc in parse_services_yaml().values():
        supplied |= set(svc["secrets"]) | set(svc["extra_env"])
    for tf in PLATFORM.glob("modules/*/*.tf"):
        t = tf.read_text()
        supplied |= set(re.findall(r'^\s*"?([A-Z][A-Z0-9_]{3,})"?\s*=', t, re.M))
        supplied |= set(re.findall(r'name\s*=\s*"([A-Z][A-Z0-9_]{3,})"', t))
        supplied |= set(re.findall(r'"([A-Z][A-Z0-9_]{3,})"\s*=>', t))
        # map literals: { NAME = value } and templated keys
        supplied |= set(re.findall(r'\b([A-Z][A-Z0-9_]{3,})\s*=\s*(?:"|local|var|module|try|format|tostring|join|jsonencode|\d)', t))
    return supplied


SECRET_LIKE = re.compile(r"SECRET|PASSWORD|_KEY$|TOKEN|CREDENTIAL")


def app_env_expected() -> dict[str, set[str]]:
    """Env names the app needs supplied on Fargate, by source file.

    Every `${NAME}` with no default in any main config file, plus every `${NAME:default}` whose name looks
    like a credential: a committed default for a secret is the local seed, and shipping it to AWS because the
    platform forgot to bind the real one is exactly the failure this check exists for.
    """
    out: dict[str, set[str]] = {}
    files = [FARGATE_CONFIG, *APP.glob("store-commons/autoconfigure/src/main/resources/*.yml"),
             *APP.glob("store-*/*/src/main/resources/application*.yml"), *APP.glob("store-*/*/*/src/main/resources/application*.yml")]
    for path in files:
        if not path.exists() or "/build/" in str(path) or path.name.endswith(("-lcl.yml", "-test-stores.yml", "-test.yml")):
            continue
        names = set()
        for name, default in re.findall(r"\$\{([A-Z][A-Z0-9_]{3,})(:[^}]*)?\}", path.read_text()):
            if not default or SECRET_LIKE.search(name):
                names.add(name)
        if names:
            out[str(path.relative_to(APP))] = names
    if CADDYFILE.exists():
        names = {n for n in re.findall(r"\{\$([A-Z][A-Z0-9_]+)(?::[^}]*)?\}", CADDYFILE.read_text()) if not n.startswith("LCL_PORT_")}
        out["store-pod/spg/Caddyfile"] = names
    return out


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout.strip()


# ----------------------------------------------------------------------------- checks

def check_catalog() -> None:
    """common-config.yml vs services.yaml vs fargate-config.yml vs lcl.yml: same names, same ports."""
    c = "catalog"
    if not (need(COMMON_CONFIG, c) and need(SERVICES_YAML, c) and need(FARGATE_CONFIG, c) and need(LCL_YML, c)):
        return
    common = parse_common_config()
    platform = {k: v for k, v in parse_services_yaml().items() if v["layer"] in ("core", "pod")}
    fargate = parse_fargate_service_ports()
    lcl_ports = parse_lcl_yml_ports()

    cp = {k: int(v["port"]) for k, v in common.items() if "port" in v}
    pp = {k: int(v["port"]) for k, v in platform.items() if "port" in v}
    for name in sorted(set(cp) | set(pp)):
        if name not in pp:
            report(c, "FAIL", f"{name}:{cp[name]} is in common-config.yml but not in cvhome-platform/services.yaml",
                   "add the service to services.yaml (port, image, database, runtime, size, edge)")
        elif name not in cp:
            report(c, "FAIL", f"{name} is in services.yaml but not in common-config.yml",
                   "remove it from services.yaml or register it in the app")
        elif cp[name] != pp[name]:
            report(c, "FAIL", f"{name}: common-config.yml port {cp[name]} != services.yaml port {pp[name]}")
    for name, port in cp.items():
        if name == "spg":
            continue  # Caddy edge: addressed by hostname/NLB, never resolved via lb://
        if name not in fargate:
            report(c, "FAIL", f"{name} missing from fargate-config.yml service-ports (lb:// will not resolve on Fargate)")
        elif fargate[name] != port:
            report(c, "FAIL", f"{name}: fargate-config.yml service-ports {fargate[name]} != common-config.yml {port}")
        if name == "spg":
            continue  # runs in Compose, not as an lcl source service
        if name not in lcl_ports:
            report(c, "WARN", f"{name} has no `ports: {{ http: … }}` entry in cvhome/lcl.yml (not part of the local stack?)")
        elif lcl_ports[name] != port:
            report(c, "FAIL", f"{name}: lcl.yml port {lcl_ports[name]} != common-config.yml {port}")
    # load-testing's compose stack copies every port (host:container) and must agree too.
    lt_compose = LOAD / "stack" / "docker-compose.yml"
    if lt_compose.exists():
        text = lt_compose.read_text()
        for name, port in cp.items():
            m = re.search(rf"^  {re.escape(name)}:\n(?:(?!^  \S).*\n)*?\s+- \"(\d+):(\d+)\"", text, re.M)
            if not m:
                report(c, "WARN", f"{name} has no container in load-testing/stack/docker-compose.yml")
            elif int(m.group(2)) != port:
                report(c, "FAIL", f"{name}: load-testing compose container port {m.group(2)} != common-config.yml {port}")
    if not any(r["check"] == c for r in results):
        report(c, "OK", f"{len(cp)} services agree across common-config.yml, services.yaml, fargate-config.yml, lcl.yml, load-testing compose")

    # The platform's own, stricter script (also checks image paths and eager-load clients).
    if DRIFT_SCRIPT.exists():
        r = subprocess.run([sys.executable, str(DRIFT_SCRIPT), "--app-repo", str(APP), "--catalog", str(SERVICES_YAML)],
                           capture_output=True, text=True)
        tail = (r.stdout + r.stderr).strip().splitlines()
        if r.returncode == 0:
            report("catalog-drift-script", "OK", "cvhome-platform/scripts/check-catalog-drift.py passes")
        else:
            report("catalog-drift-script", "FAIL", "check-catalog-drift.py failed: " + " | ".join(tail[-6:]))


def check_edges() -> None:
    """Every service is reachable through its declared gateway: spg Caddyfile routes, gateway backendServices."""
    c = "edges"
    if not (need(COMMON_CONFIG, c) and need(CADDYFILE, c) and need(GATEWAY_ROUTES, c)):
        return
    common = parse_common_config()
    caddy = CADDYFILE.read_text()
    routes = set(re.findall(r"handle(?:_path)?\s+/([a-z0-9-]+)\*", caddy))
    proxies = {m[0]: int(m[1]) for m in re.findall(r"reverse_proxy\s+https?://([a-z0-9-]+)\.\{\$NAMESPACE\}:\{\$LCL_PORT_[A-Z_]+:(\d+)\}", caddy)}
    backend = re.search(r"backendServices\s*=\s*\{([^}]*)\}", GATEWAY_ROUTES.read_text())
    backend_set = set(re.findall(r'"([a-z0-9-]+)"', backend.group(1))) if backend else set()

    ok = True
    for name, v in common.items():
        gw = v.get("gateway-service-name")
        port = int(v.get("port", 0))
        if gw == "spg" and name not in ("spg", "landing-ui"):
            if name not in routes:
                ok = False
                report(c, "FAIL", f"{name} is fronted by spg but the Caddyfile has no `handle_path /{name}*` route")
            if name in proxies and proxies[name] != port:
                ok = False
                report(c, "FAIL", f"Caddyfile default port for {name} is {proxies[name]}, common-config.yml says {port}")
        if gw == "store-core-gateway" and name not in ("store-core-gateway", "console-ui") and name not in backend_set:
            ok = False
            report(c, "FAIL", f"{name} is fronted by store-core-gateway but is not in GatewayRouteLocatorImpl.backendServices "
                              "(its /{name}/** would be served console HTML)")
    for name in sorted(backend_set - set(common) - {"spg"}):
        ok = False
        report(c, "WARN", f"backendServices lists {name}, which is not in common-config.yml")
    if ok:
        report(c, "OK", f"{len(routes)} spg routes and backendServices {sorted(backend_set)} cover every fronted service")


def check_env() -> None:
    """Env the app expects on Fargate is supplied by the platform; secret bindings point at keys the bootstrap creates."""
    c = "env"
    if not (need(SERVICES_YAML, c) and need(BOOTSTRAP, c) and need(CADDYFILE, c)):
        return
    supplied = platform_env_supplied()
    # Spring relaxed binding: the platform may supply the property under its canonical env name instead
    # of the placeholder the yml names (com.asrevo.cvhome.admin.password <- COM_ASREVO_CVHOME_ADMIN_PASSWORD).
    aliases = {"UAA_ADMIN_PASSWORD": "COM_ASREVO_CVHOME_ADMIN_PASSWORD"}
    missing = []
    for src, names in app_env_expected().items():
        for n in sorted(names):
            if n not in supplied and aliases.get(n) not in supplied:
                missing.append(f"{n} (read in {src})")
    if missing:
        report(c, "FAIL", "app reads env the platform never sets: " + ", ".join(missing),
               "add to services.yaml extra_env/secrets or compute it in modules/*/main.tf")
    keys = parse_bootstrap_secret_keys()
    bad = []
    for svc, v in parse_services_yaml().items():
        for env_name, ref in v["secrets"].items():
            secret, _, key = ref.partition(":")
            if secret not in keys:
                bad.append(f"{svc}.{env_name} -> unknown secret '{secret}'")
            elif key not in keys[secret]:
                bad.append(f"{svc}.{env_name} -> {secret} has no json key '{key}' (bootstrap creates {sorted(keys[secret])})")
    if bad:
        report(c, "FAIL", "secret bindings without a source: " + "; ".join(bad),
               "add the key to bootstrap.yaml's secret generator, or fix the binding")
    if not missing and not bad:
        report(c, "OK", "every Fargate/Caddy env var the app reads is supplied; every secret binding has a bootstrap key")


def check_spg_pin() -> None:
    """spg's Caddy base image: Dockerfile pin vs local compose pin vs saas-gateway HEAD."""
    c = "spg-image"
    if not (need(SPG_DOCKERFILE, c) and need(COMPOSE_LCL, c)):
        return
    d = re.search(r"saas-gateway:(\S+)", SPG_DOCKERFILE.read_text())
    k = re.search(r"saas-gateway:(\S+)", COMPOSE_LCL.read_text())
    dtag, ktag = (d.group(1) if d else "?"), (k.group(1) if k else "?")
    head = git(GATEWAY_IMG, "rev-parse", "--short=7", "HEAD") if GATEWAY_IMG.exists() else ""
    known = set(git(GATEWAY_IMG, "log", "--format=%h").split()) if GATEWAY_IMG.exists() else set()
    if dtag != ktag:
        report(c, "WARN", f"spg Dockerfile pins saas-gateway:{dtag} (AWS) but docker-compose-lcl.yml runs :{ktag} (local): local QA does not exercise the deployed Caddy")
    for label, tag in (("Dockerfile", dtag), ("docker-compose-lcl.yml", ktag)):
        sha = tag.replace("sha-", "")
        if known and sha not in known and tag != "latest":
            report(c, "FAIL", f"{label} pins saas-gateway:{tag}, which is not a commit in saas-gateway")
        elif head and sha != head:
            report(c, "WARN", f"{label} pins saas-gateway:{tag}; saas-gateway HEAD is {head} (unreleased Caddy changes not in use)")
    if dtag == ktag and head and dtag.replace("sha-", "") == head:
        report(c, "OK", f"spg pins saas-gateway:{dtag} everywhere and it is saas-gateway HEAD")


def check_public_ecr() -> None:
    """Every public.ecr.aws/<alias>/<image>:<tag> cvhome pulls is in public-dkr's mirror matrix."""
    c = "public-ecr"
    matrix = MIRROR / ".github/workflows/push-images.yml"
    if not need(matrix, c):
        return
    text = matrix.read_text()
    mirrored = {(i, tg) for i, tg in re.findall(r"image:\s*(\S+)\n\s+tag:\s*(\S+)", text)}
    refs: dict[tuple[str, str], list[str]] = {}
    for path in [*APP.glob("store-*/*/Dockerfile"), *APP.glob("store-*/*/compose.yml"), COMPOSE_LCL, SPG_DOCKERFILE]:
        if not path.exists():
            continue
        for image, tag in re.findall(r"public\.ecr\.aws/[a-z0-9]+/([A-Za-z0-9_./-]+):([A-Za-z0-9_.-]+)", path.read_text()):
            refs.setdefault((image, tag), []).append(str(path.relative_to(APP)))
    missing = [f"{i}:{t} ({', '.join(sorted(set(files)))})" for (i, t), files in sorted(refs.items()) if (i, t) not in mirrored]
    if missing:
        report(c, "FAIL", "cvhome pulls public-ECR images that public-dkr never mirrored: " + "; ".join(missing),
               "add the image/tag to public-dkr's push-images.yml matrix and push main")
    else:
        report(c, "OK", f"all {len(refs)} public-ECR image references in cvhome are in public-dkr's mirror matrix")
    gw = [tg for i, tg in mirrored if i.endswith("saas-gateway")]
    d = re.search(r"saas-gateway:(\S+)", SPG_DOCKERFILE.read_text()) if SPG_DOCKERFILE.exists() else None
    if d and gw and d.group(1) not in gw:
        report(c, "FAIL", f"spg Dockerfile pins saas-gateway:{d.group(1)} but public-dkr mirrors {gw}")


def check_slo() -> None:
    """k6 p95 thresholds must be bucket boundaries of the app's http.server.requests SLO histogram."""
    c = "slo"
    if not (need(COMMON_CONFIG, c) and need(THRESHOLDS, c)):
        return
    buckets = set(parse_slo_buckets())
    text = THRESHOLDS.read_text()
    p95s = {int(m) for m in re.findall(r"p95\((\d+)", text)}
    bad = sorted(v for v in p95s if v not in buckets)
    if not buckets:
        report(c, "FAIL", "no http.server.requests SLO buckets found in common-config.yml")
    elif bad:
        report(c, "WARN", f"k6 p95 thresholds {bad} ms are not bucket boundaries in common-config.yml {sorted(buckets)}; "
                          "the app-side histogram cannot express those percentiles exactly")
    else:
        report(c, "OK", f"all {len(p95s)} k6 p95 thresholds are app SLO bucket boundaries")


def check_load_env() -> None:
    """load-testing's lcl.json must point at the same gateway/uaa/pod as common-config.yml; every service has a client."""
    c = "load-testing"
    if not (need(COMMON_CONFIG, c) and need(LCL_JSON, c) and need(K6_CLIENTS, c)):
        return
    cfg = json.loads(LCL_JSON.read_text())
    common = parse_common_config()
    app_domain = parse_common_config_scalar("com.asrevo.cvhome.app.domain")
    pod_domain = (parse_common_config_scalar("com.asrevo.cvhome.pod.domain") or "").replace("${com.asrevo.cvhome.app.domain}", app_domain or "")
    problems = []
    gw_port = int(common.get("store-core-gateway", {}).get("port", 0))
    uaa_port = int(common.get("uaa", {}).get("port", 0))
    if not cfg.get("gatewayUrl", "").endswith(f"{app_domain}:{gw_port}"):
        problems.append(f"gatewayUrl {cfg.get('gatewayUrl')} != http://{app_domain}:{gw_port}")
    if not cfg.get("uaaUrl", "").endswith(f"uaa.{app_domain}:{uaa_port}"):
        problems.append(f"uaaUrl {cfg.get('uaaUrl')} != http://uaa.{app_domain}:{uaa_port}")
    if pod_domain and cfg.get("podDomain") != pod_domain:
        problems.append(f"podDomain {cfg.get('podDomain')} != {pod_domain}")
    if problems:
        report(c, "FAIL", "k6/config/env/local.json disagrees with common-config.yml: " + "; ".join(problems))

    lib_text = "\n".join(p.read_text() for p in K6_LIB.rglob("*.js"))
    alias = {"pod-registry": "podRegistry", "landing-ui": "storefrontPages", "store-core-gateway": "gateway"}
    uncovered = []
    for name in common:
        if name == "spg":
            continue
        client = alias.get(name, name)
        if not (K6_CLIENTS / f"{client}.js").exists() and f"'{name}:" not in lib_text and f"`{name}:" not in lib_text:
            uncovered.append(name)
    if uncovered:
        report(c, "WARN", f"services with no k6 client or request name: {uncovered} (see load-testing/docs/coverage.md)")
    if not problems and not uncovered:
        report(c, "OK", "lcl.json matches common-config.yml and every service has k6 coverage")


def check_lcl_validate() -> None:
    """cvhome/lcl.yml validates against the lcl CLI the org ships (dist in lcl/, else the global install)."""
    c = "lcl-schema"
    if not need(LCL_YML, c):
        return
    local_bin = LCL / "bin/lcl.js"
    cmd = ["node", str(local_bin)] if (LCL / "dist/src/main.js").exists() else ["lcl"]
    try:
        r = subprocess.run([*cmd, "validate", "--root", str(APP)], capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        report(c, "SKIP", f"lcl not runnable ({e.__class__.__name__}); build lcl/ or `npm i -g @cvhome-saas/lcl`")
        return
    if r.returncode == 0:
        report(c, "OK", f"cvhome/lcl.yml validates with {' '.join(cmd)}")
    else:
        report(c, "FAIL", "cvhome/lcl.yml does not validate: " + (r.stderr or r.stdout).strip().splitlines()[-1])


def check_release() -> None:
    """Tracking only: which released version each envs/*.tfvars names. Never a gate — releases record compatibility, they do not deploy."""
    c = "release"
    envs = sorted(PLATFORM.glob("envs/*.tfvars"))
    if not envs:
        report(c, "SKIP", "no cvhome-platform/envs/*.tfvars")
        return
    manifests = {p.stem.lstrip("v") for p in (ORG / "releases").glob("v*.yaml")}
    problems, notes = [], []
    for tf in envs:
        m = re.search(r'^\s*image_tag\s*=\s*"([^"]*)"', tf.read_text(), re.M)
        env = tf.stem
        if not m:
            notes.append(f"{env}: no image_tag (falls back to SSM / latest)")
        elif m.group(1) == "latest":
            # prod on latest is a failure once a release exists; before the 2.0.0 cut-over it is the known state
            (problems if env == "prod" and manifests else notes).append(f"{env}: image_tag = latest")
        elif m.group(1) not in manifests:
            problems.append(f"{env}: image_tag {m.group(1)} has no releases/v{m.group(1)}.yaml")
    if problems or notes:
        report(c, "WARN", "; ".join(problems + notes) + f" ({len(manifests)} manifests in releases/)")
    else:
        report(c, "OK", f"every environment names a released version ({len(manifests)} manifests)")


def check_qa() -> None:
    """Every runnable cvhome app has its QA file; report how much of it is unverified."""
    c = "qa"
    if not need(COMMON_CONFIG, c):
        return
    missing, unverified, total = [], 0, 0
    dirs = {"store-core-gateway": "gateway"}
    for svc in parse_common_config():
        if svc == "spg":
            continue
        name = dirs.get(svc, svc)
        files = list(APP.glob(f"store-*/{name}/*/qa/*-qa.md")) + list(APP.glob(f"store-*/{name}/qa/*-qa.md")) \
            + list(APP.glob(f"store-*/*/{name}/qa/*-qa.md")) + list(APP.glob(f"store-*/*/{name}-service/qa/*-qa.md"))
        if not files:
            missing.append(svc)
            continue
        text = "\n".join(f.read_text() for f in files)
        total += len(re.findall(r"\[verified\]", text)) + len(re.findall(r"\[not verified\]", text))
        unverified += len(re.findall(r"\[not verified\]", text))
    if missing:
        report(c, "FAIL", f"cvhome services with no qa/<svc>-qa.md: {missing}", "AGENTS.md: every runnable app has one; copy billing-qa.md's structure")
    if total:
        report(c, "WARN" if unverified else "OK", f"{total} cvhome QA cases, {unverified} [not verified]")


def check_skill_table() -> None:
    """cvhome's project-structure skill lists every service (the map agents navigate by)."""
    c = "skill-map"
    skill = APP / ".claude/skills/project-structure/SKILL.md"
    if not (need(COMMON_CONFIG, c) and need(skill, c)):
        return
    text = skill.read_text()
    missing = [n for n in parse_common_config() if f"`{n}`" not in text and f"/{n}`" not in text and f"`store-core/{n}" not in text]
    if missing:
        report(c, "WARN", f"cvhome/.claude/skills/project-structure/SKILL.md does not mention: {missing}")
    else:
        report(c, "OK", "project-structure skill mentions every catalog service")


CHECKS = {
    "catalog": check_catalog,
    "edges": check_edges,
    "env": check_env,
    "spg-image": check_spg_pin,
    "public-ecr": check_public_ecr,
    "slo": check_slo,
    "load-testing": check_load_env,
    "lcl-schema": check_lcl_validate,
    "skill-map": check_skill_table,
    "release": check_release,
    "qa": check_qa,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", help="comma-separated subset of: " + ",".join(CHECKS))
    repos = ("cvhome", "cvhome-platform", "load-testing", "lcl", "saas-gateway", "public-dkr")
    for repo in repos:
        ap.add_argument(f"--{repo}", dest=repo.replace("-", "_"), help=f"path to use instead of ./{repo} (a worktree or PR checkout)")
    args = ap.parse_args()
    bind_paths({r: getattr(args, r.replace("-", "_")) for r in repos})
    selected = args.only.split(",") if args.only else list(CHECKS)
    for name in selected:
        if name not in CHECKS:
            sys.exit(f"unknown check {name}; choose from {','.join(CHECKS)}")
        try:
            CHECKS[name]()
        except Exception as e:  # a parser surprise must not hide the other checks
            report(name, "FAIL", f"check crashed: {e.__class__.__name__}: {e}")
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        width = max(len(r["check"]) for r in results) if results else 10
        for r in results:
            print(f"{r['status']:4} {r['check']:{width}}  {r['message']}")
            if r["fix"]:
                print(f"{'':4} {'':{width}}  fix: {r['fix']}")
    statuses = {r["status"] for r in results}
    if "FAIL" in statuses:
        return 1
    return 0


if __name__ == "__main__":
    os.chdir(ORG)
    sys.exit(main())
