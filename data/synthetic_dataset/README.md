# Synthetic PDF benchmark

This folder contains ten fictional reports with varied layouts and a ground-truth JSON file. The reports cover prose, tables, alternate terminology, multiple pages, missing fields, conflicting results, unit normalization, out-of-range values, invalid dates, and an image-only scanned page.

**Safety / scope:** these are software test fixtures only. They are not real medicines, certificates, official specifications, or regulatory acceptance criteria. The image-only PDF requires OCR support; a text-only extractor should mark it as needing OCR rather than hallucinating values. The conflict case must be sent for human review.

`ground_truth.json` contains canonical values and expected issues for each file. `null` means a value is intentionally absent or cannot safely be resolved.
