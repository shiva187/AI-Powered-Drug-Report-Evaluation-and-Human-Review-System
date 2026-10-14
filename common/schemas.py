from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class DrugReport(BaseModel):
    """Structured information extracted from a pharmaceutical monograph / QC report."""
    model_config = ConfigDict(extra="ignore")

    report_id: str = ""
    # Product identity and descriptive profile
    drug_name: Optional[str] = None
    generic_name: Optional[str] = None
    brand_name: Optional[str] = None
    chemical_formula: Optional[str] = None
    molecular_mass: Optional[str] = None
    drug_class: Optional[str] = None
    mechanism_of_action: Optional[str] = None
    active_ingredient: Optional[str] = None
    excipients: Optional[str] = None
    dosage_form: Optional[str] = None
    strength: Optional[str] = None
    appearance: Optional[str] = None
    storage_conditions: Optional[str] = None
    # Manufacturer, report and batch identity
    manufacturer: Optional[str] = None
    manufacturing_site: Optional[str] = None
    product_code: Optional[str] = None
    ndc: Optional[str] = None
    gtin: Optional[str] = None
    gstin: Optional[str] = None
    report_number: Optional[str] = None
    laboratory_name: Optional[str] = None
    batch_number: Optional[str] = None
    manufacturing_date: Optional[str] = None
    expiry_date: Optional[str] = None
    testing_date: Optional[str] = None
    # Clinical/descriptive content copied only when present in source
    indications: Optional[str] = None
    dosage_information: Optional[str] = None
    contraindications: Optional[str] = None
    warnings: Optional[str] = None
    adverse_effects: Optional[str] = None
    drug_interactions: Optional[str] = None
    # Common QC fields retained for deterministic demo evaluation
    assay_result: Optional[float] = None
    assay_min_limit: Optional[float] = None
    assay_max_limit: Optional[float] = None
    purity_result: Optional[float] = None
    purity_min_limit: Optional[float] = None
    moisture_result: Optional[float] = None
    moisture_max_limit: Optional[float] = None
    # All table rows, units, methods and statuses, without collapsing tests into one field
    qc_tests: list[dict[str, Any]] = Field(default_factory=list)
    source_pages: dict[str, int] = Field(default_factory=dict)
    field_evidence: dict[str, str] = Field(default_factory=dict)
    extraction_notes: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

REQUIRED_FIELDS = [
    "drug_name", "manufacturer", "product_code", "dosage_form", "strength",
    "batch_number", "manufacturing_date", "expiry_date", "assay_result",
    "assay_min_limit", "assay_max_limit", "purity_result", "purity_min_limit",
    "moisture_result", "moisture_max_limit"
]

FIELD_LABELS = {
    "drug_name": "Drug name", "manufacturer": "Manufacturer", "product_code": "Product code",
    "dosage_form": "Dosage form", "strength": "Strength", "batch_number": "Batch number",
    "manufacturing_date": "Manufacturing date", "expiry_date": "Expiry date",
    "assay_result": "Assay result (%)", "assay_min_limit": "Assay minimum (%)",
    "assay_max_limit": "Assay maximum (%)", "purity_result": "Purity result (%)",
    "purity_min_limit": "Purity minimum (%)", "moisture_result": "Moisture result (%)",
    "moisture_max_limit": "Moisture maximum (%)",
}

