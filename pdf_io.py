"""PDF open, text extract, OCR, and save helpers."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import fitz
from PIL import Image


PAGE_W = 612.0
PAGE_H = 792.0
MARGIN = 54.0


def open_document(path: str | Path, password: str = "") -> fitz.Document:
    doc = fitz.open(str(path))
    if doc.is_encrypted:
        if not password:
            doc.close()
            raise PermissionError("PASSWORD_REQUIRED")
        if not doc.authenticate(password):
            doc.close()
            raise PermissionError("BAD_PASSWORD")
    return doc


def extract_page_text(page: fitz.Page) -> str:
    blocks = page.get_text("blocks") or []
    parts: list[str] = []
    for block in sorted(blocks, key=lambda b: (round(b[1], 1), b[0])):
        if len(block) > 6 and block[6] != 0:
            continue
        chunk = (block[4] or "").replace("\u00ad", "").rstrip()
        if chunk.strip():
            parts.append(chunk)
    text = "\n\n".join(parts).strip()
    if not text:
        text = (page.get_text("text") or "").replace("\u00ad", "").strip()
    return text


def extract_all_pages(doc: fitz.Document) -> list[str]:
    return [extract_page_text(doc[i]) for i in range(doc.page_count)]


def extract_clip(page: fitz.Page, rect: fitz.Rect) -> str:
    clip = fitz.Rect(rect)
    if clip.is_empty or clip.is_infinite:
        return ""
    clip.normalize()
    text = (page.get_text("text", clip=clip) or "").replace("\u00ad", "").strip()
    if text:
        return text
    blocks = page.get_text("blocks", clip=clip) or []
    parts: list[str] = []
    for block in sorted(blocks, key=lambda b: (round(b[1], 1), b[0])):
        if len(block) > 6 and block[6] != 0:
            continue
        chunk = (block[4] or "").replace("\u00ad", "").rstrip()
        if chunk.strip():
            parts.append(chunk)
    return "\n\n".join(parts).strip()


def page_has_images(page: fitz.Page) -> bool:
    return bool(page.get_images())


def page_to_pil(page: fitz.Page, clip: fitz.Rect | None = None, dpi: int = 200) -> Image.Image:
    rect = fitz.Rect(clip) if clip is not None else page.rect
    rect.normalize()
    zoom = dpi / 72.0
    longest = max(rect.width, rect.height) * zoom
    if longest > 2600:
        zoom *= 2600 / longest
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
    mode = "RGB" if pix.n < 4 else "RGBA"
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    if mode == "RGBA":
        image = image.convert("RGB")
    return image


def _ocr_windows(image: Image.Image) -> str:
    import winocr

    result = winocr.recognize_pil_sync(image)
    if isinstance(result, dict):
        lines = result.get("lines") or []
        from_lines = "\n".join(
            (line.get("text") or "").strip()
            for line in lines
            if isinstance(line, dict) and (line.get("text") or "").strip()
        )
        blob = (result.get("text") or "").strip()
        return from_lines or blob
    return (getattr(result, "text", None) or str(result) or "").strip()


def _ocr_tesseract(page: fitz.Page, clip: fitz.Rect | None, dpi: int) -> str:
    kwargs: dict = {"dpi": dpi, "full": True, "language": "eng"}
    if clip is not None:
        kwargs["clip"] = clip
    tp = page.get_textpage_ocr(**kwargs)
    return (page.get_text("text", textpage=tp) or "").strip()


def ocr_page_text(page: fitz.Page, clip: fitz.Rect | None = None, dpi: int = 200) -> str:
    errors: list[str] = []
    image = page_to_pil(page, clip=clip, dpi=dpi)

    def try_windows() -> str:
        return _ocr_windows(image)

    def try_tesseract() -> str:
        return _ocr_tesseract(page, clip, dpi)

    steps = (try_windows, try_tesseract) if sys.platform == "win32" else (try_tesseract, try_windows)
    labels = ("Windows OCR", "Tesseract") if sys.platform == "win32" else ("Tesseract", "Windows OCR")

    for step, label in zip(steps, labels):
        try:
            text = step()
            if text:
                return text
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    if errors:
        raise RuntimeError(" · ".join(errors))
    return ""


def render_page(page: fitz.Page, zoom: float) -> fitz.Pixmap:
    zoom = max(0.25, min(zoom, 4.0))
    mat = fitz.Matrix(zoom, zoom)
    return page.get_pixmap(matrix=mat, alpha=False)


def save_text_file(path: str | Path, pages: list[str]) -> None:
    chunks = []
    for i, text in enumerate(pages, start=1):
        header = f"----- page {i} -----"
        chunks.append(f"{header}\n{text.rstrip()}\n")
    Path(path).write_text("\n".join(chunks).rstrip() + "\n", encoding="utf-8")


def _wrap_page(text: str, width: int = 92) -> list[str]:
    lines: list[str] = []
    for raw in (text or "").splitlines():
        if not raw.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(raw, width=width) or [""])
    return lines


def _lines_to_pages(lines: list[str], lines_per_page: int = 52) -> list[str]:
    if not lines:
        return [""]
    out: list[str] = []
    for i in range(0, len(lines), lines_per_page):
        out.append("\n".join(lines[i : i + lines_per_page]))
    return out


def save_text_pdf(path: str | Path, pages: list[str]) -> None:
    """Write edited text as a new, fully copyable PDF."""
    doc = fitz.open()
    fontname = "helv"
    fontsize = 11.0
    rect = fitz.Rect(MARGIN, MARGIN, PAGE_W - MARGIN, PAGE_H - MARGIN)

    written = False
    for page_text in pages or [""]:
        for chunk in _lines_to_pages(_wrap_page(page_text)):
            page = doc.new_page(width=PAGE_W, height=PAGE_H)
            page.insert_textbox(
                rect,
                chunk,
                fontsize=fontsize,
                fontname=fontname,
                align=fitz.TEXT_ALIGN_LEFT,
            )
            written = True

    if not written:
        doc.new_page(width=PAGE_W, height=PAGE_H)

    doc.save(str(path), deflate=True, garbage=4)
    doc.close()
