#!/usr/bin/env node
/**
 * Org-level dispatcher for sub-repo guard hooks.
 *
 * Each sub-repo may ship its own PreToolUse guards under `<repo>/.claude/hooks/` — cvhome has
 * `worktree-guard.mjs` (no edits in the primary checkout) and `push-guard.mjs` (no push without a
 * verify receipt, never to main). Those only run when Claude Code's project dir *is* that repo. A
 * session started here, at the org root, would silently bypass them. This wrapper restores them:
 * it works out which sub-repo a Write/Edit path or a `git push` belongs to and runs that repo's
 * guard with `cwd` inside the repo, so the guard's own `git rev-parse` logic resolves correctly.
 *
 * Generic on purpose: any sub-repo that adds `.claude/hooks/worktree-guard.mjs` or
 * `.claude/hooks/push-guard.mjs` is guarded automatically. Exit codes and stderr pass through.
 */
import {existsSync, readFileSync} from 'node:fs';
import {dirname, isAbsolute, relative, resolve} from 'node:path';
import {spawnSync} from 'node:child_process';

const ORG = resolve(dirname(new URL(import.meta.url).pathname), '..', '..');

let raw = '';
try {
  raw = readFileSync(0, 'utf8');
} catch {
  process.exit(0);
}
let input;
try {
  input = JSON.parse(raw);
} catch {
  process.exit(0);
}

/** First path segment under ORG, if `p` is inside it and that segment is a git checkout. */
function subrepoOf(p) {
  if (typeof p !== 'string' || p === '') return null;
  const abs = resolve(process.cwd(), p);
  const rel = relative(ORG, abs);
  if (rel === '' || rel.startsWith('..') || isAbsolute(rel)) return null;
  const top = rel.split(/[\\/]/)[0];
  const dir = resolve(ORG, top);
  return existsSync(resolve(dir, '.git')) ? {name: top, dir} : null;
}

function run(repo, guard, cwd) {
  const script = resolve(repo.dir, '.claude', 'hooks', guard);
  if (!existsSync(script)) return;
  const r = spawnSync(process.execPath, [script], {cwd, input: raw, encoding: 'utf8', env: process.env});
  if (r.stderr) process.stderr.write(r.stderr);
  if (r.stdout) process.stdout.write(r.stdout);
  process.exit(r.status ?? 0);
}

const tool = input?.tool_name ?? '';
const ti = input?.tool_input ?? {};

if (/^(Write|Edit|MultiEdit|NotebookEdit)$/.test(tool)) {
  const target = ti.file_path ?? ti.path ?? ti.notebook_path;
  const repo = subrepoOf(target);
  if (repo) run(repo, 'worktree-guard.mjs', repo.dir);
  process.exit(0);
}

if (tool === 'Bash') {
  const command = String(ti.command ?? '');
  if (!/\bgit\b[^\n]*\bpush\b/.test(command)) process.exit(0);
  const m = /\bgit\s+-C\s+(\S+)/.exec(command) ?? /^\s*cd\s+(\S+)\s*(?:&&|;)/.exec(command);
  const dir = m ? m[1].replace(/^["']|["']$/g, '') : process.cwd();
  const repo = subrepoOf(dir);
  if (repo) run(repo, 'push-guard.mjs', resolve(process.cwd(), dir));
  process.exit(0);
}
process.exit(0);
