---
name: shop-backend-operations
description: Implement post-purchase customer voice, seller operations, settlement, dashboard read APIs, and administrator operations in shop_backend.
---

# Shop Backend: Feedback and Operations

## Outcome

Implement the post-purchase features that turn completed commerce data into seller and administrator operations.

## Scope

- Purchased-item eligibility checks for reviews and private improvement feedback.
- Public product-review reads; owner/admin-only feedback and AI-analysis reads.
- Persistence-facing interfaces for feedback summaries and categories. Keep AI generation replaceable; do not couple it to a specific model provider.
- Monthly settlement views calculated only from `PAID` order items, with `PENDING` and `COMPLETED` state handling.
- Seller dashboard read APIs for core performance, feedback, and settlement values.
- Administrator endpoints for seller/brand/product approval and settlement completion when supported by the schema.

## Domain invariants

- Reviews are public; improvement feedback is never visible to other consumers.
- A seller can view only feedback and settlements for brands they own.
- Revenue and settlement never use behavior-log events as their source of truth.
- Use `order_item` as the unit for purchase entitlement and multi-brand settlement allocation.

## Boundaries

- Treat `shop_backend/mysql-erd.sql` as the current schema authority. Do not redesign or rewrite its DDL.
- Own packages under `com.cosmetic.shopbackend.feedback`, `settlement`, `dashboard`, and `admin` only.
- Consume `PAID` order-item and identity/brand interfaces; do not edit their internal business logic.
- Do not build Kafka, Spark, recommendation, or frontend code in this task.

## Quality bar

- Test review/feedback privacy, purchased-item eligibility, cross-seller isolation, and settlement state transitions.
- Run the relevant Gradle test suite before reporting completion.

## Branch and commits

- Work on the shared `feat/shop-backend` branch and stage only this role's files.
- Before each commit, read [docs/git-convention.md](../../../docs/git-convention.md).
- Use the required Korean `type(scope): 구체적인 작업 내용` convention and keep each commit to one cohesive change.
- Never commit generated `.gradle/` files or another agent's package.
