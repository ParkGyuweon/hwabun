---
name: shop-backend-identity
description: Implement account, access control, merchant verification, and brand-management features in shop_backend without changing unrelated commerce or analytics code.
---

# Shop Backend: Identity and Brand Management

## Outcome

Implement the API layer for consumer, seller, and administrator access; seller verification; and seller-owned brand management.

## Scope

- Account registration and login foundations appropriate to the existing Spring Boot dependencies.
- Role-based authorization at API boundaries: consumer, seller, administrator.
- Seller verification status lifecycle: `PENDING`, `VERIFIED`, `MISMATCH`, `RETRY_NEEDED`, `INACTIVE`.
- Seller access to only the brands they own; administrator access to all brands.
- Brand creation, read, update, and permitted status changes.

## Boundaries

- Treat `shop_backend/mysql-erd.sql` as the current schema authority. Do not redesign or rewrite its DDL.
- Own packages under `com.cosmetic.shopbackend.identity` and `com.cosmetic.shopbackend.brand` only. Create shared primitives only after coordinating with the orchestrator.
- Do not implement product, cart, order, review, feedback, settlement, or dashboard endpoints.
- Expose stable DTOs and authorization helpers that other domains can consume without calling internal services.

## Quality bar

- Unauthorized and cross-seller access must return a safe error rather than data.
- Write focused Spring Boot tests for ownership and role boundaries.
- Run the relevant Gradle test suite before reporting completion.

## Branch and commits

- Work on `codex/identity-brand` and stage only this role's files.
- Before each commit, read [docs/git-convention.md](../../docs/git-convention.md).
- Use the required Korean `type(scope): 구체적인 작업 내용` convention and keep each commit to one cohesive change.
- Never commit generated `.gradle/` files or another agent's package.
