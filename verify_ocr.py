"""OCR a scan-style PDF with no text layer (no Tesseract required)."""

from __future__ import annotations

from pathlib import Path

import fitz

from pdf_io import extract_page_text, ocr_page_text

ROOT = Path(__file__).resolve().parent
PHRASE = "Sunday gravy starts with browned pork"


def _image_only_pdf(path: Path) -> None:
    src = fitz.open()
    page = src.new_page(width=612, height=792)
    page.insert_text((72, 180), PHRASE, fontsize=22, fontname="helv")
    pix = page.get_pixmap(dpi=150)
    src.close()

    out = fitz.open()
    dst = out.new_page(width=612, height=792)
    dst.insert_image(dst.rect, pixmap=pix)
    out.save(path)
    out.close()


def main() -> None:
    path = ROOT / "_sample_scan.pdf"
    _image_only_pdf(path)
    doc = fitz.open(path)
    page = doc[0]
    hidden = extract_page_text(page)
    assert PHRASE not in hidden, f"expected no text layer, got {hidden!r}"

    text = ocr_page_text(page)
    clip = ocr_page_text(page, clip=fitz.Rect(40, 120, 580, 260))
    doc.close()
    path.unlink(missing_ok=True)
    assert "Sunday" in text and "gravy" in text, repr(text)
    assert "Sunday" in clip or "gravy" in clip, repr(clip)
    print("ok: windows ocr on image-only pdf")


if __name__ == "__main__":
    main()
