from typing import Any, TypedDict

class DrugWorkflowState(TypedDict, total=False):
    report_id: str
    pdf_path: str
    filename: str
    source_text: str
    pages: dict[int, str]
    extracted: dict[str, Any]
    current: dict[str, Any]
    validation: dict[str, Any]
    evaluation: dict[str, Any]
    extraction_mode: str
    processing_status: str
    review_status: str
    reviewer_decision: str
    reviewer: str
    review_comment: str
    error: str
    workflow: str
