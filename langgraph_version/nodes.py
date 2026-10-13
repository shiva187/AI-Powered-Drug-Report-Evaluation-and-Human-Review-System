from common.pdf_extractor import extract_pdf_text
from common.llm_extractor import extract_fields
from common.validation import validate_fields
from common.evaluation_engine import evaluate_report

def ingest_pdf(state):
    try:
        text, pages = extract_pdf_text(state["pdf_path"])
        if not text.strip():
            return {"error": "No selectable text found; scanned PDF OCR is not included in this POC."}
        return {"source_text": text, "pages": pages}
    except Exception as exc:
        return {"error": f"PDF ingestion failed: {type(exc).__name__}: {exc}"}

def extract_fields_node(state):
    if state.get("error"):
        return {}
    report, mode = extract_fields(state["source_text"], state["report_id"])
    return {"extracted": report, "current": dict(report), "extraction_mode": mode}

def validate_node(state):
    if state.get("error"):
        return {}
    return {"validation": validate_fields(state["current"])}

def evaluate_node(state):
    if state.get("error"):
        return {"processing_status": "ERROR", "review_status": "PENDING"}
    validation = state.get("validation") or validate_fields(state["current"])
    return {
        "validation": validation,
        "evaluation": evaluate_report(state["current"], validation),
        "processing_status": "PROCESSED",
        "review_status": "PENDING",
    }

def route_after_ingest(state):
    return "error" if state.get("error") else "extract"

def route_after_evaluate(state):
    return "error" if state.get("error") else "await_review"

def await_review_node(state):
    # UI is the human interface; graph pauses at this state boundary.
    # Reviewer decision is supplied from Streamlit in a subsequent graph invocation.
    return {"review_status": "PENDING"}

def route_decision(state):
    decision = state.get("reviewer_decision", "").upper()
    if decision == "APPROVE":
        return "approved"
    if decision == "REJECT":
        return "rejected"
    if decision == "EDIT":
        return "reevaluate"
    return "await_review"

def reevaluate_node(state):
    current = state.get("current") or {}
    validation = validate_fields(current)
    return {"validation": validation, "evaluation": evaluate_report(current, validation),
            "review_status": "PENDING", "reviewer_decision": ""}

def approval_node(state):
    return {"review_status": "APPROVED"}

def rejection_node(state):
    return {"review_status": "REJECTED"}
