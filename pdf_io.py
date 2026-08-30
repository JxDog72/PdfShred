"""PDF open, text extract, OCR, and save helpers."""

from __future__ import annotations

import html
import sys
import textwrap
from difflib import SequenceMatcher
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


def _split_blocks(text: str) -> list[str]:
    text = (text or "").replace("\u00ad", "").strip()
    if not text:
        return []
    return [part.rstrip() for part in text.split("\n\n")]


def _text_blocks(page: fitz.Page) -> list[dict]:
    blocks = page.get_text("blocks") or []
    out: list[dict] = []
    for block in sorted(blocks, key=lambda b: (round(b[1], 1), b[0])):
        if len(block) > 6 and block[6] != 0:
            continue
        chunk = (block[4] or "").replace("\u00ad", "").rstrip()
        if not chunk.strip():
            continue
        out.append({"rect": fitz.Rect(block[:4]), "text": chunk})
    return out


def _rgb(color: int) -> tuple[float, float, float]:
    return (
        ((color >> 16) & 255) / 255.0,
        ((color >> 8) & 255) / 255.0,
        (color & 255) / 255.0,
    )


def _block_style(page: fitz.Page, rect: fitz.Rect) -> tuple[float, tuple[float, float, float], str]:
    info = page.get_text("dict", clip=rect) or {}
    sizes: list[float] = []
    colors: list[int] = []
    flags = 0
    for block in info.get("blocks") or []:
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                if not (span.get("text") or "").strip():
                    continue
                sizes.append(float(span.get("size") or 11.0))
                colors.append(int(span.get("color") or 0))
                flags = int(span.get("flags") or 0)
    fontsize = sorted(sizes)[len(sizes) // 2] if sizes else 11.0
    color = _rgb(colors[0]) if colors else (0.0, 0.0, 0.0)
    italic = bool(flags & 2)
    bold = bool(flags & 16)
    if bold and italic:
        fontname = "hebi"
    elif bold:
        fontname = "hebo"
    elif italic:
        fontname = "heit"
    else:
        fontname = "helv"
    return fontsize, color, fontname


def _redact(page: fitz.Page, rect: fitz.Rect) -> None:
    box = fitz.Rect(rect)
    box.normalize()
    box += (-0.6, -0.6, 0.6, 0.6)
    page.add_redact_annot(box, fill=None)


def _insert_in_rect(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    fontsize: float,
    color: tuple[float, float, float],
    fontname: str,
    *,
    invisible: bool = False,
) -> None:
    box = fitz.Rect(rect)
    box.normalize()
    if box.width < 8 or box.height < 8:
        return
    payload = text or ""
    if invisible:
        try:
            page.insert_textbox(
                box,
                payload,
                fontsize=max(6.0, fontsize),
                fontname=fontname,
                color=color,
                render_mode=3,
                overlay=True,
            )
            return
        except TypeError:
            pass
    r, g, b = (int(c * 255) for c in color)
    css = (
        f"body{{font-family:sans-serif;font-size:{max(6.0, fontsize):.1f}pt;"
        f"color:rgb({r},{g},{b});margin:0;line-height:1.15;}}"
    )
    markup = html.escape(payload).replace("\n", "<br>\n")
    try:
        page.insert_htmlbox(box, f"<div>{markup}</div>", css=css)
        return
    except Exception:
        pass
    size = max(6.0, fontsize)
    while size >= 6.0:
        leftover = page.insert_textbox(
            box,
            payload,
            fontsize=size,
            fontname=fontname,
            color=color,
            align=fitz.TEXT_ALIGN_LEFT,
        )
        if leftover >= 0:
            return
        size -= 0.5


def _apply_redactions(page: fitz.Page) -> None:
    kwargs = {}
    images = getattr(fitz, "PDF_REDACT_IMAGE_NONE", None)
    graphics = getattr(fitz, "PDF_REDACT_LINE_ART_NONE", None)
    if images is not None:
        kwargs["images"] = images
    if graphics is not None:
        kwargs["graphics"] = graphics
    page.apply_redactions(**kwargs)


def _apply_page_edits(page: fitz.Page, edited: str) -> None:
    original = extract_page_text(page)
    if (edited or "").strip() == (original or "").strip():
        return

    blocks = _text_blocks(page)
    new_parts = _split_blocks(edited)

    if not blocks:
        if new_parts:
            inner = fitz.Rect(page.rect)
            inner += (36, 36, -36, -36)
            _insert_in_rect(
                page,
                inner,
                "\n\n".join(new_parts),
                11.0,
                (0.0, 0.0, 0.0),
                "helv",
                invisible=True,
            )
        return

    if not new_parts:
        for block in blocks:
            _redact(page, block["rect"])
        _apply_redactions(page)
        return

    matcher = SequenceMatcher(
        a=[b["text"] for b in blocks],
        b=new_parts,
        autojunk=False,
    )
    pending: list[tuple[fitz.Rect, str, float, tuple[float, float, float], str]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old = blocks[i1:i2]
        new = new_parts[j1:j2]
        if tag in ("replace", "delete"):
            for block in old:
                _redact(page, block["rect"])
        if tag in ("replace", "insert") and new:
            if old and len(old) == len(new):
                for block, text in zip(old, new):
                    if text == block["text"]:
                        continue
                    fontsize, color, fontname = _block_style(page, block["rect"])
                    pending.append((block["rect"], text, fontsize, color, fontname))
            else:
                if old:
                    box = fitz.Rect(old[0]["rect"])
                    for block in old[1:]:
                        box |= block["rect"]
                    fontsize, color, fontname = _block_style(page, old[0]["rect"])
                else:
                    prev = blocks[i1 - 1]["rect"] if i1 else page.rect
                    box = fitz.Rect(prev.x0, prev.y1 + 2, prev.x1, min(prev.y1 + 72, page.rect.y1 - 12))
                    if box.height < 16:
                        box = fitz.Rect(page.rect.x0 + 36, page.rect.y1 - 90, page.rect.x1 - 36, page.rect.y1 - 24)
                    fontsize, color, fontname = 11.0, (0.0, 0.0, 0.0), "helv"
                pending.append((box, "\n\n".join(new), fontsize, color, fontname))

    _apply_redactions(page)
    for rect, text, fontsize, color, fontname in pending:
        _insert_in_rect(page, rect, text, fontsize, color, fontname)


def save_original_layout_pdf(
    path: str | Path,
    source: fitz.Document,
    pages: list[str],
) -> None:
    """Copy the original PDF and write edited text into the existing layout."""
    out = fitz.open()
    try:
        out.insert_pdf(source)
        count = min(out.page_count, len(pages))
        for i in range(count):
            _apply_page_edits(out[i], pages[i])
        out.save(str(path), deflate=True, garbage=4, encryption=fitz.PDF_ENCRYPT_NONE)
    finally:
        out.close()

