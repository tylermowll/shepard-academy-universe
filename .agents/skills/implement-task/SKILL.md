---
name: implement-task
description: Implement one approved Math Practice Tutor task with bounded scope, contract checks, tests, and evidence. Use when starting or continuing a task from docs/TASKS.md.
---

# Implement one task

1. Read root/nested AGENTS.md, the task, and only relevant README sections.
2. Inspect existing code and git status. Do not discard unrelated work.
3. Confirm dependencies and identify public contracts, security boundaries,
   migrations, and acceptance cases touched by this task.
4. Write a brief implementation/test plan, then implement the smallest working slice.
5. Add tests for the main path and at least the relevant failure/authorization path.
6. Run targeted checks, then the task's required gate. Fix implementation defects;
   never delete assertions or disable policy to make a test pass.
7. Inspect the diff for secrets, hidden-answer leaks, unsafe parsing, silent cloud
   fallback, generated-file drift, and unrequested infrastructure changes.
8. Update docs/TASKS.md with exact evidence. Report commands not run and why.

If blocked, preserve useful work, record the actual blocker, and stop at a clean
boundary. Do not start unrelated future phases or claim the application is complete.
