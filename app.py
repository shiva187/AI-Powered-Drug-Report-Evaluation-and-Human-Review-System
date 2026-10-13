import json
import uuid
import tempfile
from pathlib import Path
from datetime import date

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from common.pdf_generator import generate_sample_pdfs
from common.schemas import REQUIRED_FIELDS, FIELD_LABELS
from common.database import (
    init_db, upsert_pending, save_review, approve_record, set_rejected,
    update_current, fetch_dashboard
)
from common.metrics import calculate_metrics, extraction_completeness
from standard_python.workflow import run_standard_workflow, reevaluate
from common.validation import validate_fields
from langgraph_version.workflow import run_langgraph_workflow, run_review_decision

load_dotenv()
ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = ROOT / "data" / "sample_reports"
DB_PATH = ROOT / "data" / "drug_reports.db"

st.set_page_config(page_title="Drug Report Evaluation POC", page_icon="🧪", layout="wide")
generate_sample_pdfs(SAMPLE_DIR)
init_db(DB_PATH)

st.title("🧪 AI-Powered Drug Report Evaluation & Human Review")
st.caption("Synthetic demonstration POC | Not for real pharmaceutical, clinical, or regulatory decisions")

with st.sidebar:
    st.header("Workflow configuration")
    workflow_choice = st.radio("Choose implementation", ["Standard Python", "LangGraph"])
    reviewer = st.text_input("Reviewer ID", value="demo.reviewer")
    st.divider()
    st.markdown("**Demo data**")
    st.caption("The bundled PDFs and acceptance limits are fabricated for software demonstration only.")
    st.caption("Optional OCR requires Tesseract plus pytesseract/Pillow. Document authenticity verification is not included.")

tab_dashboard, tab_process, tab_review, tab_history = st.tabs(
    ["📊 Dashboard", "📄 Upload / Process", "🧑‍⚖️ Human Review", "🗂️ Records & History"]
)

def load_rows():
    rows, approved_count, history_count = fetch_dashboard(DB_PATH)
    return rows, approved_count, history_count

def show_evaluation(evaluation):
    checks = evaluation.get("checks", [])
    if checks:
        df = pd.DataFrame(checks)
        st.dataframe(df, use_container_width=True, hide_index=True)
    status = evaluation.get("overall_status", "UNKNOWN")
    if status == "PASS":
        st.success(f"Overall automated result: {status} — human approval is still required.")
    elif status == "INCOMPLETE":
        st.warning(f"Overall automated result: {status} — missing information requires review.")
    else:
        st.error(f"Overall automated result: {status} — one or more checks require review.")

with tab_dashboard:
    rows, approved_count, history_count = load_rows()
    metrics = calculate_metrics(rows)
    cols = st.columns(5)
    cols[0].metric("Total reports", metrics["total_reports"])
    cols[1].metric("Processed", metrics["processed_reports"])
    cols[2].metric("Pending review", metrics["pending_review"])
    cols[3].metric("Approved", metrics["approved_reports"])
    cols[4].metric("Rejected", metrics["rejected_reports"])

    cols2 = st.columns(3)
    cols2[0].metric("Processing success", f'{metrics["processing_success_rate"]}%')
    cols2[1].metric("Evaluation pass rate", f'{metrics["evaluation_pass_rate"]}%',
                    help=f'{metrics["passed_reports"]} passed out of {metrics["fully_evaluated_reports"]} fully evaluated reports.')
    cols2[2].metric("Review actions recorded", history_count)

    st.subheader("Report status")
    if rows:
        display = []
        for row in rows:
            try:
                drug = json.loads(row["current_json"])
                ev = json.loads(row["evaluation_json"])
            except Exception:
                drug, ev = {}, {}
            display.append({
                "Report ID": row["report_id"], "File": row["filename"],
                "Drug": drug.get("drug_name"), "Batch": drug.get("batch_number"),
                "Automated result": ev.get("overall_status"),
                "Review status": row["review_status"],
                "Workflow": "LangGraph" if row.get("extraction_mode") and row.get("extraction_mode") else "Shared pipeline",
            })
        st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
    else:
        st.info("No reports processed yet. Open Upload / Process to start.")

with tab_process:
    st.subheader("Process a drug report")
    sample_files = sorted(SAMPLE_DIR.glob("*.pdf"))
    benchmark_dir = ROOT / "data" / "structured_benchmark" / "pdfs"
    benchmark_files = sorted(benchmark_dir.glob("*.pdf")) if benchmark_dir.exists() else []
    file_map = {p.name: p for p in sample_files}
    # Prefix benchmark names in the UI to avoid collisions with legacy demo samples.
    options = ["Upload your own PDF"] + [p.name for p in sample_files] + [f"Benchmark: {p.name}" for p in benchmark_files]
    selected = st.selectbox("Select a bundled synthetic report or upload a PDF", options)
    uploaded_file = None
    source_path = None
    filename = None

    if selected == "Upload your own PDF":
        uploaded_file = st.file_uploader("Upload PDF", type=["pdf"], key="pdf_upload")
        if uploaded_file:
            filename = uploaded_file.name
    else:
        if selected.startswith("Benchmark: "):
            filename = selected.replace("Benchmark: ", "", 1)
            source_path = benchmark_dir / filename
        else:
            source_path = SAMPLE_DIR / selected
            filename = selected
        st.caption(f"Selected synthetic test case: {filename}")

    if st.button("Run extraction and evaluation", type="primary", disabled=(selected == "Upload your own PDF" and uploaded_file is None)):
        report_id = f"DR-{uuid.uuid4().hex[:10].upper()}"
        temp_path = None
        try:
            if uploaded_file is not None:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.getbuffer())
                    temp_path = tmp.name
                pdf_path = temp_path
            else:
                pdf_path = str(source_path)

            with st.spinner(f"Running {workflow_choice} workflow..."):
                if workflow_choice == "LangGraph":
                    state = run_langgraph_workflow(pdf_path, report_id, filename)
                else:
                    state = run_standard_workflow(pdf_path, report_id)
                    state["filename"] = filename

                upsert_pending(
                    report_id, filename, state["extracted"], state["current"],
                    state["evaluation"], state["extraction_mode"], DB_PATH
                )
                save_review(report_id, "PROCESSED", state["extracted"], state["current"],
                            reviewer, f"Workflow: {workflow_choice}", DB_PATH)
                st.session_state["active_report_id"] = report_id
                st.session_state["active_state"] = state
                st.session_state["active_state"]["filename"] = filename
                st.session_state["active_state"]["workflow"] = workflow_choice
            st.success(f"Processed successfully. Report ID: {report_id}")
        except Exception as exc:
            st.error(f"Processing failed: {type(exc).__name__}: {exc}")
        finally:
            if temp_path and Path(temp_path).exists():
                Path(temp_path).unlink(missing_ok=True)

    state = st.session_state.get("active_state")
    if state:
        st.divider()
        st.subheader("Latest extraction")
        st.write(f"Report ID: `{state['report_id']}` | Mode: `{state['extraction_mode']}`")
        completeness = extraction_completeness(state["current"], REQUIRED_FIELDS)
        st.metric("Extraction completeness", f"{completeness}%")
        st.json(state["current"])
        show_evaluation(state["evaluation"])
        with st.expander("Extracted PDF text"):
            st.text(state.get("source_text", "")[:12000])

with tab_review:
    st.subheader("Human review queue")
    rows, _, _ = load_rows()
    pending = [r for r in rows if r["review_status"] == "PENDING"]
    if not pending:
        st.info("No pending reports. Process a report first.")
    else:
        labels = {}
        for row in pending:
            try:
                current = json.loads(row["current_json"])
                labels[row["report_id"]] = f'{row["report_id"]} — {current.get("drug_name") or "Unknown drug"} ({row["filename"]})'
            except Exception:
                labels[row["report_id"]] = row["report_id"]
        chosen_id = st.selectbox("Choose report to review", list(labels), format_func=lambda x: labels[x])
        row = next(r for r in pending if r["report_id"] == chosen_id)
        current = json.loads(row["current_json"])
        extracted = json.loads(row["extracted_json"])
        evaluation = json.loads(row["evaluation_json"])

        st.markdown("**Original extraction**")
        st.json(extracted)
        st.markdown("**Edit extracted fields below. Leave optional or missing values blank if unknown.**")
        with st.form(f"review_form_{chosen_id}"):
            edited = {}
            for field in REQUIRED_FIELDS:
                value = current.get(field)
                label = FIELD_LABELS.get(field, field)
                if field in {
                    "assay_result", "assay_min_limit", "assay_max_limit",
                    "purity_result", "purity_min_limit", "moisture_result", "moisture_max_limit"
                }:
                    try:
                        value = float(value) if value is not None else None
                    except (TypeError, ValueError):
                        value = None
                    edited[field] = st.number_input(label, value=value, format="%.3f",
                        key=f"{chosen_id}_{field}", placeholder="0.000")
                else:
                    edited[field] = st.text_input(label, value=str(value or ""),
                        key=f"{chosen_id}_{field}")
            # Preserve non-editable extraction metadata.
            edited["report_id"] = chosen_id
            edited["source_pages"] = current.get("source_pages", {})
            edited["extraction_notes"] = current.get("extraction_notes", [])
            review_comment = st.text_input("Reviewer comment", key=f"comment_{chosen_id}")
            c1, c2, c3 = st.columns(3)
            with c1:
                save_edit = st.form_submit_button("Save edits & re-evaluate")
            with c2:
                approve = st.form_submit_button("Approve and save")
            with c3:
                reject = st.form_submit_button("Reject report")

        if save_edit:
            validation, new_evaluation = reevaluate(edited)
            update_current(chosen_id, edited, new_evaluation, DB_PATH)
            save_review(chosen_id, "EDITED", current, edited, reviewer, review_comment, DB_PATH)
            if st.session_state.get("active_state", {}).get("report_id") == chosen_id:
                st.session_state["active_state"]["current"] = edited
                st.session_state["active_state"]["validation"] = validation
                st.session_state["active_state"]["evaluation"] = new_evaluation
            st.success("Edits saved and evaluation recalculated. Review the updated result before approval.")
            st.rerun()

        if approve:
            # Approve only after recalculating the current form values.
            validation, new_evaluation = reevaluate(edited)
            update_current(chosen_id, edited, new_evaluation, DB_PATH)
            save_review(chosen_id, "APPROVAL_REQUESTED", current, edited, reviewer, review_comment, DB_PATH)
            approve_record(chosen_id, edited, reviewer, DB_PATH)
            save_review(chosen_id, "APPROVED", current, edited, reviewer, review_comment, DB_PATH)
            if workflow_choice == "LangGraph":
                try:
                    run_review_decision({
                        "report_id": chosen_id, "current": edited,
                        "validation": validation, "evaluation": new_evaluation
                    }, "APPROVE", reviewer, review_comment)
                except Exception as exc:
                    st.warning(f"Database approval succeeded, but review graph transition could not be displayed: {exc}")
            st.success("Human approval recorded and approved record saved to SQLite.")
            st.rerun()

        if reject:
            save_review(chosen_id, "REJECTED", current, edited, reviewer, review_comment, DB_PATH)
            set_rejected(chosen_id, DB_PATH)
            if workflow_choice == "LangGraph":
                try:
                    run_review_decision({
                        "report_id": chosen_id, "current": edited,
                        "validation": validate_fields(edited), "evaluation": evaluation
                    }, "REJECT", reviewer, review_comment)
                except Exception:
                    pass
            st.warning("Report rejected. No approved record was created.")
            st.rerun()

        st.divider()
        st.subheader("Current evaluation")
        show_evaluation(evaluation)

with tab_history:
    st.subheader("Database records")
    rows, approved_count, history_count = load_rows()
    if rows:
        table = []
        for row in rows:
            try:
                cur = json.loads(row["current_json"])
                ev = json.loads(row["evaluation_json"])
            except Exception:
                cur, ev = {}, {}
            table.append({
                "Report ID": row["report_id"], "File": row["filename"],
                "Drug": cur.get("drug_name"), "Batch": cur.get("batch_number"),
                "Automated status": ev.get("overall_status"),
                "Review status": row["review_status"], "Updated": row["updated_at"]
            })
        st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
    st.metric("Approved records in database", approved_count)
    st.metric("Review-history events", history_count)
    if st.button("Refresh records"):
        st.rerun()

st.divider()
st.caption("POC limitation: sample criteria are fabricated; uploaded reports should be sanitized and approved for processing. This application does not verify document authenticity or establish clinical safety/efficacy.")
