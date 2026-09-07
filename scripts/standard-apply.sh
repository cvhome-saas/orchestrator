#!/usr/bin/env bash
# Bring one checkout up to the org repo standard, on a branch, without overwriting what the repo already
# has. Mechanical part only: the agent then fills AGENTS.md placeholders / merges the conventions section
# into an existing AGENTS.md, lists the real gates in scripts/verify.steps.sh, verifies, and ships a PR.
#
#   scripts/standard-apply.sh <repo> [--branch chore/repo-standard]
set -euo pipefail
cd "$(dirname "$0")/.."
repo="${1:?repo name}"; branch="${3:-chore/repo-standard}"
dir=$(python3 - "$repo" <<'PY'
import re, sys, pathlib
t = pathlib.Path("repos.yaml").read_text()
for b in re.split(r"\n  - name: ", t)[1:]:
    n = b.split("\n",1)[0].strip()
    if n == sys.argv[1]:
        d = re.search(r"\n    dir: (\S+)", b); print(d.group(1) if d else n); break
PY
)
[ -d "$dir/.git" ] || { echo "no checkout $dir (scripts/clone.sh $repo)"; exit 1; }
ui=false; case "$repo" in cvhome|cvhome-saas.github.io) ui=true ;; esac

# cvhome enforces its worktree rule; everything else gets a plain branch.
if [ "$repo" = "cvhome" ]; then
  wt="$dir/.claude/worktrees/${branch//\//-}"
  [ -d "$wt" ] || git -C "$dir" worktree add --no-track "$wt" -b "$branch" origin/main
  work="$wt"
else
  git -C "$dir" fetch origin --quiet
  git -C "$dir" switch -c "$branch" origin/main 2>/dev/null || git -C "$dir" switch "$branch"
  work="$dir"
fi

added=()
copy() {  # copy <template-relative> only if absent
  local f="$1"
  if [ ! -e "$work/$f" ]; then mkdir -p "$work/$(dirname "$f")"; cp "templates/repo/$f" "$work/$f"; added+=("$f"); fi
}
for f in CLAUDE.md .claude/settings.json .claude/hooks/worktree-guard.mjs .claude/hooks/push-guard.mjs \
         .claude/commands/go.md .claude/commands/reset.md .github/PULL_REQUEST_TEMPLATE.md .github/release.yml \
         .githooks/pre-push scripts/verify.sh scripts/verify.steps.sh .agents/plans/README.md qa/README.md; do
  copy "$f"
done
if $ui; then copy .claude/hooks/design-guard.mjs; copy .agents/designs/README.md; fi
if [ ! -e "$work/AGENTS.md" ]; then
  copy AGENTS.md
  usage=$(python3 -c "
import re,sys,pathlib
t=pathlib.Path('repos.yaml').read_text()
for b in re.split(r'\n  - name: ', t)[1:]:
    if b.split('\n',1)[0].strip()=='$repo': print(re.search(r'usage: (.*)', b).group(1)); break")
  entry=$(python3 -c "
import re,pathlib
t=pathlib.Path('repos.yaml').read_text()
for b in re.split(r'\n  - name: ', t)[1:]:
    if b.split('\n',1)[0].strip()=='$repo': print(re.search(r'entry: \[(.*)\]', b).group(1)); break")
  sed -i '' -e "s#__REPO__#$repo#g" -e "s#__USAGE__#$usage#g" -e "s#__ENTRY__#$entry#g" \
      -e 's#__GATES__#```bash\nscripts/verify.sh        \# every gate in scripts/verify.steps.sh, then the push receipt\n```\n\nTODO: list the real build, lint and test commands in `scripts/verify.steps.sh`, identical to CI.#' "$work/AGENTS.md"
fi
# A CLAUDE.md that is not the import: keep it, the agent merges by hand.
if [ -e "$work/CLAUDE.md" ] && [ "$(tr -d '[:space:]' < "$work/CLAUDE.md")" != "@AGENTS.md" ] && [ ! -e "$work/AGENTS.md" ]; then
  echo "NOTE: $repo has a full CLAUDE.md and no AGENTS.md — rename CLAUDE.md to AGENTS.md, merge the standard conventions in, and make CLAUDE.md '@AGENTS.md'."
fi
# .gitignore entries
for line in ".claude/worktrees/" ".DS_Store"; do
  grep -qxF "$line" "$work/.gitignore" 2>/dev/null || { echo "$line" >> "$work/.gitignore"; added+=(".gitignore:$line"); }
done
chmod +x "$work/scripts/verify.sh" "$work/.githooks/pre-push"
git -C "$work" config core.hooksPath .githooks
echo "== $repo ($work) on $branch"
printf '  added %s\n' "${added[@]:-nothing}"
echo "Next: merge the 'Working conventions (org standard)' section of templates/repo/AGENTS.md into $work/AGENTS.md if it existed,"
echo "      fill scripts/verify.steps.sh with the real gates, run scripts/verify.sh, then commit and open the PR (repo-standard skill)."
