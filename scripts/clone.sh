#!/usr/bin/env bash
# Clone (or fetch) the org's repos from repos.yaml into this directory.
#   scripts/clone.sh                 # every repo in the manifest
#   scripts/clone.sh cvhome lcl      # just these
# Prints one line per repo: cloned | fetched, plus behind/ahead against origin/<branch>.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - "$@" <<'PY'
import re, subprocess, sys, pathlib
names = sys.argv[1:]
text = pathlib.Path("repos.yaml").read_text()
blocks = re.split(r"\n  - name: ", text)[1:]
known = {}
for b in blocks:
    name = b.split("\n", 1)[0].strip()
    d = re.search(r"\n    dir: (\S+)", b)
    known[name] = (re.search(r"url: (\S+)", b).group(1), d.group(1) if d else name)
unknown = [n for n in names if n not in known]
if unknown:
    sys.exit(f"not in repos.yaml: {', '.join(unknown)}")
for name, (url, d) in known.items():
    if name == "orchestrator" or (names and name not in names):
        continue
    p = pathlib.Path(d)
    if (p / ".git").exists():
        subprocess.run(["git", "-C", d, "fetch", "--prune", "--quiet"], check=False)
        try:
            branch = subprocess.check_output(["git", "-C", d, "branch", "--show-current"], text=True).strip()
            ab = subprocess.check_output(["git", "-C", d, "rev-list", "--left-right", "--count", f"origin/{branch}...{branch}"], text=True).split()
            state = f"fetched  branch={branch} behind={ab[0]} ahead={ab[1]}"
        except subprocess.CalledProcessError:
            state = "fetched  (no upstream)"
    else:
        r = subprocess.run(["git", "clone", "--quiet", url, d], check=False)
        state = "cloned" if r.returncode == 0 else f"clone FAILED ({url})"
    print(f"{name:24} -> {d:24} {state}")
PY
