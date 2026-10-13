from pathlib import Path
import fitz


def extract_pdf_text(file_path: str | Path) -> tuple[str, dict[int, str]]:
    """Extract selectable PDF text; if a page is image-only, try optional Tesseract OCR.

    OCR requires the `pytesseract` Python package and the Tesseract binary installed on the OS.
    If unavailable, the page is retained as empty text and a clear note is included.
    """
    document = fitz.open(str(file_path))
    pages: dict[int, str] = {}
    chunks: list[str] = []
    for i, page in enumerate(document, start=1):
        page_text = page.get_text("text").strip()
        if len(page_text) < 30:
            try:
                import pytesseract
                from PIL import Image
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_text = pytesseract.image_to_string(image).strip()
                if ocr_text:
                    page_text = ocr_text
                else:
                    page_text = "[OCR attempted but no text was detected on this page.]"
            except Exception as exc:
                page_text = f"[IMAGE-ONLY PAGE: OCR unavailable ({type(exc).__name__}).]"
        pages[i] = page_text
        chunks.append(f"[PAGE {i}]\n{page_text}")
    document.close()
    return "\n\n".join(chunks), pages
