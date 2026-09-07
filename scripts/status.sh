#!/usr/bin/env bash
# One line per checkout: branch, ahead/behind, dirty count, last commit.
set -uo pipefail
cd "$(dirname "$0")/.."
for d in */; do
  d=${d%/}
  [ -d "$d/.git" ] || continue
  branch=$(git -C "$d" branch --show-current 2>/dev/null)
  dirty=$(git -C "$d" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  ab=$(git -C "$d" rev-list --left-right --count "origin/$branch...$branch" 2>/dev/null | awk '{print "-"$1" +"$2}')
  last=$(git -C "$d" log -1 --format='%cs %s' 2>/dev/null | cut -c1-70)
  printf '%-24s %-28s %-10s dirty=%-3s %s\n' "$d" "$branch" "${ab:-?}" "$dirty" "$last"
done
