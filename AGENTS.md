# Project Agent Boundary: AI_actuarial_inforsearch

## Identity

- Project: `AI_actuarial_inforsearch`
- Repo path: `/home/ec2-user/work/AI_actuarial_inforsearch`
- Remote: `https://github.com/ferryhe/AI_actuarial_inforsearch`
- Worker role: 旧的一体化信息检索/RAG 产品，作为经验和可抽取代码来源。

## Hard Boundaries

1. Treat this repository as the only writable workspace for this project.
2. Do not read, edit, or infer requirements from sibling repositories unless the current task explicitly names them.
3. Do not copy secrets, local `.env` files, generated credentials, or unreviewed artifacts between projects.
4. Do not commit, push, create PRs, delete branches, rewrite history, or run destructive cleanup without explicit user approval.
5. Before editing, run `git status --short --branch` and identify unrelated local changes.
6. Keep changes narrow and project-scoped. For cross-project contracts, edit only this repo's side unless the task explicitly covers multiple repos.

## Branch Policy

- `main` is treated as the clean baseline tracking `origin/main`.
- New work starts from latest `main` on a task branch.
- Do not implement directly on `main`.
- Commit/push/PR actions require explicit approval from 北老师.

## Required Startup Routine

Every Codex worker run must:

1. Read this `AGENTS.md`.
2. Read `.hermes/project-status.md` if present.
3. Run `git status --short --branch`.
4. Restate the active repo, branch, files in scope, and whether sibling repos are off-limits.
5. Only then edit files.

## Verification Policy

- Prefer focused tests for touched code.
- For CLI contract changes, verify `--help`, `--json` output, schema fixtures, and idempotent reruns.
- For frontend/API work, run local service/build checks and browser smoke when UI behavior changes.
- If checks cannot run, record the exact blocker and the next command to run.

## Reporting Format

End every run with:

- Project and branch
- Files changed
- Checks run and results
- Uncommitted/untracked files noticed
- Blockers or decisions needed
- Recommended next action

Also update `.hermes/project-status.md` with the latest state.
