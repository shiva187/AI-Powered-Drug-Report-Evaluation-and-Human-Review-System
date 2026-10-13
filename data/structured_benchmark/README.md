# Structured pharmaceutical report benchmark (v2.0)

These ten PDFs preserve the uploaded example's four-section structure: (1) Chemical & Core Profile, (2) Administrative & Supply Chain Identifiers, (3) Clinical Guidelines & Safety Protocol, and (4) Laboratory QC Grid. A notes section is included for contradictions and synthetic test conditions.

Files vary by narrative/table layout, alternate terminology, multipage content, missing expiry, conflicting assay, alternate units, out-of-range assay, invalid dates, and image-only scan. `ground_truth.json` stores expected extracted values and known issues.

**All data are fictional.** The acceptance limits are illustrative test values, not approved product specifications or regulatory standards. Clinical descriptions are test content only. The benchmark is not suitable for medical decisions or real batch release.

For `10_scanned_image_only.pdf`, OCR requires the OS Tesseract binary and Python packages `pytesseract` and `Pillow`; without them the application will identify the page as image-only and flag that OCR is unavailable.
