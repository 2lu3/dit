---
name: flow
description: Use when the user explicitly invokes the repository lifecycle as `flow p/plan`, `flow d/do`, `flow c/check`, or `flow a/auto`; recognize the current task, worktree, and PR state and run through the requested endpoint.
---

# Flow

`flow` is the single public lifecycle skill for this repository. The phase argument is required:

- `flow p` / `flow plan`: plan the work and register the task.
- `flow d` / `flow do`: implement the work.
- `flow c` / `flow check`: finish implementation, validate it, and create or update a Draft PR.
- `flow a` / `flow auto`: resume from the current state and complete the whole lifecycle through PR merge.

There is no `flow m` phase. `flow a` owns PR merge.

`flow c` and `flow a` are resumable endpoint commands. Before changing anything, identify the current state and print the phases that will run. Do not rerun completed work unnecessarily, and do not infer a task from a branch name.

## Authorization boundaries

An explicit phase invocation authorizes only the operations in that phase and any prerequisite phases that the endpoint requires:

- `p` authorizes task registration, but not implementation or Git delivery.
- `d` authorizes implementation and local validation, but not commit, push, PR creation, or PR merge.
- `c` authorizes the `p`/`d` prerequisites when needed, commit, merging the latest `origin/main` into the feature branch, push, and creating or updating one Draft PR. It NEVER authorizes merging a PR.
- `a` authorizes all required `p`/`d`/`c` work and PR merge. It is the only phase that merges a PR.

Never run the entire lifecycle for a bare `flow` request. Report the valid phases and stop. If a phase is invalid or ambiguous, stop before mutation.

## Recognize the current state

Use evidence in this order:

1. Use the task explicitly named by the user or registered earlier in the conversation. Do not guess a task from the current branch name.
2. When a task exists, read the repository README declaration `task_tracker: <name>` and use that tracker as the source of truth. Follow [タスクの状態管理](../../../.agents/rules/task-management.md).
3. Inspect the registered plan, current worktree changes, branch, relevant validation, and the open PR associated with the current branch. Use `gh api` for PR operations.
4. Determine the first incomplete endpoint from the evidence. If task or PR ownership, implementation completeness, or the requested scope is ambiguous, stop and report the ambiguity instead of guessing.

At the beginning of a resumable command, report a short state and execution plan, for example:

```text
現在状態: タスク登録済み、未実装
実行予定: d → c
```

The endpoint behavior is:

| Invocation | Required endpoint |
| --- | --- |
| `flow p` | task registered |
| `flow d` | implementation and local validation complete |
| `flow c` | validated Draft PR created or updated |
| `flow a` | PR merged and task completion verified |

If there is no target task, output `タスクが明記されていません。`, skip tracker mutations, task metadata, and closing references, and continue only with the user's explicit scope. Do not invent a task. For `flow p`, a task tracker declaration is still required before registration.

## `flow p` / `flow plan`

Turn the agreed plan into the source-of-truth task.

1. Confirm the requirements and intended scope from the conversation. Do not create a task from an unresolved or ambiguous plan.
2. Read the repository README for `task_tracker: <name>`. If absent, ask which tracker to use and do not infer one from installed tools or integrations.
3. Prefer `Execution mode: single` when no mode is specified. Use `multi` only when the user explicitly agrees. Record exactly one of these values in the task.
4. Create one task containing the requirements, implementation plan, key decisions, and a reconstructed `# User Prompt` that stands alone. Do not paste a chat log.
5. Stop after task registration. Do not implement, commit, push, create a PR, or merge.

If an equivalent task is already registered, do not create a duplicate; report the existing task and continue only when the user explicitly invoked a later endpoint.

## `flow d` / `flow do`

Reach the implementation endpoint.

1. If the plan/task endpoint has not been completed, run the `p` prerequisite first. If no target task exists, use no-task mode and the user's explicit request as the source of truth.
2. For a target task, move it to the tracker's In Progress equivalent before implementation and verify the result. If the tracker has no matching state, report it and stop.
3. Read exactly one `Execution mode: single` or `Execution mode: multi` from the task. Missing mode defaults to `single`; an invalid or ambiguous explicit mode stops the workflow.
4. For `single`, implement in the current task workspace. For `multi`, act as the parent coordinator: follow the registered decomposition, assign clear ownership, avoid concurrent edits to shared files, integrate results, resolve conflicts, and run the relevant validation as the parent.
5. Do not broaden the registered scope or invent subtasks. If the plan cannot be decomposed safely, stop and report the blocker.
6. Always update the relevant documentation for the implementation. This is mandatory for every `d`: update the affected README, docs, or agent instructions, and do not skip the update because the code change appears self-explanatory.
7. Always add or update tests for the implementation. This is mandatory for every `d`: cover the changed behavior and regression cases; merely running existing tests does not count as a test update. If no suitable test location or framework exists, stop and report the blocker instead of skipping the update.
8. Run the relevant local validation, including the tests added or updated in step 7, and report its result.

Do not commit, push, create/update a PR, or merge during `d`. A successful `d` leaves the work ready for `c` and keeps a tracked task In Progress.

## `flow c` / `flow check`

Reach the reviewable Draft PR endpoint. Run any missing `p` and `d` prerequisites first, then:

1. Run the relevant validation and stop on validation failures that are not an expected natural downstream failure.
2. Selectively stage the files belonging to this work. Use a commit message beginning with `feat:`, `fix:`, `refactor:`, `docs:`, or `chore:`. Never bypass pre-commit hooks.
3. Fetch the latest `origin/main` and merge it into the feature branch. Never rebase. Follow the [main-merge conflict policy](#main-merge-conflict-policy); resolve mechanically safe or semantically compatible conflicts and stop for human review when the intent is unclear, incompatible, or not verifiable.
4. Push the feature branch. Never force-push.
5. Query open PRs with `gh api`. Update the one identified PR for the current branch, or create exactly one new PR with `draft: true`. If an existing matching PR is not a draft, convert it to a draft through the GitHub GraphQL `convertPullRequestToDraft` mutation before updating it.
6. Write the PR title and body in Japanese. The body must contain, in order, `# Summary`, `# Items to Confirm / Review`, and `# User Prompt`. Include the implementation approach, validation, and key decisions. Reuse the registered task's `# User Prompt` when one exists. A tracked task's closing reference belongs at the very end; omit it in no-task mode.
7. After the PR is created or updated successfully, move the tracked task to the tracker's In Review equivalent and verify it. Do not change task metadata beyond the status transition.

`c` NEVER merges a PR. If multiple PRs could match or ownership cannot be determined confidently, stop instead of creating a second PR.

### Main-merge conflict policy

This policy applies to the `origin/main` merge in `flow c` and to the `c` prerequisite of `flow a`.

1. Before fetching or merging, run `git status --short` and confirm that there are no unrelated working-tree changes. After a conflict, keep the merge in progress and enumerate the unmerged paths with `git diff --name-only --diff-filter=U`. Inspect each path's combined diff with `git diff --cc -- <path>` and its stage 1 (merge base), stage 2 (ours), and stage 3 (theirs) entries.
2. A path is eligible for automatic resolution only when it is a normal text file with all three stages present and the file mode is the same in every stage, and one of these mechanical facts is true:
   - stage 2 is exactly equal to stage 1: take stage 3;
   - stage 3 is exactly equal to stage 1: take stage 2;
   - stage 2 and stage 3 are byte-for-byte identical: take either side.
   Compare the stage entries before choosing a side, for example by checking the mode and blob IDs from `git ls-files -u -- <path>`. Once an equality is established, use `git checkout --theirs -- <path>` or `git checkout --ours -- <path>` only for that individual path, then `git add -- <path>`. Do not infer safety from file age, line count, or which side is `main`.
3. For a path that is not covered by mechanical equality, recover both sides' intent before editing: compare the merge base, feature branch (ours), `main` (theirs), relevant commits, surrounding code or documentation, and affected tests. State what behavior or contract each side is adding, removing, or preserving. If the intents are compatible, construct a result that preserves both intents even when the conflict hunk overlaps; do not simply choose the newer side or delete one change. For generated or lock files, reconcile the source and regenerate them instead of hand-editing the generated output.
4. A semantic resolution is safe only when every conflict hunk has an explainable intent-level resolution and the relevant validation covers the affected behavior. Include the resolution rationale in the flow report or PR review notes. If the intents conflict, the intent is ambiguous, a rename/delete or binary/submodule/file-mode conflict cannot be mechanically resolved, or validation cannot establish the result, leave the merge in progress and request human review.
5. After resolving mechanically safe or semantically compatible paths individually, verify that no unmerged paths remain, `git diff --cached --check` passes, no conflict markers remain, and the relevant tests pass. Only then run `GIT_EDITOR=true git merge --continue`, rerun the relevant validation on the completed merge, and inspect `git status --short`.
6. Do not use `git merge -X ours/theirs`, `git checkout --ours/--theirs .`, broad marker replacement, `git merge --abort`, or any other blanket choice to avoid the intent review. For a human-review case, do not commit or push; report the unmerged path list, combined diffs, inferred intents, and the unresolved question.

## `flow a` / `flow auto`

Reach the terminal completed endpoint. Run missing `p`, `d`, and `c` prerequisites in order, then:

1. Confirm the exact PR to merge from the current flow, the user's explicit PR reference, or an unambiguous task closing reference. Do not guess between multiple PRs.
2. Check required checks, reviews, mergeability, and branch protection through `gh api`. If required checks fail, required reviews are missing, or the PR is not mergeable, stop and report the current state. Never bypass a required check or review.
3. If the PR is a draft, mark it ready for review through the GitHub GraphQL `markPullRequestReadyForReview` mutation.
4. Merge through `gh api` with `merge_method: merge`. Never squash-merge, rebase-merge, force-merge, or force-push.
5. After merge, move the tracked task to the tracker's Done equivalent or verify the tracker's automatic transition. Confirm the final PR and task state. In no-task mode, merge without changing task metadata.

If the PR is already merged, do not merge again; verify the local and tracker state and finish. If any prerequisite cannot be completed safely, stop at that phase and report what remains.
