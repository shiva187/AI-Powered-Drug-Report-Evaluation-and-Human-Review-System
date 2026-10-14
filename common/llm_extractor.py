import json
import os
import re
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from common.schemas import DrugReport


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# ============================================================
# GENERAL HELPERS
# ============================================================

def _number(value):
    """Return a float only for an unambiguous plain numeric value."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    value = str(value).strip().replace(",", "")

    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
        return float(value)

    return None


def _append_note(data: dict[str, Any], note: str) -> None:
    """Add a note without discarding existing extraction notes."""
    notes = data.get("extraction_notes")

    if notes is None:
        notes = []
    elif isinstance(notes, str):
        notes = [notes]
    elif not isinstance(notes, list):
        notes = [str(notes)]

    if note not in notes:
        notes.append(note)

    data["extraction_notes"] = notes


# ============================================================
# LOCAL FALLBACK EXTRACTION
# ============================================================

def _fallback_extract(text: str, report_id: str) -> dict[str, Any]:
    """
    Conservative local parser for labelled benchmark PDF text.

    This parser does not use the LLM. It extracts only values
    that can be found in explicitly labelled document text.
    """

    def field(*labels):
        for label in labels:
            pattern = rf"^{re.escape(label)}\s*:\s*(.*?)\s*$"

            match = re.search(
                pattern,
                text,
                re.IGNORECASE | re.MULTILINE,
            )

            if not match:
                continue

            value = match.group(1).strip()

            if not value:
                next_line = re.search(r"\S[^\n]*", text[match.end():])
                value = next_line.group(0).strip() if next_line else ""

            if (
                not value
                or value.startswith("[INTENTIONALLY MISSING]")
                or value.startswith("[CONFLICT")
            ):
                return None

            return value

        return None

    drug_name = field("Drug name", "Generic name")
    manufacturer = field("Manufacturer", "Maker")
    product_code = field("Product code", "Item code")
    dosage_form = field("Dosage form")
    strength = field("Strength")

    batch_number = field(
        "Batch number",
        "Lot / batch number",
        "Lot number",
        "Lot",
    )

    manufacturing_date = field(
        "Manufacturing date",
        "Date of manufacture",
        "Manufactured on",
    )

    expiry_date = field(
        "Expiry date",
        "Use before / expiry date",
        "Use before",
        "Expiry",
    )

    assay_result = _number(field("Assay result"))

    assay_range = field(
        "Assay acceptance range",
        "Assay specification",
        "Assay range",
    )

    assay_min = None
    assay_max = None

    if assay_range:
        nums = re.findall(
            r"-?\d+(?:\.\d+)?",
            assay_range.replace(",", ""),
        )

        if len(nums) >= 2:
            assay_min = float(nums[0])
            assay_max = float(nums[1])

    purity_result = _number(field("Purity result"))
    purity_min = _number(field("Purity minimum"))

    moisture_result = _number(field("Moisture result"))
    moisture_max = _number(field("Moisture maximum"))

    notes = []

    conflict = re.search(
        r"summary reports assay\s*([\d.]+)\s*%.*?"
        r"(?:secondary|laboratory) note reports assay\s*([\d.]+)\s*%",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    if conflict:
        assay_result = None

        notes.append(
            f"Conflicting assay values found: "
            f"{conflict.group(1)}% and {conflict.group(2)}%; "
            "human review required."
        )
    else:
        secondary = re.search(
            r"secondary note reports assay\s*([\d.]+)\s*%",
            text,
            re.IGNORECASE,
        )

        if secondary:
            notes.append(
                f"A secondary assay value was found: "
                f"{secondary.group(1)}%. "
                "Verify against the primary result."
            )

    if "[IMAGE-ONLY PAGE:" in text:
        notes.append(
            "An image-only page could not be read. OCR may be "
            "unavailable or may have produced no text."
        )

    if "fraction" in (assay_range or "").lower() and assay_result is not None:
        notes.append(
            "Assay values are expressed as fractions. Preserve source "
            "units and confirm normalization before evaluation."
        )

    extra = {
        "generic_name": field("Generic name"),
        "brand_name": field("Brand name"),
        "chemical_formula": field("Chemical formula"),
        "molecular_mass": field("Molecular mass"),
        "drug_class": field("Drug class"),
        "mechanism_of_action": field("Mechanism of action"),
        "active_ingredient": field("Active ingredient"),
        "excipients": field("Excipients"),
        "appearance": field("Appearance"),
        "storage_conditions": field("Storage conditions"),
        "manufacturing_site": field("Manufacturing site"),
        "ndc": field("NDC"),
        "gtin": field("GTIN"),
        "gstin": field("GSTIN"),
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

    # DrugReport expects molecular_mass to be a string or None.
    if extra["molecular_mass"] is not None:
        extra["molecular_mass"] = str(extra["molecular_mass"])

    page_for = {}

    page_values = {
        "drug_name": drug_name,
        "manufacturer": manufacturer,
        "product_code": product_code,
        "dosage_form": dosage_form,
        "strength": strength,
        "batch_number": batch_number,
        "manufacturing_date": manufacturing_date,
        "expiry_date": expiry_date,
        "assay_result": assay_result,
        "purity_result": purity_result,
        "moisture_result": moisture_result,
    }

    for key, value in page_values.items():
        if value is not None:
            match = re.search(
                rf"\[PAGE\s+(\d+)\].*?{re.escape(str(value))}",
                text,
                re.IGNORECASE | re.DOTALL,
            )

            page_for[key] = int(match.group(1)) if match else 1

    qc_tests = []

    if (
        assay_result is not None
        or assay_min is not None
        or assay_max is not None
    ):
        qc_tests.append({
            "test_name": "Assay / potency",
            "method": None,
            "specification": assay_range,
            "observed_value": assay_result,
            "unit": "% or source unit",
            "reported_status": None,
        })

    if purity_result is not None or purity_min is not None:
        qc_tests.append({
            "test_name": "Purity",
            "method": None,
            "specification": (
                f"Minimum {purity_min}"
                if purity_min is not None
                else None
            ),
            "observed_value": purity_result,
            "unit": "source unit",
            "reported_status": None,
        })

    if moisture_result is not None or moisture_max is not None:
        qc_tests.append({
            "test_name": "Moisture",
            "method": None,
            "specification": (
                f"Maximum {moisture_max}"
                if moisture_max is not None
                else None
            ),
            "observed_value": moisture_result,
            "unit": "source unit",
            "reported_status": None,
        })

    report = DrugReport(
        report_id=report_id,
        drug_name=drug_name,
        manufacturer=manufacturer,
        product_code=product_code,
        dosage_form=dosage_form,
        strength=strength,
        batch_number=batch_number,
        manufacturing_date=manufacturing_date,
        expiry_date=expiry_date,
        assay_result=assay_result,
        assay_min_limit=assay_min,
        assay_max_limit=assay_max,
        purity_result=purity_result,
        purity_min_limit=purity_min,
        moisture_result=moisture_result,
        moisture_max_limit=moisture_max,
        source_pages=page_for,
        field_evidence={},
        extraction_notes=notes,
        qc_tests=qc_tests,
        **extra,
    )

    return report.to_dict()


# ============================================================
# RESPONSE NORMALIZATION
# ============================================================

def _reconcile_evidence(parsed: dict[str, Any]) -> dict[str, Any]:
    """
    Recover a missing field only from explicitly labelled string
    evidence. Structured evidence is normalized separately.
    """
    evidence = parsed.get("field_evidence")

    if not isinstance(evidence, dict):
        return parsed

    for field_name, evidence_text in evidence.items():
        if field_name not in parsed or parsed[field_name] is not None:
            continue

        if not isinstance(evidence_text, str):
            continue

        label, separator, value = evidence_text.partition(":")

        if not separator:
            continue

        normalized_label = label.strip().lower().replace(" ", "_")

        if normalized_label != field_name.lower():
            continue

        value = value.strip()

        if not value or value.startswith("["):
            continue

        if value.lower() in {
            "unknown",
            "not provided",
            "not specified",
            "not available",
            "n/a",
            "null",
        }:
            continue

        parsed[field_name] = value

    return parsed


def _normalize_llm_response(
    parsed: dict[str, Any],
    report_id: str,
) -> dict[str, Any]:
    """
    Flatten nested LLM responses and normalize fields for DrugReport.
    """

    normalized = dict(parsed)

    # Flatten common nested sections.
    sections = [
        "product_information",
        "identifiers_and_batch_information",
        "clinical_and_descriptive_information",
        "numeric_fields",
    ]

    for section_name in sections:
        section = normalized.get(section_name)

        if isinstance(section, dict):
            for key, value in section.items():
                if (
                    key not in normalized
                    or normalized[key] is None
                    or normalized[key] == ""
                ):
                    normalized[key] = value

    # Recover QC rows from supported nested layouts.
    qc_section = normalized.get("quality_control_results")

    if not normalized.get("qc_tests"):
        if isinstance(qc_section, list):
            normalized["qc_tests"] = qc_section

        elif isinstance(qc_section, dict):
            for key in (
                "qc_tests",
                "tests",
                "results",
                "rows",
                "quality_control_tests",
            ):
                if isinstance(qc_section.get(key), list):
                    normalized["qc_tests"] = qc_section[key]
                    break

    # Normalize common field aliases.
    aliases = {
        "maker": "manufacturer",
        "generic_drug_name": "generic_name",
        "brand": "brand_name",
        "item_code": "product_code",
        "lot_number": "batch_number",
        "lot_batch_number": "batch_number",
        "date_of_manufacture": "manufacturing_date",
        "use_before_date": "expiry_date",
        "qc_results": "qc_tests",
        "quality_control_tests": "qc_tests",
        "source_page_numbers": "source_pages",
    }

    for old_name, new_name in aliases.items():
        old_value = normalized.get(old_name)

        if old_value is not None and (
            new_name not in normalized
            or normalized[new_name] is None
            or normalized[new_name] == ""
        ):
            normalized[new_name] = old_value

    # Evidence schema requires dict[str, str].
    raw_evidence = normalized.get("field_evidence")

    if not isinstance(raw_evidence, dict):
        raw_evidence = {}

    evidence = {}

    for field_name, value in raw_evidence.items():
        if isinstance(value, str):
            evidence[str(field_name)] = value

        elif isinstance(value, dict):
            evidence_value = value.get("value")
            pages = value.get("source_pages", [])

            if evidence_value is not None:
                excerpt = f"{field_name}: {evidence_value}"

                if pages:
                    if not isinstance(pages, list):
                        pages = [pages]

                    excerpt += (
                        " (source pages: "
                        + ", ".join(map(str, pages))
                        + ")"
                    )

                evidence[str(field_name)] = excerpt

            else:
                evidence[str(field_name)] = json.dumps(
                    value,
                    ensure_ascii=False,
                )

        elif value is not None:
            evidence[str(field_name)] = str(value)

    normalized["field_evidence"] = evidence

    # Notes schema requires list[str].
    notes = normalized.get("extraction_notes")

    if notes is None:
        normalized["extraction_notes"] = []

    elif isinstance(notes, str):
        normalized["extraction_notes"] = [notes]

    elif isinstance(notes, list):
        normalized["extraction_notes"] = [
            str(note) for note in notes if note is not None
        ]

    else:
        normalized["extraction_notes"] = [str(notes)]

    # Page schema requires dict[str, int].
    raw_pages = normalized.get("source_pages")

    if not isinstance(raw_pages, dict):
        raw_pages = {}

    pages_normalized = {}

    for field_name, page_value in raw_pages.items():
        if isinstance(page_value, list):
            page_value = page_value[0] if page_value else None

        try:
            if page_value is not None:
                pages_normalized[str(field_name)] = int(page_value)

        except (TypeError, ValueError):
            pass

    # Also extract page numbers from structured evidence.
    for field_name, value in raw_evidence.items():
        if not isinstance(value, dict):
            continue

        evidence_pages = value.get("source_pages")

        if isinstance(evidence_pages, int):
            evidence_pages = [evidence_pages]

        if (
            isinstance(evidence_pages, list)
            and evidence_pages
            and field_name not in pages_normalized
        ):
            try:
                pages_normalized[str(field_name)] = int(
                    evidence_pages[0]
                )

            except (TypeError, ValueError):
                pass

    normalized["source_pages"] = pages_normalized

    # Normalize QC row names.
    qc_rows = normalized.get("qc_tests")

    if qc_rows is None:
        qc_rows = []

    if isinstance(qc_rows, dict):
        for key in (
            "qc_tests",
            "tests",
            "results",
            "rows",
            "quality_control_tests",
        ):
            if isinstance(qc_rows.get(key), list):
                qc_rows = qc_rows[key]
                break

    if not isinstance(qc_rows, list):
        qc_rows = []

    qc_aliases = {
        "test": "test_name",
        "name": "test_name",
        "result": "observed_value",
        "value": "observed_value",
        "acceptance_criteria": "specification",
        "acceptance_range": "specification",
        "status": "reported_status",
        "page_number": "page",
        "source_page": "page",
    }

    normalized_rows = []

    for item in qc_rows:
        if not isinstance(item, dict):
            continue

        row = dict(item)

        for old_name, new_name in qc_aliases.items():
            if old_name in row and (
                new_name not in row
                or row[new_name] is None
                or row[new_name] == ""
            ):
                row[new_name] = row[old_name]

        if row.get("page") is not None:
            try:
                row["page"] = int(row["page"])

            except (TypeError, ValueError):
                row["page"] = None

        normalized_rows.append(row)

    normalized["qc_tests"] = normalized_rows

    # Numeric summary fields: convert only plain numeric strings.
    for name in (
        "assay_result",
        "assay_min_limit",
        "assay_max_limit",
        "purity_result",
        "purity_min_limit",
        "moisture_result",
        "moisture_max_limit",
    ):
        value = normalized.get(name)

        if isinstance(value, str):
            candidate = value.strip()

            if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", candidate):
                normalized[name] = float(candidate)

    # IMPORTANT FIX:
    # DrugReport expects molecular_mass to be a string or None,
    # but the LLM may return a JSON number such as 151.163.
    molecular_mass = normalized.get("molecular_mass")

    if molecular_mass is not None:
        normalized["molecular_mass"] = str(molecular_mass)

    normalized["report_id"] = report_id

    return _reconcile_evidence(normalized)


# ============================================================
# PROMPT
# ============================================================

def _build_prompt(text: str, report_id: str) -> str:
    """Request a flat JSON object compatible with DrugReport."""

    template = {
        "report_id": report_id,
        "drug_name": None,
        "generic_name": None,
        "brand_name": None,
        "chemical_formula": None,
        "molecular_mass": None,
        "drug_class": None,
        "mechanism_of_action": None,
        "active_ingredient": None,
        "excipients": None,
        "dosage_form": None,
        "strength": None,
        "appearance": None,
        "storage_conditions": None,
        "manufacturer": None,
        "manufacturing_site": None,
        "product_code": None,
        "ndc": None,
        "gtin": None,
        "gstin": None,
        "report_number": None,
        "laboratory_name": None,
        "batch_number": None,
        "manufacturing_date": None,
        "expiry_date": None,
        "testing_date": None,
        "indications": None,
        "dosage_information": None,
        "contraindications": None,
        "warnings": None,
        "adverse_effects": None,
        "drug_interactions": None,
        "assay_result": None,
        "assay_min_limit": None,
        "assay_max_limit": None,
        "purity_result": None,
        "purity_min_limit": None,
        "moisture_result": None,
        "moisture_max_limit": None,
        "qc_tests": [],
        "source_pages": {},
        "field_evidence": {},
        "extraction_notes": [],
    }

    return f"""
You are a pharmaceutical document extraction system.
Return ONLY one valid JSON object matching this exact flat structure.
Do not nest fields inside sections such as product_information or
identifiers_and_batch_information.

JSON TEMPLATE:
{json.dumps(template, indent=2)}

RULES
1. Extract only information supported by the supplied document.
2. Never invent missing values. Use null for missing scalar fields.
3. Preserve source meaning, units, ranges, symbols, and qualifiers.
4. Do not confuse example identifiers with actual identifiers.
5. Keep clinical information separate from batch QC results.
6. A reported PASS or FAIL is not independently verified.
7. Never silently resolve contradictory values. Use null when no
   canonical value can safely be selected and explain the conflict.
8. Descriptive fields must be strings or null.
9. Numeric summary fields must be JSON numbers or null.
10. qc_tests must be a list of objects, with one row per test. Preserve
    test_name, method, specification, observed_value, unit,
    reported_status, and page when available.
11. Do not omit a readable QC row just because one field is missing.
12. Do not invent methods, specifications, values, units, or statuses.
13. Do not silently convert units or assume every measurement is a percent.
14. source_pages maps field names to integer page numbers.
15. field_evidence maps field names to short verbatim string excerpts.
16. extraction_notes is always a list of strings.
17. Use YYYY-MM-DD only for unambiguous dates; otherwise preserve source
    text and explain ambiguity.
18. Do not add clinical information from general knowledge or provide advice.
19. Mention unreadable, image-only, or uncertain OCR content in notes.
20. report_id must exactly equal {json.dumps(report_id)}.
21. Do not equate 0.985 with 98.5%, or 98.5% with 98.5 mg.

DOCUMENT TEXT:
{text[:18000]}
""".strip()


# ============================================================
# MAIN EXTRACTION
# ============================================================

def extract_fields(
    text: str,
    report_id: str,
) -> tuple[dict[str, Any], str]:
    """
    Extract a DrugReport using the configured OpenAI-compatible endpoint.

    Falls back to the conservative local parser if the LLM call,
    response parsing, or schema validation fails.
    """

    load_dotenv(PROJECT_ROOT / ".env", override=False)

    api_key = os.getenv("FRESCO_API_KEY", "").strip()
    base_url = os.getenv("FRESCO_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("FRESCO_MODEL", "").strip()

    verify_ssl = (
        os.getenv("FRESCO_VERIFY_SSL", "true").strip().lower()
        not in {"0", "false", "no"}
    )

    def fallback(note: str, mode: str):
        result = _fallback_extract(text, report_id)
        _append_note(result, note)
        return result, mode

    if (
        not api_key
        or api_key == "replace_with_your_api_key"
        or not base_url
        or not model
    ):
        return fallback(
            "FRESCO_API_KEY, FRESCO_BASE_URL, or FRESCO_MODEL is missing. "
            "The local demo parser was used.",
            "local_demo_parser",
        )

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Extract pharmaceutical report data faithfully. "
                            "Return one valid JSON object matching the flat schema."
                        ),
                    },
                    {
                        "role": "user",
                        "content": _build_prompt(text, report_id),
                    },
                ],
            },
            timeout=90,
            verify=verify_ssl,
        )

        response.raise_for_status()

        response_data = response.json()
        choices = response_data.get("choices", [])

        if not choices:
            raise ValueError("LLM response contains no choices.")

        content = choices[0].get("message", {}).get("content")

        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM returned empty or invalid message content.")

        content = content.strip()

        # Handle JSON wrapped in Markdown code fences.
        if content.startswith("```"):
            content = re.sub(
                r"\A```(?:json)?\s*|\s*```\s*\Z",
                "",
                content,
                flags=re.IGNORECASE,
            ).strip()

        parsed = json.loads(content)

        if not isinstance(parsed, dict):
            raise ValueError("LLM response must be a JSON object.")

        parsed = _normalize_llm_response(parsed, report_id)

        try:
            report = DrugReport.model_validate(parsed).to_dict()

        except Exception as exc:
            print("SCHEMA VALIDATION ERROR:")
            print(exc)
            print("NORMALIZED FIELDS:", list(parsed.keys()))
            print(
                "NORMALIZED QC ROW COUNT:",
                len(parsed.get("qc_tests", [])),
            )
            raise

        print("LLM extraction succeeded.")
        print(f"Extraction model: {model}")
        print(f"Report ID: {report_id}")
        print(f"Drug name extracted: {report.get('drug_name')}")
        print(f"Manufacturer extracted: {report.get('manufacturer')}")
        print(f"Batch number extracted: {report.get('batch_number')}")
        print(
            f"QC test rows extracted: {len(report.get('qc_tests', []))}"
        )

        return report, f"llm:{model}"

    except requests.exceptions.SSLError as exc:
        print(f"Fresco SSL error: {exc}")

        return fallback(
            "LLM extraction failed because of an SSL certificate error. "
            "The local parser was used instead.",
            "local_demo_parser_after_ssl_error",
        )

    except requests.exceptions.HTTPError as exc:
        status = (
            exc.response.status_code
            if exc.response is not None
            else "unknown"
        )

        print(f"Fresco HTTP error: status={status}, error={exc}")

        return fallback(
            f"LLM extraction failed with HTTP status {status}. "
            "The local parser was used instead.",
            "local_demo_parser_after_http_error",
        )

    except requests.exceptions.ConnectionError as exc:
        print(f"Fresco connection error: {exc}")

        return fallback(
            "LLM extraction failed because the endpoint could not be reached. "
            "The local parser was used instead.",
            "local_demo_parser_after_connection_error",
        )

    except requests.exceptions.Timeout as exc:
        print(f"Fresco request timed out: {exc}")

        return fallback(
            "LLM extraction timed out. The local parser was used instead.",
            "local_demo_parser_after_timeout",
        )

    except Exception as exc:
        print(f"LLM extraction failed: {type(exc).__name__}: {exc}")

        return fallback(
            f"LLM extraction failed ({type(exc).__name__}). "
            "The local parser was used instead.",
            "local_demo_parser_after_llm_error",
        )

