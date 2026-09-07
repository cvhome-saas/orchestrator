#!/usr/bin/env bash
# Clone (or fetch) repos from repos.yaml into this directory.
#   scripts/clone.sh                 # every active repo
#   scripts/clone.sh --all           # also deprecated/reference repos, for reading history
#   scripts/clone.sh cvhome lcl      # just these (any status)
# Prints one line per repo: cloned | fetched, plus ahead/behind against origin/<default>.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - "$@" <<'PY'
import re, subprocess, sys, pathlib
args = sys.argv[1:]
want_all = "--all" in args
names = [a for a in args if not a.startswith("--")]
text = pathlib.Path("repos.yaml").read_text()
blocks = re.split(r"\n  - name: ", text)[1:]
known = {}
for b in blocks:
    name = b.split("\n", 1)[0].strip()
    known[name] = (re.search(r"status: (\w+)", b).group(1), re.search(r"url: (\S+)", b).group(1))
unknown = [n for n in names if n not in known]
if unknown:
    sys.exit(f"not in repos.yaml: {', '.join(unknown)}")
for name, (status, url) in known.items():
    if name == "orchestrator":
        continue
    if names and name not in names:
        continue
    if not names and status != "active" and not want_all:
        continue
    p = pathlib.Path(name)
    if p.is_dir() and (p / ".git").exists():
        subprocess.run(["git", "-C", name, "fetch", "--prune", "--quiet"], check=False)
        try:
            branch = subprocess.check_output(["git", "-C", name, "branch", "--show-current"], text=True).strip()
            ab = subprocess.check_output(["git", "-C", name, "rev-list", "--left-right", "--count", f"origin/{branch}...{branch}"], text=True).split()
            state = f"fetched  branch={branch} behind={ab[0]} ahead={ab[1]}"
        except subprocess.CalledProcessError:
            state = "fetched  (no upstream)"
    else:
        r = subprocess.run(["git", "clone", "--quiet", url, name], check=False)
        state = "cloned" if r.returncode == 0 else f"clone FAILED ({url})"
    print(f"{name:24} {status:10} {state}")
PY
