from common.pdf_extractor import extract_pdf_text
from common.llm_extractor import extract_fields
from common.validation import validate_fields
from common.evaluation_engine import evaluate_report

def run_standard_workflow(pdf_path, report_id):
    """Conventional Python orchestration: functions and explicit control flow."""
    text, pages = extract_pdf_text(pdf_path)
    if not text.strip():
        raise ValueError("No selectable text was found. This POC does not OCR scanned PDFs yet.")
    extracted, mode = extract_fields(text, report_id)
    validation = validate_fields(extracted)
    evaluation = evaluate_report(extracted, validation)
    return {
        "report_id": report_id, "source_text": text, "pages": pages,
        "extracted": extracted, "current": dict(extracted),
        "validation": validation, "evaluation": evaluation,
        "extraction_mode": mode, "workflow": "standard_python",
        "processing_status": "PROCESSED", "review_status": "PENDING"
    }

def reevaluate(current):
    validation = validate_fields(current)
    evaluation = evaluate_report(current, validation)
    return validation, evaluation
