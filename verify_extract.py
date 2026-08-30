"""Smoke-test extract/copy/save against a copy-restricted PDF."""

from __future__ import annotations

from pathlib import Path

import fitz

from pdf_io import extract_all_pages, extract_clip, open_document, save_text_file, save_text_pdf

ROOT = Path(__file__).resolve().parent
PHRASE = "Sunday gravy starts with browned pork and a long simmer."


def main() -> None:
    locked = ROOT / "_sample_locked.pdf"
    out_txt = ROOT / "_sample_out.txt"
    out_pdf = ROOT / "_sample_editable.pdf"

    src = fitz.open()
    page = src.new_page(width=612, height=792)
    page.insert_text((72, 120), PHRASE, fontsize=14, fontname="helv")
    page.insert_text((72, 160), "Second paragraph lives here.", fontsize=14, fontname="helv")
    perm = fitz.PDF_PERM_PRINT
    src.save(
        locked,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner-secret",
        user_pw="",
        permissions=perm,
    )
    src.close()

    doc = open_document(locked)
    pages = extract_all_pages(doc)
    assert PHRASE in pages[0], repr(pages[0])
    clip = extract_clip(doc[0], fitz.Rect(60, 100, 500, 140))
    assert "Sunday gravy" in clip, repr(clip)

    save_text_file(out_txt, pages)
    assert PHRASE in out_txt.read_text(encoding="utf-8")

    save_text_pdf(out_pdf, ["Edited: " + PHRASE])
    check = fitz.open(out_pdf)
    exported = check[0].get_text("text")
    check.close()
    doc.close()
    assert "Edited:" in exported and "Sunday gravy" in exported, repr(exported)

    locked.unlink(missing_ok=True)
    out_txt.unlink(missing_ok=True)
    out_pdf.unlink(missing_ok=True)
    print("ok: extract, clip, save txt, save pdf")


if __name__ == "__main__":
    main()
