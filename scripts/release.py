#!/usr/bin/env python3
"""
Release helper for the cvhome-saas product ring (docs/release-plan.md).

    scripts/release.py next-version [--bump auto|patch|minor|major] [--repo cvhome]
        Print the next product version: last `v*` tag of cvhome + the bump derived from the labels/titles of
        the PRs merged since it (warn/api-change|warn/behavior-change|"!:" → major; type/enhancement|"feat:" →
        minor; else patch; nothing but ignore-changelog → exit 3, "no release").

    scripts/release.py tagged-repos
        Print the repos that receive the product tag (repos.yaml `tag: true`), space-separated.

    scripts/release.py manifest --version 2.0.0 [--out releases/v2.0.0.yaml]
        Write the release manifest: for every tagged repo the commit vX.Y.Z points at, plus the commits of
        the validating repos (load-testing, e2e-testing).


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
VALIDATORS = ("load-testing", "e2e-testing")


def tagged_repos() -> list[str]:
    """Repos with `tag: true` in repos.yaml, in manifest order."""
    text = (ORG / "repos.yaml").read_text()
    return [b.split("\n", 1)[0].strip() for b in re.split(r"\n  - name: ", text)[1:] if re.search(r"\n    tag: true", b)]
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


def cmd_tagged_repos(a) -> int:
    print(" ".join(tagged_repos()))
    return 0


def cmd_manifest(a) -> int:
    v = a.version.lstrip("v")
    tag = f"v{v}"
    doc = [f"version: {v}", f"date: {dt.date.today().isoformat()}", "repos:"]
    for repo in tagged_repos():
        sha = sh("gh", "api", f"repos/{GH_ORG}/{repo}/git/ref/tags/{tag}", "--jq", ".object.sha", check=False)
        doc.append(f"  {repo + ':':22} {sha[:8] if sha else 'MISSING'}")
    doc.append("validated_by:")
    for repo in VALIDATORS:
        sha = sh("gh", "api", f"repos/{GH_ORG}/{repo}/commits/main", "--jq", ".sha", check=False)
        doc.append(f"  {repo + ':':22} {{ commit: {sha[:8] if sha else 'null'}, result: pending }}")
    out = Path(a.out or ORG / "releases" / f"{tag}.yaml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(doc) + "\n")
    print(out)
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
    mf.set_defaults(fn=cmd_manifest)
    sub.add_parser("tagged-repos").set_defaults(fn=cmd_tagged_repos)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
