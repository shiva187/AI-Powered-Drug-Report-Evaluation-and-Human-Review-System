from datetime import date
from common.schemas import FIELD_LABELS

def evaluate_report(report: dict, validation: dict | None = None) -> dict:
    checks = []

    def add(name, status, observed=None, criterion=None, explanation="", category="quality"):
        checks.append({
            "check_name": name, "status": status, "observed_value": observed,
            "criterion": criterion, "explanation": explanation, "category": category
        })

    # Required fields
    missing = (validation or {}).get("missing_fields", [])
    if missing:
        add("Required-field completeness", "INCOMPLETE",
            observed=", ".join(missing),
            criterion="All required fields present",
            explanation="Some mandatory fields are missing.", category="completeness")
    else:
        add("Required-field completeness", "PASS",
            observed="All required fields present",
            criterion="All required fields present",
            explanation="All configured required fields are present.", category="completeness")

    invalid_items = (validation or {}).get("invalid_items", [])
    if invalid_items:
        add("Data validation", "FAIL", observed="; ".join(invalid_items),
            criterion="Valid dates and numeric values",
            explanation="One or more data validation checks failed.", category="validation")
    else:
        add("Data validation", "PASS", observed="Dates and numeric values checked",
            criterion="Valid dates and numeric values",
            explanation="No basic type/date validation errors were detected.", category="validation")

    # Assay range
    result, low, high = report.get("assay_result"), report.get("assay_min_limit"), report.get("assay_max_limit")
    if result is None or low is None or high is None:
        add("Assay compliance", "INCOMPLETE", result, f"{low}–{high}",
            "Assay result or configured limit is missing.", category="quality")
    elif float(low) <= float(result) <= float(high):
        add("Assay compliance", "PASS", result, f"{low}–{high}",
            "Assay result is within the configured synthetic limits.", category="quality")
    else:
        add("Assay compliance", "FAIL", result, f"{low}–{high}",
            "Assay result is outside the configured synthetic limits.", category="quality")

    # Purity minimum
    result, low = report.get("purity_result"), report.get("purity_min_limit")
    if result is None or low is None:
        add("Purity compliance", "INCOMPLETE", result, f">= {low}",
            "Purity result or minimum limit is missing.", category="quality")
    elif float(result) >= float(low):
        add("Purity compliance", "PASS", result, f">= {low}",
            "Purity result meets the configured synthetic minimum.", category="quality")
    else:
        add("Purity compliance", "FAIL", result, f">= {low}",
            "Purity result is below the configured synthetic minimum.", category="quality")

    # Moisture maximum
    result, high = report.get("moisture_result"), report.get("moisture_max_limit")
    if result is None or high is None:
        add("Moisture compliance", "INCOMPLETE", result, f"<= {high}",
            "Moisture result or maximum limit is missing.", category="quality")
    elif float(result) <= float(high):
        add("Moisture compliance", "PASS", result, f"<= {high}",
            "Moisture result meets the configured synthetic maximum.", category="quality")
    else:
        add("Moisture compliance", "FAIL", result, f"<= {high}",
            "Moisture result exceeds the configured synthetic maximum.", category="quality")

    # Batch expiry
    expiry = report.get("expiry_date")
    if not expiry:
        add("Batch validity", "INCOMPLETE", expiry, "Expiry date must be present and current",
            "Cannot verify batch validity without an expiry date.", category="batch")
    else:
        try:
            expiry_date = date.fromisoformat(str(expiry)[:10])
            today = date.today()
            if expiry_date < today:
                add("Batch validity", "FAIL", expiry_date.isoformat(), f">= {today.isoformat()}",
                    "The batch expiry date is in the past.", category="batch")
            else:
                add("Batch validity", "PASS", expiry_date.isoformat(), f">= {today.isoformat()}",
                    "The batch has not passed its stated expiry date.", category="batch")
        except ValueError:
            add("Batch validity", "FAIL", expiry, "Valid ISO date",
                "Expiry date could not be interpreted.", category="batch")

    notes = report.get("extraction_notes") or []
    if notes:
        add("Document consistency / notes", "FLAGGED", observed="; ".join(notes),
            criterion="No unresolved contradictions",
            explanation="Extraction notes or potential contradictions require human review.",
            category="consistency")
    else:
        add("Document consistency / notes", "PASS", observed="No contradictions detected by parser",
            criterion="No unresolved contradictions",
            explanation="No contradiction was detected by the current extraction checks. This is not a guarantee of authenticity.",
            category="consistency")

    statuses = [c["status"] for c in checks]
    if "FAIL" in statuses or "FLAGGED" in statuses:
        overall = "FLAGGED"
    elif "INCOMPLETE" in statuses:
        overall = "INCOMPLETE"
    else:
        overall = "PASS"

    return {"checks": checks, "overall_status": overall}
