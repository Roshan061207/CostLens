# CostLens Hackathon Demo Script

Target runtime: about 2 minutes 30 seconds. Keep the final recording under 3 minutes.

## 0:00–0:20 — Problem

“Data-platform teams can see usage and costs rise, but a monthly total does not explain which workloads drove the change. CostLens connects Exasol workload patterns to an explainable cost model, practical optimization ideas, and a way to measure a fix.”

## 0:20–0:55 — Explain the change

Open `/platform`. Show the monthly comparison and growth attribution.

“This demo compares the first and selected months. It separates modeled cost growth into active users, queries per user, and cost per query. In this synthetic example, modeled cost rises about 48%, while query volume rises about 13%. The cost-per-query factor is the largest contributor, so the team has a clear place to investigate.”

## 0:55–1:30 — Find an action

Show repeated queries, wide scans, peak-hour load, and pre-flight analysis.

“CostLens surfaces repeated heavy queries and wide scans, and suggests targeted actions rather than applying a blanket limit. The pre-flight check compares a submitted SQL shape with workload history; it does not execute the pasted SQL.”

## 1:30–1:55 — Measure

Show the before/after proof workflow.

“For a selected optimization, CostLens measures query time before and after and records the result. This makes the improvement measurable instead of assuming that a recommendation produced savings.”

## 1:55–2:20 — Department spend

Open `/org`, then the spend and Files views.

“The companion department view shows spend shares, monthly amounts and changes, budgets versus actuals, and team-scoped files. It supports reviewed CSV/Excel upload, manual entry, and local OCR of a user-selected screen area.”

## 2:20–2:30 — Close with disclosure

“The project demonstrates the workflow on Exasol. Included query, ledger, operations, and live-feed data are synthetic; modeled costs are estimates, not invoices. A production rollout would connect approved telemetry and calibrate the model to real billing.”
