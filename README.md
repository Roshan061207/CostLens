# CostLens

CostLens helps data-platform teams understand why modeled query costs are changing, prioritize workload improvements, and measure a fix. It is built around Exasol analytics, with a companion departmental-spend view.

## Problem and who it affects

Data-platform owners, analytics engineers, and finance teams can see that usage or spend has risen, but raw query logs and a single monthly total rarely explain which workloads drove the change. Without an understandable breakdown, teams may optimize the wrong query, disrupt useful work, or report savings that were never measured. CostLens connects workload patterns to an explainable cost model and a before/after measurement workflow.

All included query history, ledger rows, live-feed entries, and operations-health examples are **synthetic**. Modeled cost is an estimate, not an Exasol or cloud-provider invoice.

## Overview

## What it does
- **Introduction and navigation** (`/`): explains CostLens, its data sources and modelled cost, then links to department sign-in (`/org`) and platform analysis (`/platform`).
- **Platform cost** (`/platform`, lead/admin): growth split into users x queries per user x cost per query, repeated heavy queries, wide scans, peak load, unused tables, per-team forecast, pre-flight SQL check, and an apply-and-measure fix.
- The growth chart compares the first month with the selected month, showing modelled spend and query totals, absolute and percentage change, and each factor's share of the change.
- The live query feed uses synthetic demo rows; leads and admins can start it, while database fixes remain admin-only.
- **Organisation spend** (`/org`): team ledger with category share percentages, monthly totals and changes, and per-category budget, actual, variance, and utilization values. Chart and Files-tab values are always readable; other monetary values can be revealed with the Show/Hide amounts control. Also includes anomaly flags, a what-if savings simulator, a grounded "Ask CostLens", and a tamper-evident hash chain.
- **Add data three ways:** upload CSV/Excel, share a screen and read **only a box you draw around the numbers** (OCR on your device; dates, dark themes and repeated reads are handled), or type a row.
- **Access:** member sees only files they uploaded; lead sees their team and sets budgets; admin sees every team. All platform data endpoints require a login.
- **Operations health:** silent overnight pipeline failures, stale or disagreeing dashboards, waiting data requests.

## Setup and run locally

### Prerequisites
- Python 3.10+ and pip.
- A running Exasol instance reachable by the application. The defaults target a local Exasol Personal instance at `localhost:8563`.
- Git LFS is not required by the current project files.

### Windows PowerShell

From the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Set connection details and a persistent application signing secret before initializing the database:

```powershell
$env:EXA_DSN = "localhost:8563"
$env:EXA_USER = "sys"
$env:EXA_PASSWORD = "<your Exasol password>"
$env:COSTLENS_SECRET = "<a long random secret>"
```

The local connection defaults are defined in `db.py`; override them with `EXA_DSN`, `EXA_USER`, and `EXA_PASSWORD` for your environment. Do not commit credentials or secrets.

### Initialize demo data and users

Run these commands once against a fresh demo database:

```powershell
python setup_data.py
python secure.py seed
python secure.py demo-users
python secure.py demo Finance
python secure.py demo Marketing
python secure.py demo Ops
python secure.py demo Product
```

The sample department accounts are listed on the sign-in page and use the shared demo-only password `CostLensDemo2026!`. Do not use that password outside this synthetic demo. To create a separate admin account:

```powershell
python secure.py add YOUR_ADMIN_NAME Finance YOUR_ADMIN_PASSWORD admin
```

### Start and use

```powershell
uvicorn server:app --host 127.0.0.1 --port 8000
```

- Introduction: http://localhost:8000/
- Department dashboard and sign-in: http://localhost:8000/org
- Platform cost analysis: http://localhost:8000/platform

Optional: set `ANTHROPIC_API_KEY` to enable LLM-generated text in “Ask CostLens”; without it, the app uses a template answer.

### Tests

```powershell
python test_secure.py
python smoke_test.py
```

`test_secure.py` is an offline security/ledger test. `smoke_test.py` runs the analysis queries against the configured Exasol database.

## Deployment notes

The app is currently a Python/FastAPI application intended to run beside a reachable Exasol instance. For a local or internal demo, install requirements, configure the environment variables above, initialize the database, and run the Uvicorn command.

### Deploy a synthetic preview on Render

The repository includes a Render Blueprint in [`render.yaml`](./render.yaml) and pins the runtime to Python 3.12 in [`.python-version`](./.python-version).

1. Push `render.yaml` and `.python-version` to the `main` branch of the public GitHub repository.
2. In Render, choose **New → Blueprint**, connect `Roshan061207/CostLens`, and select the branch containing `render.yaml`.
3. Review the `costlens` web service and choose **Deploy Blueprint**. Render generates `COSTLENS_SECRET`.
4. When deployment finishes, open the service's `onrender.com` URL and verify `/`, `/platform`, and `/org`. Render enables `COSTLENS_DEMO_PREVIEW`: the sample department accounts sign in to a read-only dashboard with generated synthetic spend and operations data. It does not connect to Exasol or persist uploads.

To enable database-backed features later, use an Exasol instance reachable from Render (a database on your laptop or private network normally will not work). Disable `COSTLENS_DEMO_PREVIEW` in Render, add `EXA_DSN`, `EXA_USER`, and `EXA_PASSWORD` as secret environment variables, then initialize the database once from a machine that can connect to Exasol using `python setup_data.py`, `python secure.py seed`, and `python secure.py demo-users`. Redeploy and test `/org` and `/platform`.

The free web-service plan may sleep when idle, so the first request can take time. A public demo account is included in the app; deploy only with synthetic demo data and never use this setup for confidential or production data. The current Exasol connector disables certificate verification, so this configuration is a hackathon demo path, not a production security configuration. See the production notes below before exposing real data.

Before any shared or production deployment:
- Put the application behind HTTPS and a production-grade ASGI server/reverse proxy.
- Store `COSTLENS_SECRET`, Exasol credentials, and any LLM API key in a secret manager; never in source control.
- Replace synthetic query/operations data with approved, real Exasol monitoring sources and validate the model against billing data.
- Review database TLS/certificate verification and access controls for the target environment.
- Run `smoke_test.py` against the exact supported Exasol version. The SQL has not been verified on every Exasol release.

There is no Docker deployment configuration in this repository yet.

## Hackathon submission assets

- Pitch deck: [CostLens Exasol Hackathon](./CostLens_Exasol_Hackathon.pptx) (PowerPoint).
- Demo video: not included yet. Record a walkthrough of no more than 3 minutes and link it here before final submission.
- Public source repository: [Roshan061207/CostLens](https://github.com/Roshan061207/CostLens).
- Requirement-by-requirement status: [Hackathon submission checklist](./HACKATHON_SUBMISSION.md).
- Suggested short walkthrough: [Demo script](./DEMO_SCRIPT.md).
- The OCR engine, Chart.js and SheetJS are bundled in `static/vendor/` (about 21 MB), so the live feed and charts work with no internet.
- `python test_secure.py` runs offline tests. `python smoke_test.py` checks the SQL on your Exasol.
- If you ran an earlier version, drop `COSTLENS.LEDGER` and `COSTLENS.UPLOADS` first (a column was added).

## Real vs simulated
Real: every analysis query, the fix and its timing, access rules, hash chain. Simulated: query log, SALES, ops data, live feed generator, "wasted minutes". The growth chart reads the monthly query aggregates from `COSTLENS.QUERY_LOG` when connected (or generated preview data without the backend); the included setup creates synthetic query history. Cost units are a model (runtime seconds + scanned MB / 100), not an invoice. The change split allocates the total cost difference symmetrically across active users, queries per user, and cost per query.

## Limits
- Screen masking, blur and watermark **deter** casual capture. A web page cannot detect a phone camera; the watermark names the viewer so leaks can be traced.
- Data is not encrypted at rest, the hash chain can be recomputed by someone with full database write access, and OCR can misread digits, so rows are reviewed before saving. The privacy blur pauses while the live feed is on (the watermark stays). Screen sharing needs a desktop browser on localhost or HTTPS.
- Use HTTPS in any real deployment. The SQL has not been verified on every Exasol version; run `smoke_test.py` first.

Licence: MIT.
