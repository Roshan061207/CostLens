# Exasol Hackathon Submission Checklist

| Requirement | Status | Evidence / remaining action |
|---|---|---|
| Clear problem statement: who has the problem and why it matters | Ready | README explains the impact on data-platform owners, analytics engineers, and finance teams. |
| Public code repository | Ready | [Roshan061207/CostLens](https://github.com/Roshan061207/CostLens) is public and contains the application source. |
| Pitch deck in PDF or PPT format | Ready | [CostLens_Exasol_Hackathon.pptx](./CostLens_Exasol_Hackathon.pptx) |
| Demo video, maximum 3 minutes | Pending | No video file or public video URL is included. Record a walkthrough under three minutes and add its link to the README. A suggested narration and timing are in [DEMO_SCRIPT.md](./DEMO_SCRIPT.md). |
| README with overview, setup, and usage | Ready | README includes the project problem, feature overview, Windows setup, demo initialization, usage URLs, and tests. |
| Deployment instructions and run guide | Partial | README documents local setup and a read-only Render synthetic preview using `render.yaml`. Live Exasol mode requires a reachable database and credentials; the demo is not production-hardened. |
| Apache 2.0 or MIT license | Ready | [LICENSE](./LICENSE) is MIT. |

## Important demo disclosure

The included query history, department ledger data, operations-health examples, and live-feed rows are synthetic. Cost units are modeled estimates, not provider invoices. Keep this disclosure in the pitch and demo.

## Before submission

1. Record and upload the short demo video; add its public link to README.
2. Decide whether to configure hosted Exasol for the Render service so sign-in, ledger storage, and Exasol-backed analysis work; add the public service URL if hosted access is required.
3. Confirm the public repository, deck, license, setup instructions, and synthetic-data disclosure remain visible before submission.
