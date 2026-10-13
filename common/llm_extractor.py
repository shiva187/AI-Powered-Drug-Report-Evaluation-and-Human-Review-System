import json
import os
import re
from datetime import date
from typing import Any
import requests
from dotenv import load_dotenv
from common.schemas import DrugReport

load_dotenv()

def _first(pattern: str, text: str, flags=re.IGNORECASE):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None

def _number(value):
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None

def _fallback_extract(text: str, report_id: str) -> dict[str, Any]:
    """Conservative local parser for benchmark PDFs; never guesses missing/conflicting values."""
    def field(*labels):
        for label in labels:
            # The extracted PDF text may place a value on the same line or next line.
            pattern = rf"^{re.escape(label)}\s*:\s*(.*?)\s*$"
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                if not value:
                    after = text[match.end():]
                    next_line = re.search(r"\S[^\n]*", after)
                    value = next_line.group(0).strip() if next_line else ""
                if not value or value.startswith("[INTENTIONALLY MISSING]") or value.startswith("[CONFLICT"):
                    return None
                return value
        return None

    def number(value):
        if value is None:
            return None
        match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
        return float(match.group(0)) if match else None

    drug_name = field("Drug name", "Generic name")
    manufacturer = field("Manufacturer", "Maker")
    product_code = field("Product code", "Item code")
    dosage_form = field("Dosage form")
    strength = field("Strength")
    batch_number = field("Batch number", "Lot / batch number", "Lot number", "Lot")
    manufacturing_date = field("Manufacturing date", "Date of manufacture", "Manufactured on")
    expiry_date = field("Expiry date", "Use before / expiry date", "Use before", "Expiry")

    assay_result = number(field("Assay result"))
    assay_range = field("Assay acceptance range", "Assay specification", "Assay range")
    assay_min = assay_max = None
    if assay_range:
        nums = re.findall(r"-?\d+(?:\.\d+)?", assay_range.replace(",", ""))
        if len(nums) >= 2:
            assay_min, assay_max = float(nums[0]), float(nums[1])
    purity_result = number(field("Purity result"))
    purity_min = number(field("Purity minimum"))
    moisture_result = number(field("Moisture result"))
    moisture_max = number(field("Moisture maximum"))

    # Detect contradictory assay values explicitly; don't select one based on order alone.
    notes = []
    conflict = re.search(r"summary reports assay\s*([\d.]+)\s*%.*?(?:secondary|laboratory) note reports assay\s*([\d.]+)\s*%", text, re.I | re.S)
    if conflict:
        assay_result = None
        notes.append(f"Conflicting assay values found: {conflict.group(1)}% and {conflict.group(2)}%; human review required.")
    else:
        secondary = re.search(r"secondary note reports assay\s*([\d.]+)\s*%", text, re.I)
        if secondary:
            notes.append(f"Conflicting assay value found in report note: {secondary.group(1)}%")

    if "[IMAGE-ONLY PAGE:" in text:
        notes.append("Image-only page could not be read; OCR is unavailable or produced no text.")
    if "fraction" in (assay_range or "").lower() and assay_result is not None:
        notes.append("Assay values are expressed as fractions; preserve source unit and confirm normalization before evaluation.")

    # Basic descriptive fields are captured when their explicit labels are present.
    extra = {
        "generic_name": field("Generic name"),
        "chemical_formula": field("Chemical formula"),
        "molecular_mass": field("Molecular mass"),
        "drug_class": field("Drug class"),
        "mechanism_of_action": field("Mechanism of action"),
        "active_ingredient": field("Active ingredient"),
        "excipients": field("Excipients"),
        "appearance": field("Appearance"),
        "storage_conditions": field("Storage conditions"),
        "manufacturing_site": field("Manufacturing site"),
        "ndc": field("NDC"), "gtin": field("GTIN"), "gstin": field("GSTIN"),
        "report_number": field("Report number"),
        "laboratory_name": field("Testing laboratory", "QC laboratory"),
        "testing_date": field("Testing date"),
        "indications": field("Indications"),
        "dosage_information": field("Dosage information"),
        "contraindications": field("Contraindications"),
        "warnings": field("Critical warnings", "Warnings"),
        "adverse_effects": field("Adverse effects"),
        "drug_interactions": field("Drug interactions"),
    }
    page_for = {}
    for key, value in {
        "drug_name": drug_name, "manufacturer": manufacturer, "product_code": product_code,
        "dosage_form": dosage_form, "strength": strength, "batch_number": batch_number,
        "manufacturing_date": manufacturing_date, "expiry_date": expiry_date,
        "assay_result": assay_result, "purity_result": purity_result, "moisture_result": moisture_result,
    }.items():
        if value is not None:
            m = re.search(rf"\[PAGE\s+(\d+)\].*?{re.escape(str(value))}", text, re.I | re.S)
            page_for[key] = int(m.group(1)) if m else 1
    qc_tests = []
    if assay_result is not None or assay_min is not None or assay_max is not None:
        qc_tests.append({"test_name": "Assay / potency", "method": "HPLC", "specification": assay_range,
                         "observed_value": assay_result, "unit": "% or source unit", "reported_status": None})
    return DrugReport(
        report_id=report_id, drug_name=drug_name, manufacturer=manufacturer, product_code=product_code,
        dosage_form=dosage_form, strength=strength, batch_number=batch_number,
        manufacturing_date=manufacturing_date, expiry_date=expiry_date,
        assay_result=assay_result, assay_min_limit=assay_min, assay_max_limit=assay_max,
        purity_result=purity_result, purity_min_limit=purity_min,
        moisture_result=moisture_result, moisture_max_limit=moisture_max,
        source_pages=page_for, field_evidence={}, extraction_notes=notes, qc_tests=qc_tests,
        **extra,
    ).to_dict()

def extract_fields(text: str, report_id: str) -> tuple[dict[str, Any], str]:
    """
    Uses the configured OpenAI-compatible TCS endpoint when credentials exist.
    Falls back to a deterministic parser for the bundled synthetic PDFs.
    Returns (field_dictionary, extraction_mode).
    """
    api_key = os.getenv("FRESCO_API_KEY", "").strip()
    base_url = os.getenv("FRESCO_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("FRESCO_MODEL", "").strip()
    verify_ssl = os.getenv("FRESCO_VERIFY_SSL", "true").lower() not in {"0", "false", "no"}
    if not api_key or api_key == "replace_with_your_api_key" or not base_url or not model:
        return _fallback_extract(text, report_id), "local_demo_parser"

    prompt = f"""
Extract fields from this synthetic pharmaceutical Certificate of Analysis. Do not infer missing values.
Return ONLY valid JSON using the full DrugReport schema. Include these groups when present:
product profile (drug_name, generic_name, brand_name, chemical_formula, molecular_mass, drug_class,
mechanism_of_action, active_ingredient, excipients, dosage_form, strength, appearance, storage_conditions);
identifiers and batch (manufacturer, manufacturing_site, product_code, ndc, gtin, gstin, report_number,
laboratory_name, batch_number, manufacturing_date, expiry_date, testing_date);
clinical/descriptive text (indications, dosage_information, contraindications, warnings, adverse_effects,
drug_interactions); core QC numbers (assay_result, assay_min_limit, assay_max_limit, purity_result,
purity_min_limit, moisture_result, moisture_max_limit); qc_tests (an array with one object per test row,
including test_name, method, specification, observed_value, unit, reported_status, and page when available);
source_pages (field-to-page mapping), field_evidence (field-to-short-verbatim-source-evidence mapping),
and extraction_notes.
Numbers for the legacy core QC fields must be JSON numbers or null. Keep other values as strings when appropriate.
Dates should be YYYY-MM-DD only when unambiguous; otherwise preserve the source text and explain ambiguity.
Do not infer values, normalize away meaningful units, or silently resolve conflicts. If contradictory values occur,
set the affected canonical value to null when no safe single value exists and explain both values in extraction_notes.
Do not treat example identifier formats as actual identifiers. Keep clinical text separate from batch QC results.
report_id must be "{report_id}". Never make up values. For image-only/OCR-uncertain text, say so in extraction_notes.

DOCUMENT TEXT:
{text[:18000]}
"""
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": "You extract structured data faithfully. Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=90,
            verify=verify_ssl,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
        parsed = json.loads(content)
        parsed["report_id"] = report_id
        report = DrugReport.model_validate(parsed).to_dict()
        return report, f"llm:{model}"
    except Exception as exc:
        # Keep the app usable for evaluation when API credentials or endpoint are unavailable.
        fallback = _fallback_extract(text, report_id)
        fallback.setdefault("extraction_notes", []).append(
            f"LLM extraction failed; local demo parser used ({type(exc).__name__})."
        )
        return fallback, "local_demo_parser_after_llm_error"
