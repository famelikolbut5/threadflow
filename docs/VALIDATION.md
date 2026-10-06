# Validation - 2026-10-06

Windows / Python 3.12 / Node 22 / pnpm 11.19.0. TypeScript checks and production builds passed locally.
All examples use synthetic data. Local tests do not imply successful hosted CI or quality on real customer data.

3 tests passed. Covers same-request replay, conflicting idempotency payload, invalid contact, failed notification retry and exactly one ticket/notification after repeated retries. Notifications are local records, not delivered to external systems.

Docker image built and started locally as a non-root user. Static UI and health endpoint returned successfully. A container request failed at notification, retry completed it, and the run history contained exactly one run.

## Selected interface verification

Final TypeScript/Vite build passed. Browser review at measured 1454 × 818 desktop and 443 px mobile width found no horizontal page overflow. Escape closes project dialogs. `preview.png` is an actual local application screenshot, not a design mockup.
A real run completed all 5 steps. A separate run failed at notification; retry completed the same ticket TF-613B398D. The canvas represents this sequential pipeline; it does not claim Telegram/Google Sheets integrations.
