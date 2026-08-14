# Tasks

This directory contains local working files for in-progress tasks. Nothing here is committed — Jira and GitHub PRs are the record of truth.

## Workflow

1. Copy templates into `tasks/<task-name>/`:
   ```
   cp templates/spec.md tasks/<task-name>/spec.md
   cp templates/plan.md tasks/<task-name>/plan.md
   cp templates/execution.md tasks/<task-name>/execution.md
   ```
2. Fill in `spec.md` — define the problem and goals
3. Fill in `plan.md` — agree on the approach before coding
4. Work through `execution.md` — track progress as you go
5. Move to `completed/` when done:
   ```
   mv tasks/<task-name> completed/
   ```

## Directory structure

```
tasks/
  README.md          — this file (committed)
  <task-name>/       — gitignored, local only
    spec.md
    plan.md
    execution.md
completed/           — gitignored, local only
```
