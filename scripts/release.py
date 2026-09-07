#!/usr/bin/env python3
"""
Release helper for the cvhome-saas product ring (docs/release-plan.md).

    scripts/release.py next-version [--bump auto|patch|minor|major] [--repo cvhome]
        Print the next product version: last `v*` tag of cvhome + the bump derived from the labels/titles of
        the PRs merged since it (warn/api-change|warn/behavior-change|"!:" → major; type/enhancement|"feat:" →
        minor; else patch; nothing but ignore-changelog → exit 3, "no release").

    scripts/release.py manifest --version 2.0.0 [--out releases/v2.0.0.yaml]
        Write the release manifest: product tag pair (tag + commit), images.json from cvhome's release asset,
        the latest tag of every component repo, and the contract-check result at the pair.

    scripts/release.py promote --version 2.0.0 --env dev [--platform ../cvhome-platform]
        Set `image_tag = "2.0.0"` in envs/<env>.tfvars of a cvhome-platform checkout (the caller commits/PRs).

Needs `gh` authenticated for the org and `git`. Dependency-free on purpose.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ORG = Path(__file__).resolve().parent.parent
GH_ORG = "cvhome-saas"
PRODUCT = ("cvhome", "cvhome-platform")
COMPONENTS = ("saas-gateway", "caddy-domainlookup", "certmagic-s3", "aws-otel-collector", "lcl")
VALIDATORS = ("load-testing", "e2e-testing")
SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def sh(*args: str, check: bool = True) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=check).stdout.strip()


def gh_json(*args: str):
    return json.loads(sh("gh", *args))


def latest_tag(repo: str) -> str | None:
    """Highest semver tag on the remote (works without a local clone)."""
    out = sh("git", "ls-remote", "--tags", "--refs", f"https://github.com/{GH_ORG}/{repo}.git", check=False)
    tags = [line.split("refs/tags/")[1] for line in out.splitlines() if "refs/tags/" in line]
    semver = [(tuple(int(x) for x in m.groups()), t) for t in tags if (m := SEMVER.match(t))]
    return max(semver)[1] if semver else None


def merged_prs_since(repo: str, tag: str | None) -> list[dict]:
    """PRs whose merge commits are on main after `tag` (all of main if no tag)."""
    if tag:
        compare = gh_json("api", f"repos/{GH_ORG}/{repo}/compare/{tag}...main", "--paginate")
        commits = compare.get("commits", [])
    else:
        commits = gh_json("api", f"repos/{GH_ORG}/{repo}/commits?sha=main&per_page=100")
    numbers = sorted({int(n) for c in commits for n in re.findall(r"\(#(\d+)\)", c["commit"]["message"])})
    prs = []
    for n in numbers:
        pr = gh_json("pr", "view", str(n), "-R", f"{GH_ORG}/{repo}", "--json", "number,title,labels,mergedAt")
        if pr.get("mergedAt"):
            prs.append({"number": n, "title": pr["title"], "labels": [l["name"] for l in pr["labels"]]})
    return prs


def bump_from(prs: list[dict]) -> str | None:
    considered = [p for p in prs if "ignore-changelog" not in p["labels"]]
    if not considered:
        return None
    level = "patch"
    for p in considered:
        labels, title = set(p["labels"]), p["title"]
        if labels & {"warn/api-change", "warn/behavior-change"} or re.match(r"^[a-z-]+(\([^)]*\))?!:", title):
            return "major"
        if "type/enhancement" in labels or title.startswith("feat"):
            level = "minor"
    return level


def bumped(tag: str | None, bump: str) -> str:
    m = SEMVER.match(tag) if tag else None
    major, minor, patch = (int(x) for x in m.groups()) if m else (0, 0, 0)
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def cmd_next_version(a) -> int:
    tag = latest_tag(a.repo)
    prs = merged_prs_since(a.repo, tag)
    bump = a.bump if a.bump != "auto" else bump_from(prs)
    if bump is None:
        print(f"no release: {len(prs)} PRs since {tag or 'the beginning'}, all ignore-changelog or none", file=sys.stderr)
        return 3
    version = bumped(tag, bump)
    print(json.dumps({"last_tag": tag, "bump": bump, "version": version, "prs": prs}) if a.json else version)
    return 0


def cmd_manifest(a) -> int:
    v = a.version.lstrip("v")
    tag = f"v{v}"
    doc = [f"product: {v}", f"date: {dt.date.today().isoformat()}"]
    for repo in PRODUCT:
        sha = sh("gh", "api", f"repos/{GH_ORG}/{repo}/git/ref/tags/{tag}", "--jq", ".object.sha", check=False)
        doc.append(f"{repo + ':':18} {{ tag: {tag}, commit: {sha[:8] if sha else 'MISSING'} }}")
    doc.append("images:")
    images = []
    try:
        subprocess.run(["gh", "release", "download", tag, "-R", f"{GH_ORG}/cvhome", "-p", "images.json", "-O", "/tmp/cvhome-images.json", "--clobber"],
                       check=True, capture_output=True)
        images = json.loads(Path("/tmp/cvhome-images.json").read_text())
    except subprocess.CalledProcessError:
        doc.append("  # images.json asset not found on the cvhome release; fill after release-images.yml completes")
    for img in images:
        doc.append(f"  {img['image'] + ':':22} {{ tag: {img['tag']}, digest: {img.get('digest', 'unknown')} }}")
    doc.append("components:")
    for repo in COMPONENTS:
        pin = a.pins.get(repo) if a.pins else None
        t = pin or latest_tag(repo)
        doc.append(f"  {repo + ':':22} {t.lstrip('v') if t else 'untagged'}")
    doc.append("validated_by:")
    for repo in VALIDATORS:
        sha = sh("gh", "api", f"repos/{GH_ORG}/{repo}/commits/main", "--jq", ".sha", check=False)
        doc.append(f"  {repo + ':':16} {{ commit: {sha[:8] if sha else 'null'}, result: pending }}")
    doc.append(f"contract_check: {a.contract_check}")
    out = Path(a.out or ORG / "releases" / f"{tag}.yaml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(doc) + "\n")
    print(out)
    return 0


def cmd_promote(a) -> int:
    v = a.version.lstrip("v")
    path = Path(a.platform) / "envs" / f"{a.env}.tfvars"
    text = path.read_text()
    new, n = re.subn(r'^(\s*image_tag\s*=\s*)"[^"]*"', rf'\g<1>"{v}"', text, count=1, flags=re.M)
    if n == 0:
        new = text.rstrip("\n") + f'\n\n# product version this environment runs (cvhome-saas/orchestrator releases/)\nimage_tag = "{v}"\n'
    path.write_text(new)
    print(f"{path}: image_tag = \"{v}\"")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    nv = sub.add_parser("next-version")
    nv.add_argument("--bump", default="auto", choices=["auto", "patch", "minor", "major"])
    nv.add_argument("--repo", default="cvhome")
    nv.add_argument("--json", action="store_true")
    nv.set_defaults(fn=cmd_next_version)
    mf = sub.add_parser("manifest")
    mf.add_argument("--version", required=True)
    mf.add_argument("--out")
    mf.add_argument("--contract-check", default="unknown")
    mf.add_argument("--pin", action="append", default=[], help="component=version override, repeatable")
    mf.set_defaults(fn=cmd_manifest)
    pr = sub.add_parser("promote")
    pr.add_argument("--version", required=True)
    pr.add_argument("--env", required=True, choices=["dev", "staging", "prod"])
    pr.add_argument("--platform", default=str(ORG / "cvhome-platform"))
    pr.set_defaults(fn=cmd_promote)
    a = ap.parse_args()
    if getattr(a, "pin", None) is not None:
        a.pins = dict(p.split("=", 1) for p in a.pin)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
