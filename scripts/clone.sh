#!/usr/bin/env bash
# Clone (or fetch) every active repo from repos.yaml into this directory.
#   scripts/clone.sh            # active repos only
#   scripts/clone.sh --all      # also deprecated/reference repos, for reading history
set -euo pipefail
cd "$(dirname "$0")/.."
want_all=${1:-}
python3 - "$want_all" <<'PY'
import re, subprocess, sys, pathlib
want_all = sys.argv[1] == "--all"
text = pathlib.Path("repos.yaml").read_text()
blocks = re.split(r"\n  - name: ", text)[1:]
for b in blocks:
    name = b.split("\n", 1)[0].strip()
    status = re.search(r"status: (\w+)", b).group(1)
    url = re.search(r"url: (\S+)", b).group(1)
    if name == "orchestrator":
        continue
    if status != "active" and not want_all:
        continue
    p = pathlib.Path(name)
    if p.is_dir():
        print(f"== {name}: fetch")
        subprocess.run(["git", "-C", name, "fetch", "--prune"], check=False)
    else:
        print(f"== {name}: clone ({status})")
        subprocess.run(["git", "clone", url, name], check=False)
PY
