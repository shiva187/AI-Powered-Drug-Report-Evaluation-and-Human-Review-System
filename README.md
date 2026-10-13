# AI-Powered Drug Report Evaluation POC

A small, end-to-end demonstration comparing two orchestration approaches:
1. Standard Python workflow
2. LangGraph workflow

The application uses synthetic CoA-style PDFs, LLM-assisted extraction when configured, deterministic validation/evaluation rules, a Streamlit human-review UI, and SQLite persistence.

> **Safety note:** All bundled reports and acceptance criteria are fabricated. This is a software POC, not a pharmaceutical quality system and not suitable for real drug, clinical, patient-safety, or regulatory decisions.

## Features

- Generate five synthetic PDF test reports automatically.
- Upload a PDF or choose a bundled sample.
- Extract structured fields using a TCS Fresco Play AI Labs-compatible endpoint.
- Fall back to a local parser for the bundled demo PDFs if API credentials are not configured or the API call fails.
- Evaluate completeness, basic data validity, assay, purity, moisture, expiry, and extraction notes.
- Review and edit extracted fields.
- Re-evaluate after edits.
- Approve or reject reports.
- Save approved records and audit events in SQLite.
- Dashboard metrics: processing success, evaluation pass rate, extraction completeness.

## Requirements

Python 3.10+ recommended.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with the endpoint, key, and model available to you in TCS Fresco Play AI Labs.

Example values may look like:

```env
FRESCO_API_KEY=your_actual_key
FRESCO_BASE_URL=https://genailab.tcs.in/litellm/v1
FRESCO_MODEL=genailab-maas-gpt-4o
FRESCO_VERIFY_SSL=true
```

Use the endpoint and model authorized for your current lab environment. Do not commit `.env` or share API keys.

If TLS verification fails, do not permanently disable verification for production. Contact the environment administrator or use an approved certificate configuration.

## Run

```bash
streamlit run app.py
```

On first launch, the five legacy sample PDFs are generated under `data/sample_reports/`. Ten structured benchmark PDFs are bundled under `data/structured_benchmark/pdfs/` and are available in the Upload / Process selector.

## Demo path

1. Open **Upload / Process**.
2. Choose `01_complete_pass.pdf` and run extraction/evaluation.
3. Review the output and extraction mode.
4. Open **Human Review**, edit a field if needed, and choose Save edits & re-evaluate.
5. Approve or reject the report.
6. Open **Dashboard** and **Records & History**.
7. Repeat with the assay-fail, missing-expiry, expired-batch, and conflicting-assay samples.
8. Switch between Standard Python and LangGraph in the sidebar to compare orchestration.

## Architecture

- `common/`: shared extraction, schemas, validation, evaluation, database, metrics, synthetic PDF generation.
- `standard_python/`: conventional Python orchestration.
- `langgraph_version/`: LangGraph state, nodes, conditional routing, and graph construction.
- `app.py`: shared Streamlit dashboard and reviewer interface.

## Metrics

- **Processing success rate** = successfully processed reports / reports present in the application.
- **Evaluation pass rate** = reports with overall PASS / fully evaluated reports.
- **Extraction completeness** = non-empty required fields / required fields.

For a production evaluation, extraction correctness should be measured against a labelled ground-truth dataset, not merely field presence.

## Structured pharmaceutical report benchmark (v2.0)

The `data/structured_benchmark/` folder contains ten synthetic reports that preserve the four-section layout of the supplied Paracetamol example: Chemical & Core Profile; Administrative & Supply Chain Identifiers; Clinical Guidelines & Safety Protocol; Laboratory QC Grid. Each has narrative content and tables, with test variations for alternate terminology, multipage layout, missing fields, conflicting values, units, out-of-range values, invalid dates, and image-only OCR. `ground_truth.json` contains the expected values for offline evaluation.

The extraction schema now supports drug description fields, supply-chain and batch identifiers, clinical/descriptive fields, QC row arrays, page references, and source evidence. Existing core QC fields remain compatible with the current evaluator and review UI.

## Current limitations

- OCR is optional and requires the Tesseract OS binary plus `pytesseract` and `Pillow`; if unavailable, image-only pages are flagged rather than guessed.
- Bundled test PDFs are intentionally simple and generated for this demo.
- The local fallback parser remains intentionally limited; robust extraction of the expanded narrative and table fields depends on configuring the TCS LLM endpoint. Compare outputs with `data/structured_benchmark/ground_truth.json` before making accuracy claims.
- The graph uses an in-memory checkpointer in this demonstration. It does not provide durable graph resumption across restarts. Use a durable LangGraph checkpointer and stable thread IDs for a production workflow.
- The UI is a demonstration and does not implement authentication/role-based access controls.
- Database operations and review states should receive additional hardening before any real deployment.
- Document authenticity, approved product specifications, and regulatory checks are out of scope.

## Before using real documents

Obtain approval for document handling and model/API use, confirm privacy and retention requirements, source real acceptance limits from authorized specifications, validate extraction against ground truth, add OCR if needed, implement authentication and role-based access, and review database/audit requirements with the project owner.

## Synthetic benchmark dataset (added)

A more varied test set is available under `data/synthetic_dataset/`:

- `pdfs/`: ten fictional reports with prose, tables, alternate terms, a two-page report, missing data, conflicting values, unit conversion, out-of-range assay, invalid dates, and an image-only scan.
- `ground_truth.json`: expected canonical values and known issues for each PDF.
- `README.md`: dataset scope and caveats.

Use this dataset to evaluate extraction quality. The image-only scan intentionally has no selectable PDF text and should be marked as requiring OCR. The conflicting-assay report intentionally has no single safe assay value and should be routed to human review. All documents and specifications are synthetic demonstration data, not official pharmaceutical standards or regulatory advice.
