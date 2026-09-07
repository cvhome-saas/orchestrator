#!/usr/bin/env python3
"""
Audit every checkout against the org repo standard (templates/repo, the `repo-standard` skill).

    scripts/standard-check.py            # every repo in repos.yaml (except this one)
    scripts/standard-check.py cvhome lcl
    scripts/standard-check.py --json

For each repo: which standard files are present, missing, or present-but-stale (hook scripts that differ
from the template, ignoring the repo-specific verify path), and whether AGENTS.md states the conventions
(worktree, plan phases, PR per phase, verify receipt, QA file, design gate). Exit 1 if any repo is missing a
required file. `scripts/standard-apply.sh <repo>` fixes the mechanical part.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ORG = Path(__file__).resolve().parent.parent
TEMPLATE = ORG / "templates" / "repo"

REQUIRED = [
    "CLAUDE.md",
    "AGENTS.md",
    ".claude/settings.json",
    ".claude/hooks/worktree-guard.mjs",
    ".claude/hooks/push-guard.mjs",
    ".claude/commands/go.md",
    ".claude/commands/reset.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/release.yml",
    ".githooks/pre-push",
    "scripts/verify.sh",
    "scripts/verify.steps.sh",
    ".agents/plans/README.md",
    "qa/README.md",
]
UI_ONLY = [".claude/hooks/design-guard.mjs", ".agents/designs/README.md"]  # required where a UI lives
# Repos that host pages: cvhome (console-ui, landing-ui, uaa-fe), the docs site
UI_REPOS = {"cvhome", "cvhome-saas.github.io"}

# What AGENTS.md must say, as regexes (any phrasing).
CONVENTIONS = {
    "worktree per change": r"worktree add",
    "plan = phases, phase = PR": r"[Pp]hase.*PR|PR per phase|one PR",
    "verify receipt before push": r"verify.*receipt|receipt.*push|verify-before-push|scripts/verify\.sh",
    "never push to main": r"[Nn]ever.*(commit|push).*main|main.*PR",
    "QA file": r"qa/.*-qa\.md|\[verified\]",
    "release by tag, not by hand": r"tag.*orchestrator|orchestrator.*tag|never.*tag.*by hand|Release",
}
UI_CONVENTIONS = {"design gate": r"design.*(portal|canvas|record)|\.agents/designs"}

# Hooks may legitimately differ from the template in these tokens (repo-specific names).
NORMALISE = [
    (r"extra/scripts/verify-before-push\.sh", "scripts/verify.sh"),
    (r"cvhome-verified", "verified"),
    (r"CVHOME_ALLOW_MAIN_WRITES", "ALLOW_MAIN_WRITES"),
]


def repos(names: list[str]) -> list[tuple[str, Path]]:
    text = (ORG / "repos.yaml").read_text()
    out = []
    for b in re.split(r"\n  - name: ", text)[1:]:
        name = b.split("\n", 1)[0].strip()
        if name == "orchestrator" or (names and name not in names):
            continue
        d = re.search(r"\n    dir: (\S+)", b)
        out.append((name, ORG / (d.group(1) if d else name)))
    return out


def normalised(text: str) -> str:
    for pat, rep in NORMALISE:
        text = re.sub(pat, rep, text)
    return text


def audit(name: str, path: Path) -> dict:
    if not (path / ".git").exists():
        return {"repo": name, "status": "MISSING-CHECKOUT"}
    required = REQUIRED + (UI_ONLY if name in UI_REPOS else [])
    missing = [f for f in required if not (path / f).exists()]
    stale = []
    for f in (".claude/hooks/worktree-guard.mjs", ".claude/hooks/push-guard.mjs", ".claude/hooks/design-guard.mjs", ".githooks/pre-push"):
        a, b = path / f, TEMPLATE / f
        if a.exists() and b.exists() and normalised(a.read_text()) != normalised(b.read_text()):
            stale.append(f)
    agents = (path / "AGENTS.md").read_text() if (path / "AGENTS.md").exists() else ""
    conv = dict(CONVENTIONS, **(UI_CONVENTIONS if name in UI_REPOS else {}))
    unstated = [k for k, rx in conv.items() if not re.search(rx, agents)]
    claude = (path / "CLAUDE.md").read_text().strip() if (path / "CLAUDE.md").exists() else ""
    notes = []
    if claude and claude != "@AGENTS.md" and (path / "AGENTS.md").exists():
        notes.append("CLAUDE.md is not the one-line @AGENTS.md import (two rulebooks drift)")
    status = "FAIL" if missing else ("WARN" if stale or unstated or notes else "OK")
    return {"repo": name, "status": status, "missing": missing, "stale": stale, "unstated": unstated, "notes": notes}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repos", nargs="*")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    results = [audit(n, p) for n, p in repos(a.repos)]
    if a.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            line = f"{r['status']:5} {r['repo']}"
            if r.get("missing"):
                line += f"\n      missing: {', '.join(r['missing'])}"
            if r.get("stale"):
                line += f"\n      stale vs template: {', '.join(r['stale'])}"
            if r.get("unstated"):
                line += f"\n      AGENTS.md does not state: {', '.join(r['unstated'])}"
            for n in r.get("notes", []):
                line += f"\n      {n}"
            print(line)
    return 1 if any(r["status"] in ("FAIL", "MISSING-CHECKOUT") for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
