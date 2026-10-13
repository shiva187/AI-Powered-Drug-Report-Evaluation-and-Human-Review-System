from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

SAMPLES = [
    {
        "filename": "01_complete_pass.pdf",
        "title": "Synthetic CoA - Complete Passing Report",
        "fields": {
            "Drug name": "Demo Drug A", "Manufacturer": "Example Pharma Ltd.",
            "Product code": "DDA-100", "Dosage form": "Tablet", "Strength": "100 mg",
            "Batch number": "BATCH-2026-001", "Manufacturing date": "2026-01-10",
            "Expiry date": "2028-01-10", "Assay result": "99.2 %",
            "Assay acceptance range": "98.0 - 102.0 %", "Purity result": "99.5 %",
            "Purity minimum": "98.0 %", "Moisture result": "0.8 %",
            "Moisture maximum": "1.5 %", "Report note": "All listed tests conform to the synthetic specification."
        }
    },
    {
        "filename": "02_assay_fail.pdf",
        "title": "Synthetic CoA - Assay Outside Range",
        "fields": {
            "Drug name": "Demo Drug B", "Manufacturer": "Example Pharma Ltd.",
            "Product code": "DDB-200", "Dosage form": "Capsule", "Strength": "200 mg",
            "Batch number": "BATCH-2026-002", "Manufacturing date": "2026-02-01",
            "Expiry date": "2028-02-01", "Assay result": "96.7 %",
            "Assay acceptance range": "98.0 - 102.0 %", "Purity result": "99.1 %",
            "Purity minimum": "98.0 %", "Moisture result": "0.9 %",
            "Moisture maximum": "1.5 %", "Report note": "Assay result is intentionally outside the synthetic acceptance range."
        }
    },
    {
        "filename": "03_missing_expiry.pdf",
        "title": "Synthetic CoA - Missing Expiry Date",
        "fields": {
            "Drug name": "Demo Drug C", "Manufacturer": "Sample Biologics Inc.",
            "Product code": "DDC-300", "Dosage form": "Powder", "Strength": "50 mg",
            "Batch number": "BATCH-2026-003", "Manufacturing date": "2026-03-15",
            "Expiry date": "", "Assay result": "99.0 %",
            "Assay acceptance range": "98.0 - 102.0 %", "Purity result": "98.9 %",
            "Purity minimum": "98.0 %", "Moisture result": "1.0 %",
            "Moisture maximum": "1.5 %", "Report note": "Expiry date intentionally omitted from this synthetic report."
        }
    },
    {
        "filename": "04_expired_batch.pdf",
        "title": "Synthetic CoA - Expired Batch",
        "fields": {
            "Drug name": "Demo Drug D", "Manufacturer": "Sample Biologics Inc.",
            "Product code": "DDD-400", "Dosage form": "Tablet", "Strength": "400 mg",
            "Batch number": "BATCH-2023-004", "Manufacturing date": "2023-01-10",
            "Expiry date": "2025-01-10", "Assay result": "99.4 %",
            "Assay acceptance range": "98.0 - 102.0 %", "Purity result": "99.0 %",
            "Purity minimum": "98.0 %", "Moisture result": "0.7 %",
            "Moisture maximum": "1.5 %", "Report note": "Expiry date is intentionally in the past."
        }
    },
    {
        "filename": "05_conflicting_assay.pdf",
        "title": "Synthetic CoA - Conflicting Assay Values",
        "fields": {
            "Drug name": "Demo Drug E", "Manufacturer": "Demo Manufacturing Co.",
            "Product code": "DDE-500", "Dosage form": "Tablet", "Strength": "500 mg",
            "Batch number": "BATCH-2026-005", "Manufacturing date": "2026-04-05",
            "Expiry date": "2028-04-05", "Assay result": "99.3 %",
            "Assay acceptance range": "98.0 - 102.0 %", "Purity result": "99.2 %",
            "Purity minimum": "98.0 %", "Moisture result": "0.8 %",
            "Moisture maximum": "1.5 %", "Report note": "Summary section reports assay 99.3%, while a secondary note reports assay 96.3%."
        }
    },
]

def generate_sample_pdfs(output_dir: str | Path) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for idx, sample in enumerate(SAMPLES, start=1):
        path = output_dir / sample["filename"]
        if path.exists():
            created.append(path)
            continue
        c = canvas.Canvas(str(path), pagesize=letter)
        width, height = letter
        c.setTitle(sample["title"])
        y = height - 60
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, y, sample["title"])
        y -= 28
        c.setFont("Helvetica", 9)
        c.drawString(50, y, "SYNTHETIC TRAINING DATA - NOT A REAL MEDICINAL PRODUCT OR CoA")
        y -= 30
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "Product and batch information")
        y -= 18
        for label in ["Drug name", "Manufacturer", "Product code", "Dosage form", "Strength",
                      "Batch number", "Manufacturing date", "Expiry date"]:
            value = sample["fields"].get(label, "")
            c.setFont("Helvetica-Bold", 9)
            c.drawString(55, y, f"{label}:")
            c.setFont("Helvetica", 9)
            c.drawString(190, y, value if value else "[INTENTIONALLY MISSING]")
            y -= 16
        y -= 8
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "Laboratory quality tests (illustrative limits only)")
        y -= 20
        rows = [
            ("Assay", sample["fields"]["Assay result"], sample["fields"]["Assay acceptance range"]),
            ("Purity", sample["fields"]["Purity result"], f"Minimum {sample['fields']['Purity minimum']}"),
            ("Moisture", sample["fields"]["Moisture result"], f"Maximum {sample['fields']['Moisture maximum']}"),
        ]
        c.setFont("Helvetica-Bold", 9)
        c.drawString(55, y, "Test")
        c.drawString(160, y, "Observed result")
        c.drawString(300, y, "Acceptance criterion")
        y -= 15
        c.setFont("Helvetica", 9)
        for test, result, limit in rows:
            c.drawString(55, y, test)
            c.drawString(160, y, result)
            c.drawString(300, y, limit)
            y -= 17
        y -= 12
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, "Notes")
        y -= 16
        c.setFont("Helvetica", 9)
        note = sample["fields"]["Report note"]
        # Wrap note into lines
        words, line = note.split(), ""
        for word in words:
            if len(line + " " + word) > 88:
                c.drawString(55, y, line)
                y -= 13
                line = word
            else:
                line = (line + " " + word).strip()
        if line:
            c.drawString(55, y, line)
        y -= 28
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(50, y, "This document is fabricated for software demonstration. It must not be used for medical or regulatory decisions.")
        c.showPage()
        c.save()
        created.append(path)
    return created

if __name__ == "__main__":
    for p in generate_sample_pdfs(Path(__file__).resolve().parents[1] / "data" / "sample_reports"):
        print(p)
