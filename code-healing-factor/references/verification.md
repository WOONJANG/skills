# Verification policies

Freeze the gate plan before implementation. Add gates as risk becomes clearer. Mark optional irrelevant gates NOT_APPLICABLE with a justification. Document external blockers. The runner records execution and attestations. Codex evaluates semantic coverage and decides which checks actually prove the requirements.

| Gate | Objective |
| --- | --- |
| G01 | Requirements, constraints, scope and traceability |
| G02 | Feynman explanation checked against code |
| G03 | Adversarial counterexamples |
| G04 | Syntax and types |
| G05 | Static analysis |
| G06 | Unit behavior |
| G07 | Integration behavior |
| G08 | Runtime through supported entry points |
| G09 | Boundary and negative cases |
| G10 | Security |
| G11 | Regression protection |
| G12 | Maintainability |
| G13 | Separate critical review |
| G14 | Final acceptance and evidence inspection |

LIGHT covers G01 and G14 plus applicable syntax, formatting and regression checks. STANDARD adds G02, G03, G11 and G12, plus applicable execution gates G04–G09 and separate review G13 for meaningful changes. STRICT adds mandatory integration, runtime, boundary, security, regression and separate review for high-risk changes, including payments, migrations, auth and customer data. Plan execution-based checks for every significant behavioral requirement. Escalate when evidence contradicts the plan.

Test known examples with independent oracles. Use characterization or differential checks for compatibility, property and metamorphic checks for invariants, and isolated mutation tests when an apparently good suite might miss critical defects. Prefer existing tooling. Compare baseline and final behavior with the same fixtures.

## Profiles

- PHP 8.x. Discover PHP and Composer versions, lint applicable changed files with php -l, and execute application tests covering runtime contracts, sessions, uploads and DB calls.
- MariaDB. Use an isolated database. Check bound parameters, migrations against old data, constraints, transaction rollback, duplicates, concurrency and failure recovery.
- JavaScript, HTML and CSS. Check module loading and normal browser workflows, console errors, form failures, duplicate submissions, keyboard interaction and representative mobile and desktop viewports. Compare screenshots when a trusted baseline exists.
- Financial and settlement. Use STRICT. Check independent worked examples for discounts, fees, taxes, rounding order, refunds and negative or zero transactions. Use minor units or decimal arithmetic as appropriate. Assert reconciliation and residual rules from the actual contract.
- CSV and XLSX. Check encoding, headers, missing columns, duplicates, empty rows, dates, money, totals and import/export round trips.
- LocalStorage and IndexedDB. Check reload, old schema, malformed state, quota failures, interrupted writes and migration recovery with synthetic data.

## Findings and review

Classify each confirmed finding, for example LOGIC_ERROR, DATA_INTEGRITY_ERROR, RACE_CONDITION, SECURITY_VULNERABILITY, API_CONTRACT_VIOLATION, TEST_DEFECT or ENVIRONMENT_ERROR. Record a stable ID, location, reproduction, expected and actual results, root cause, strategy and affected regressions. Record severity from INFORMATIONAL through CRITICAL. Block unresolved HIGH and CRITICAL security findings by default. Check authorization, injection, session handling, path traversal, disclosure, secrets and dependencies when applicable. Never use production data or transmit private code without authorization.

Review whether abstractions, dependencies and duplication are justified. Simplify only when tests preserve contracts and failure behavior. For the separate critical pass, challenge coverage gaps, circular oracles, plausible wrong outputs and completion claims with counterexamples or evidence independent of the implementation explanation.
