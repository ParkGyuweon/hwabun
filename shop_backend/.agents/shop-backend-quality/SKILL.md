---
name: shop-backend-quality
description: Review and test shop_backend changes for purchase-flow correctness, authorization boundaries, and compatibility with the existing MySQL DDL without implementing new product features.
---

# Shop Backend: Quality Review and Tests

## Outcome

Independently verify the implemented Shop Backend. Add focused automated tests that do not require a live Docker database, and report actionable defects with evidence.

## Review focus

- Compare entity mappings and SQL assumptions with `shop_backend/mysql-erd.sql`.
- Verify the completed-purchase boundary: only `PAID` order items permit review, feedback, revenue, and settlement.
- Verify privacy and ownership boundaries: public reviews, private feedback, seller-owned brands, and administrator-only operations.
- Verify idempotent ordering/payment and that server-side product pricing is used.
- Verify the temporary identity contract is consistently `X-User-Id` plus `X-User-Role`.

## Test scope

- Add unit tests in `shop_backend/src/test/java` for deterministic rules that run without MySQL; prioritize authorization parsing and status/ownership guard behavior.
- Run the Gradle test task. If network or Docker prevents a test, state the exact command and blocker.
- Do not add test-only behavior to production code.

## Boundaries

- Do not redesign the schema, add endpoints, or implement new features.
- Do not change production source solely to silence a test. Report real production defects to the orchestrator instead.
- Keep tests and review output scoped to `shop_backend`.

## Reporting

- Report tests added and their result.
- List findings by severity with file and line evidence, expected behavior, and impact. Report no finding when none is substantiated.

## Branch and commits

- Work on the shared `feat/shop-backend` branch and stage only test and role-instruction files.
- Before each commit, read [docs/git-convention.md](../../../docs/git-convention.md).
- Use the required Korean `type(scope): 구체적인 작업 내용` convention and keep each commit to one cohesive change.
- Never commit generated `.gradle/` files or production code unless the orchestrator explicitly asks for a fix.
