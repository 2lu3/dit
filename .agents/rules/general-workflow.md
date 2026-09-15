---
applies_to: [all]
---

# General

## Global Cursor Settings

- Keywords: **MUST** / **NEVER** = mandatory. **SHOULD** = recommended unless there is a clear reason not to. **MAY** = optional.

## General

- When today's date is needed, MUST run the `date` command to get it — NEVER rely on model's internal knowledge
- MUST VERIFY the actual implementation before writing API/tool documentation — NEVER guess API names or parameters

## Change Scope Rules

- MUST only make changes that were explicitly requested — NEVER autonomously add features, tools, packages, or content
- MUST ask first if something additional seems needed
- MUST keep PR comments, commit messages, and documentation concise unless asked otherwise

## Creating and Revising Outputs

- When creating or revising explanations, proposals, plans, code, or other outputs, MUST consider who will use them, what information they can access, and what they need to understand, decide, or do. This includes both people and other agents.
- MUST distinguish information available to the intended user from context available only in the current conversation, and include the context needed for correct understanding, decisions, and execution. SHOULD adapt terminology and detail to the user's knowledge and working environment.
- MUST integrate revision requests into the overall purpose, requirements, and constraints. MUST judge each element's necessity, placement, length, and emphasis by its role in the final output. NEVER treat the fact that something was requested or corrected as evidence of its importance.
- MUST consider what the intended user would assume or do if a statement were omitted. MUST state conditions needed to prevent unintended interpretations or actions, and remove statements that serve no purpose in the final output.
- Before delivering, MUST check whether the intended user can reach the intended understanding, decisions, and actions using only the information actually available to them.

## Work Recap

- After finishing work, MUST briefly explain what was done in the final response using bullet points

## Debugging Approach

- MUST diagnose the ROOT CAUSE before attempting fixes
- NEVER try quick-fix approaches (hardcoding values, JSON workarounds)
- MUST check git history/diffs when investigating regressions
- MUST understand what the user is asking before jumping to debug

## Skills

- Prefer these skills over doing the work by hand:

  - **Task registration / implementation / delivery** → `flow p`, `flow d`, `flow c`, `flow a`
  - **Code review / refactor / security** → `/code-review`, `/simplify`, `/security-review`
  - **Web run / perf** → `run`, `/web-perf` (see Web Design & Debugging)

## Web Design & Debugging

- MUST prefer the dedicated skills over driving a browser by hand:
  - `run` — launch and drive the project's app to see a change working / take a screenshot
  - `/web-perf` — web performance investigation
