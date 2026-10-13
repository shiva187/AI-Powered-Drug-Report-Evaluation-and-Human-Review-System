from datetime import date
from common.schemas import REQUIRED_FIELDS, FIELD_LABELS

def validate_fields(report: dict) -> dict:
    missing = []
    invalid = []
    for field in REQUIRED_FIELDS:
        value = report.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)

    for field in ("manufacturing_date", "expiry_date"):
        value = report.get(field)
        if value:
            try:
                date.fromisoformat(str(value)[:10])
            except ValueError:
                invalid.append(f"{FIELD_LABELS.get(field, field)} is not a valid ISO date.")

    for field in (
        "assay_result", "assay_min_limit", "assay_max_limit",
        "purity_result", "purity_min_limit", "moisture_result", "moisture_max_limit"
    ):
        value = report.get(field)
        if value is not None:
            try:
                float(value)
            except (TypeError, ValueError):
                invalid.append(f"{FIELD_LABELS.get(field, field)} must be numeric.")

    if report.get("assay_min_limit") is not None and report.get("assay_max_limit") is not None:
        if float(report["assay_min_limit"]) > float(report["assay_max_limit"]):
            invalid.append("Assay minimum is greater than assay maximum.")

    return {"missing_fields": missing, "invalid_items": invalid,
            "is_complete": len(missing) == 0, "is_valid": len(invalid) == 0}
