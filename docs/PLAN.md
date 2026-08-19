# Delivery plan

Each milestone requires its implementation tests plus `make check`.
1. Standards/docs — required repository documents exist; validate `test -f AGENTS.md`.
2. Infrastructure/manifests — locked packages and Compose; validate `docker compose config`.
3. Database/health — models, migration, probes; validate `pytest tests/unit`.
4. Authentication/security — Argon2, opaque sessions, CSRF; validate auth tests.
5. Detection core — normalization, segmentation, diagnostics, fake; validate detector tests.
6. ModernBERT — safe provider/readiness; validate `make model-smoke`.
7. Async analysis/privacy — Celery, encryption, ownership; validate API tests.
8. Documents — guarded TXT/PDF/DOCX; validate parser tests.
9. Public UI/analyzer — responsive real API flow; validate frontend tests/build.
10. Results — factors, paragraphs, export/print/feedback; validate result tests.
11. Account UI — history/settings; validate dashboard tests.
12. Admin — RBAC, health/settings/audit; validate admin tests.
13. Accessibility/E2E — primary flows; validate `make e2e`.
14. CI/production — hardened images/workflows/docs; validate Compose/build.
15. Reconciliation — `make check`, smoke, visual viewports, docs review.
