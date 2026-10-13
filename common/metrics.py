import json

def calculate_metrics(rows):
    total = len(rows)
    processed = sum(1 for r in rows if r.get("processing_status") == "PROCESSED")
    pending = sum(1 for r in rows if r.get("review_status") == "PENDING")
    approved = sum(1 for r in rows if r.get("review_status") == "APPROVED")
    rejected = sum(1 for r in rows if r.get("review_status") == "REJECTED")
    fully_evaluated = 0
    passed = 0
    for row in rows:
        try:
            evaluation = json.loads(row.get("evaluation_json") or "{}")
            statuses = [c.get("status") for c in evaluation.get("checks", [])]
            if statuses and all(s not in {"INCOMPLETE"} for s in statuses):
                fully_evaluated += 1
                if evaluation.get("overall_status") == "PASS":
                    passed += 1
        except Exception:
            pass
    # Processing success is successful processed reports / reports present in the app.
    return {
        "total_reports": total,
        "processed_reports": processed,
        "pending_review": pending,
        "approved_reports": approved,
        "rejected_reports": rejected,
        "processing_success_rate": round(processed / total * 100, 1) if total else 0.0,
        "evaluation_pass_rate": round(passed / fully_evaluated * 100, 1) if fully_evaluated else 0.0,
        "fully_evaluated_reports": fully_evaluated,
        "passed_reports": passed,
    }

def extraction_completeness(report, required_fields):
    present = sum(1 for f in required_fields if report.get(f) is not None and str(report.get(f)).strip() != "")
    return round(present / len(required_fields) * 100, 1) if required_fields else 0.0
