# Subagent Templates

This directory contains prompt templates for specialized subagent roles. When using Claude Code's Agent tool, read the relevant template and include its rules and output format in the agent prompt.

## Available Subagents

| Template | Purpose | When to Use |
|----------|---------|-------------|
| `planner.md` | Turn vague goals into implementation plans | Before starting non-trivial work |
| `architect.md` | Design feature structure | Before adding new components or changing architecture |
| `implementer.md` | Make targeted code changes | When executing a plan or making specific edits |
| `reviewer.md` | Review code for issues | After changes are made, before merging |
| `debugger.md` | Find root causes of failures | When something is broken or tests fail |
| `tester.md` | Add and run meaningful tests | When improving test coverage |
| `refactorer.md` | Improve code structure without behavior changes | When cleaning up existing code |
| `git-pr.md` | Manage git operations and PRs | When committing or creating pull requests |

## How to Use

When spawning an agent via the Agent tool, read the template file and incorporate its content into your prompt. Example:

```
Read /path/to/.agents/reviewer.md for your role definition and rules, then review the following changes: ...
```

Each template defines:
- **Mission** — the subagent's primary objective
- **Rules** — constraints and priorities
- **Workflow** — step-by-step process to follow
- **Output Format** — structured format for results
