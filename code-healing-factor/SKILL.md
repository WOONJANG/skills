---
name: code-healing-factor
description: Verify and repair code changes through reproducible checks, bounded diagnosis and repair, and regression evidence. Use for requested code healing, execution-backed QA, or project-required verification of a code change.
---

# Code Healing Factor

Take a task and project root, with any user-specified constraints and verification level. In audit-only work, diagnose and report findings. Apply repairs when the request authorizes edits.

1. Discover the actual runtime, entry points, manifests, CI commands, AGENTS.md and Git status. Preserve existing edits and untracked files. Establish a baseline and distinguish pre-existing failures. Use isolated fixtures for destructive, security-sensitive or data-changing checks.
2. Write a compact specification covering objective, inputs, expected outputs, constraints, protected behavior, boundaries and acceptance criteria. Map significant behavioral requirements to execution check IDs in STANDARD and STRICT plans, with independent expected results. For LIGHT, record the expected behavior and focused check briefly. Choose the level and mandatory gates before editing. See [verification policies](references/verification.md).
3. Reproduce the failure or establish a focused failing test when practical. For STANDARD and STRICT changes, explain the problem, transformation and correctness argument in three sentences and compare them with the implementation. Trace preconditions, state changes, invariants and errors. Challenge assumptions with applicable invalid inputs, partial failures, retries, concurrent updates, old data and dependent callers. Turn consequential counterexamples into executable checks.
4. Execute the relevant checks, using the [evidence runner](references/runner.md) to record current-source results. Inspect actual assertions, exit codes and coverage. Diagnose failures using a minimized input, expected versus actual result, implicated path, and discriminating experiments. Classify the failure and record the confirmed root cause and discarded hypotheses. Repair the cause with a minimal change, rerun the failed checks, then test affected regressions. Never change a valid oracle, hide an error or remove behavior to make a check pass.
5. Record each repair attempt with a new strategy or new evidence. Default to eight attempts, pivot after two consecutive attempts without measurable progress, and stop after a failed pivot if progress is still absent. Stop sooner for missing authorization or an external blocker with no safe workaround. Changes in code alone are insufficient progress.
6. Review security, protected behavior and maintainability. Use a separate critical pass against the specification, diff and test oracles. For complex or high-risk changes, use an independent reviewer where available and authorized. Otherwise disclose the separate self-review and ground it in independent evidence. Fix confirmed blocking findings and repeat affected checks.
7. Finalize against the reviewed run ID and final source fingerprint. Report PASS only when every mandatory gate passes, no blocking findings remain and evidence is current. Report FAILED for confirmed failures and BLOCKED for unavailable verification. Give actual commands, outcomes, evidence paths, resolved and remaining findings, and any unverified requirements.

Explicit invocation works independently of hooks. For project instructions or optional Stop integration, see [activation](references/activation.md).
