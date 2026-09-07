#!/usr/bin/env bash
# Create a new cvhome-saas repository on GitHub from the org standard (templates/repo), register it in
# repos.yaml and .gitignore, clone it beside the others, and push the scaffold.
#
#   scripts/new-repo.sh <name> --kind <app|infra|tool|image|plugin|docs|ideas|mirror> \
#       --usage "one sentence: what it is for" [--tag] [--private] [--entry "README.md, src/"]
#
#   --tag      the repo receives the product tag vX.Y.Z on every release (docs/release-plan.md)
#   --private  default is public, like every other org repo
#
# A new *service* inside cvhome is NOT a new repo: follow cvhome's project-structure
# references/new-service.md. Use this for a genuinely separate deliverable: a shared library, a tool, an
# image, a plugin, a docs site.
set -euo pipefail
cd "$(dirname "$0")/.."

name=""; kind=""; usage=""; tag=false; visibility="--public"; entry="README.md, AGENTS.md"
while [ $# -gt 0 ]; do
  case "$1" in
    --kind) kind="$2"; shift 2 ;;
    --usage) usage="$2"; shift 2 ;;
    --entry) entry="$2"; shift 2 ;;
    --tag) tag=true; shift ;;
    --private) visibility="--private"; shift ;;
    -*) echo "unknown flag $1" >&2; exit 2 ;;
    *) name="$1"; shift ;;
  esac
done
[ -n "$name" ] && [ -n "$kind" ] && [ -n "$usage" ] || { sed -n 2,12p "$0"; exit 2; }
[[ "$name" =~ ^[a-z0-9][a-z0-9.-]*$ ]] || { echo "name must be kebab-case" >&2; exit 2; }
grep -q "^  - name: $name$" repos.yaml && { echo "$name is already in repos.yaml" >&2; exit 1; }
[ -e "$name" ] && { echo "./$name already exists" >&2; exit 1; }

echo "== creating github.com/cvhome-saas/$name ($visibility)"
gh repo create "cvhome-saas/$name" $visibility --description "$usage" --clone
cd "$name"
git switch -c main 2>/dev/null || true

echo "== scaffolding from templates/repo"
cp -R ../templates/repo/. .
python3 - "$name" "$usage" "$entry" <<'PY'
import pathlib, sys
name, usage, entry = sys.argv[1:4]
p = pathlib.Path("AGENTS.md"); t = p.read_text()
t = t.replace("__REPO__", name).replace("__USAGE__", usage).replace("__ENTRY__", entry)
t = t.replace("__GATES__", "```bash\nscripts/verify.sh        # every gate in scripts/verify.steps.sh, then the push receipt\n```\n\nList the real build, lint and test commands in `scripts/verify.steps.sh` and keep them identical to CI.")
p.write_text(t)
pathlib.Path("README.md").write_text(f"# {name}\n\n{usage}\n\nPart of [cvhome-saas](https://github.com/cvhome-saas). Contributor rules: `AGENTS.md`.\n")
PY
chmod +x scripts/verify.sh .githooks/pre-push 2>/dev/null || true
git config core.hooksPath .githooks

echo "== labels (release notes + version bumps)"
for l in "type/enhancement:0e8a16" "type/bug:d73a4a" "type/documentation:0075ca" "type/test:bfd4f2" "type/chore:ededed" "type/dependency-upgrade:fbca04" \
         "warn/api-change:b60205" "warn/behavior-change:e99695" "warn/deprecation:f9d0c4" "warn/regression:d93f0b" "warn/blocker:000000" "ignore-changelog:ffffff"; do
  gh label create "${l%%:*}" -R "cvhome-saas/$name" --color "${l##*:}" --force >/dev/null
done

echo "== first commit"
git add -A
git -c user.name="${GIT_AUTHOR_NAME:-$(git config user.name)}" commit -q -m "chore: scaffold from the cvhome-saas repo standard

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push -u origin main

cd ..
echo "== registering in repos.yaml and .gitignore"
python3 - "$name" "$kind" "$usage" "$entry" "$tag" <<'PY'
import pathlib, sys
name, kind, usage, entry, tag = sys.argv[1:6]
p = pathlib.Path("repos.yaml"); t = p.read_text().rstrip("\n")
block = f"\n\n  - name: {name}\n" + ("    tag: true\n" if tag == "true" else "") + f"    kind: {kind}\n    url: https://github.com/cvhome-saas/{name}.git\n    usage: {usage}\n    entry: [{entry}]\n"
p.write_text(t + block)
g = pathlib.Path(".gitignore"); s = g.read_text()
s = s.replace("# any other checkout dropped in here", f"/{name}/\n# any other checkout dropped in here")
g.write_text(s)
PY
echo
echo "Done. Next: fill scripts/verify.steps.sh and the 'Build, run and verify' section of $name/AGENTS.md,"
echo "add a scripts/impact.py rule if other repos will depend on it, then commit repos.yaml + .gitignore here."
