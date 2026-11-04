# Code Healing Factor

A Codex skill for verifying and repairing code changes. It records executed checks, review findings, and the source fingerprint associated with the result.

## Install

Clone this repository as `code-healing-factor` under your personal `~/.agents/skills` directory or a project's `.agents/skills` directory. Keep the complete directory together and reload Codex if the skill does not appear.

## Use

Invoke `$code-healing-factor` in Codex and describe what to verify or repair. For example:

> Use $code-healing-factor to reproduce and fix the import failure, then verify the affected behavior and report the checks you ran.

The evidence runner requires Python 3.11 or later. See the [runner guide](references/runner.md) for plans, evidence, and finalization. See the [activation guide](references/activation.md) for optional Stop hook setup.

## Evidence

- Linked requirement checks must pass before the run can pass.
- Finalization keeps unresolved findings and reuses the reviewed execution.
- Optional JUnit XML reports supply execution and skip counts.
- Git scope reporting flags visible worktree changes outside the fingerprint.

Finalization rejects assessments for a different project, source fingerprint or execution. It refreshes Git scope while preserving the inventory recorded during the original run.

## Test

Run from the repository root:

```sh
python -B -m unittest discover -s tests -v
```
