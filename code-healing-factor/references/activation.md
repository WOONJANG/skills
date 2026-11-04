# Activation and optional Stop hook

Use `$code-healing-factor` with a code verification or repair request. Select the skill through the supported picker if your client uses mentions. Current Codex discovers personal skills under `$HOME/.agents/skills` and repository skills under `.agents/skills`. Copy the complete skill folder to the chosen location. Check for an existing copy before installing. Reload Codex if the skill does not appear. Implicit selection depends on task matching. [Build skills](https://learn.chatgpt.com/docs/build-skills)

To opt a project in, add this instruction to its existing AGENTS.md after reviewing and preserving its current rules.

> For implementation and bug fixes, apply $code-healing-factor before declaring completion. Preserve existing behavior, execute relevant tests and report missing evidence and unresolved blockers.

## Stop adapter

Explicit invocation needs no hooks. The optional adapter consumes a documented Codex Stop event and emits JSON. It is a bounded prompt to finish verification when feasible. It performs read-only validation and makes at most one continuation per armed turn using stop_hook_active. A cancelled turn, unrelated session or turn, or absent arming file is ignored. Malformed or concurrently written state yields a diagnostic when detectable.

In a trusted project, merge the [hook example](hooks.example.json) into the existing project .codex/hooks.json. Replace the absolute paths for the native Python interpreter, script, project root, frozen plan and task state. Keep the task state outside the project. Review the exact command and trust it using Codex's hook trust UI or /hooks where available. Installation of the skill alone does not enable it. [Codex hooks](https://learn.chatgpt.com/docs/hooks)

Arm only a known session and turn using a private state/arm.json with session_id, turn_id and cancelled set to false. Use IDs supplied by your supported host integration. Arm before running verification so reports from prior turns cannot qualify. Set cancelled to true to disarm a cancelled run. If IDs are unavailable, leave it unarmed and use explicit invocation. The hook checks the source fingerprint, normalized plan, required gates and repair policy. Use a fresh state directory per task and clear arming data at the end. The hook never executes test commands or spawns another repair process.

## Activation evaluation

In a fresh Codex session with the skill discoverable, try explicit invocation on an isolated bug fixture, then a matching unqualified request to verify and repair code with regression evidence, then an unrelated writing request. Verify tool execution and observed skill selection through the client. A metadata check or a simulated Stop event is separate evidence from live Codex invocation and hook lifecycle testing.

