---
name: shop-backend-commerce
description: Implement catalog and purchase-flow APIs in shop_backend, from products through a mock PAID order, while preserving existing schema and ownership boundaries.
---

# Shop Backend: Catalog and Commerce

## Outcome

Implement a consumer purchase flow and seller product-management APIs backed by the existing MySQL schema.

## Scope

- Product, variant, image, and attribute read APIs for consumers.
- Seller-authorized product create, update, and sale-status management.
- Server-side cart persistence and cart item operations.
- Order creation from a cart and idempotent mock payment completion to `PAID`.
- Accurate item snapshots and payment-time totals for later review, feedback, and settlement.

## Domain invariants

- Only a `PAID` order item represents a completed purchase.
- A single order may contain products from more than one brand.
- The server calculates prices and totals; do not trust client-submitted amounts.
- Product modification must verify the requesting seller owns the product's brand.

## Boundaries

- Treat `shop_backend/mysql-erd.sql` as the current schema authority. Do not redesign or rewrite its DDL.
- Own packages under `com.cosmetic.shopbackend.catalog` and `com.cosmetic.shopbackend.commerce` only.
- Reuse the identity/brand public interfaces for authorization; do not implement authentication or brand administration.
- Do not implement reviews, feedback, settlement, dashboards, or administrator screens.

## Quality bar

- Test price calculation, repeated payment safety, cross-seller product protection, and multi-brand order handling.
- Run the relevant Gradle test suite before reporting completion.

## Branch and commits

- Work on the shared `feat/shop-backend` branch and stage only this role's files.
- Before each commit, read [docs/git-convention.md](../../../docs/git-convention.md).
- Use the required Korean `type(scope): 구체적인 작업 내용` convention and keep each commit to one cohesive change.
- Never commit generated `.gradle/` files or another agent's package.
