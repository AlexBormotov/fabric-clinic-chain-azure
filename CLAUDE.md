# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

## Claude Code wiring

- Rule sets: `.claude/skills` → symlink to `../.agents/skills`. On Windows this needs Developer
  Mode (or admin) and `git config core.symlinks true`; if a clone shows `.claude/skills` as a plain
  file, fix the symlink rather than copying the skills.
- Second-opinion subagents in `.claude/agents/` (`claude-thinking`, `codex-thinking`,
  `cursor-thinking`, `gemini-thinking`) run only when the owner explicitly names that route. Their
  output is advisory. They need `SECOND_OPINION_MONITOR_DIR`, set in `.claude/settings.local.json`;
  usage report: `python .claude/monitoring/second_opinion_usage.py report`.
- Session discipline follows `cherny-workflow`: plan first for anything non-trivial, track it in
  `tasks/todo.md`, read `tasks/lessons.md` at session start.

Build, test and deploy commands are added here once `plan.md` fixes the toolchain (a `Makefile`
that CI also runs is required by the repository standard).
