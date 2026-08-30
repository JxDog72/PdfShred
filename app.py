#!/usr/bin/env python3
"""PdfShred — open a PDF, copy its text, edit, and save."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox

import customtkinter as ctk
import fitz
from PIL import Image, ImageOps, ImageTk

from pdf_io import (
    extract_all_pages,
    extract_clip,
    ocr_page_text,
    open_document,
    page_has_images,
    render_page,
    save_original_layout_pdf,
    save_text_file,
    save_text_pdf,
)

UI_FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"

# Brass desk lamp on a dark walnut desk — preview stays paper-white.
COLORS = {
    "bg": "#161311",
    "panel": "#211c18",
    "panel2": "#2a241e",
    "border": "#3d342c",
    "text": "#f0e6d8",
    "muted": "#9a8b78",
    "accent": "#d4783c",
    "accent_hover": "#e08950",
    "ok": "#8fbf7a",
    "danger": "#d46868",
    "paper": "#f3ead7",
    "ink": "#1a140f",
    "btn": "#2f2822",
    "btn_hover": "#3d342c",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


def copy_to_clipboard(widget: ctk.CTkBaseClass, text: str) -> None:
    widget.clipboard_clear()
    widget.clipboard_append(text)
    widget.update()


class PdfShred(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PdfShred")
        self.geometry("1280x800")
        self.minsize(900, 600)
        self.configure(fg_color=COLORS["bg"])

        self.doc: fitz.Document | None = None
        self.path: Path | None = None
        self.page_index = 0
        self.page_texts: list[str] = []
        self._loaded_texts: list[str] = []
        self.zoom = 1.35
        self._photo: ImageTk.PhotoImage | None = None
        self._drag_start: tuple[float, float] | None = None
        self._sel_id: int | None = None
        self._ocr_busy = False
        self._fit_pending = False
        self._page_dark = False

        self._build()
        self.bind("<Control-o>", lambda e: self.open_pdf())
        self.bind("<Control-O>", lambda e: self.open_pdf())
        self.bind("<Control-s>", lambda e: self.save_txt())
        self.bind("<Control-S>", lambda e: self.save_txt())
        self.bind("<Control-Shift-s>", lambda e: self.save_pdf())
        self.bind("<Control-Shift-S>", lambda e: self.save_pdf())
        self.bind("<Prior>", lambda e: self.goto_page(self.page_index - 1))
        self.bind("<Next>", lambda e: self.goto_page(self.page_index + 1))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if len(sys.argv) > 1:
            self.after(80, lambda: self.open_path(Path(sys.argv[1])))

    def _font(self, size: int, weight: str = "normal") -> ctk.CTkFont:
        return ctk.CTkFont(family=UI_FONT, size=size, weight=weight)

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color=COLORS["panel"], height=64, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="PDFSHRED",
            font=ctk.CTkFont(family=UI_FONT, size=18, weight="bold"),
            text_color=COLORS["accent"],
        ).pack(side="left", padx=(18, 8))
        ctk.CTkLabel(
            header,
            text="Open · copy · edit PDFs — text stays on this machine",
            font=self._font(13),
            text_color=COLORS["muted"],
        ).pack(side="left")

        self._btn(header, "Open PDF", self.open_pdf, accent=True).pack(
            side="right", padx=16, pady=14
        )

        toolbar = ctk.CTkFrame(self, fg_color=COLORS["panel2"], height=48, corner_radius=0)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        self._btn(toolbar, "◀", lambda: self.goto_page(self.page_index - 1), w=40).pack(
            side="left", padx=(12, 4), pady=8
        )
        self._btn(toolbar, "▶", lambda: self.goto_page(self.page_index + 1), w=40).pack(
            side="left", padx=4, pady=8
        )
        self.page_label = ctk.CTkLabel(
            toolbar, text="No file", font=self._font(13), text_color=COLORS["text"]
        )
        self.page_label.pack(side="left", padx=10)

        self._btn(toolbar, "−", lambda: self.set_zoom(self.zoom - 0.15), w=40).pack(
            side="left", padx=(16, 4), pady=8
        )
        self._btn(toolbar, "+", lambda: self.set_zoom(self.zoom + 0.15), w=40).pack(
            side="left", padx=4, pady=8
        )
        self._btn(toolbar, "Fit", self.fit_width, w=56).pack(side="left", padx=4, pady=8)
        self._theme_btn = self._btn(toolbar, "Page dark", self.toggle_page_theme, w=96)
        self._theme_btn.pack(side="left", padx=(16, 4), pady=8)

        self._btn(toolbar, "Copy page", self.copy_page).pack(side="right", padx=(4, 12), pady=8)
        self._btn(toolbar, "Copy all", self.copy_all).pack(side="right", padx=4, pady=8)
        self._ocr_btn = self._btn(toolbar, "OCR page", self.ocr_current_page)
        self._ocr_btn.pack(side="right", padx=4, pady=8)
        self._ocr_btn.bind(
            "<Enter>",
            lambda e: self.set_status(
                "OCR: read text from a photo/scan of this page when there is no selectable text layer."
            ),
        )
        self._btn(toolbar, "Keep layout", self.save_original_pdf).pack(side="right", padx=4, pady=8)
        self._btn(toolbar, "Save PDF", self.save_pdf).pack(side="right", padx=4, pady=8)
        self._btn(toolbar, "Save text", self.save_txt).pack(side="right", padx=4, pady=8)

        body = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        body.pack(fill="both", expand=True, padx=10, pady=(8, 4))

        self._paned = tk.PanedWindow(
            body,
            orient=tk.HORIZONTAL,
            sashwidth=8,
            sashrelief=tk.FLAT,
            sashpad=1,
            bd=0,
            bg=COLORS["border"],
            opaqueresize=True,
        )
        self._paned.pack(fill="both", expand=True)

        left = ctk.CTkFrame(self._paned, fg_color=COLORS["bg"], corner_radius=0)
        ctk.CTkLabel(
            left,
            text="PAGE  ·  drag a box to copy  ·  drag the mid bar to resize",
            font=self._font(11),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", padx=4, pady=(0, 4))

        canvas_wrap = ctk.CTkFrame(left, fg_color=COLORS["panel"], corner_radius=8)
        canvas_wrap.pack(fill="both", expand=True)

        self.canvas = ctk.CTkCanvas(
            canvas_wrap,
            background=COLORS["panel2"],
            highlightthickness=0,
        )
        yscroll = ctk.CTkScrollbar(canvas_wrap, orientation="vertical", command=self.canvas.yview)
        xscroll = ctk.CTkScrollbar(canvas_wrap, orientation="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        canvas_wrap.grid_rowconfigure(0, weight=1)
        canvas_wrap.grid_columnconfigure(0, weight=1)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", lambda e: self._maybe_fit())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", self._on_wheel)
        self.canvas.bind("<Button-5>", self._on_wheel)

        right = ctk.CTkFrame(self._paned, fg_color=COLORS["bg"], corner_radius=0)
        ctk.CTkLabel(
            right,
            text="TEXT  ·  select and copy, or edit then save",
            font=self._font(11),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", padx=4, pady=(0, 4))

        self.editor = ctk.CTkTextbox(
            right,
            font=ctk.CTkFont(family="Georgia", size=15),
            fg_color=COLORS["paper"],
            text_color=COLORS["ink"],
            wrap="word",
            corner_radius=8,
            border_width=0,
            undo=True,
        )
        self.editor.pack(fill="both", expand=True)
        self.editor.bind("<KeyRelease>", lambda e: self._stash_editor())

        self._paned.add(left, minsize=160, stretch="always", width=780)
        self._paned.add(right, minsize=140, stretch="always", width=440)

        status = ctk.CTkFrame(self, fg_color=COLORS["panel"], height=32, corner_radius=0)
        status.pack(fill="x", side="bottom")
        status.pack_propagate(False)
        self.status = ctk.CTkLabel(
            status,
            text="Open a PDF. Digital text is extracted even if a viewer blocks copy.",
            font=self._font(12),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.status.pack(fill="x", padx=14)

        self._draw_empty()

    def _btn(self, parent, text, command, accent: bool = False, w: int | None = None):
        kwargs = {
            "text": text,
            "command": command,
            "font": self._font(13, "bold" if accent else "normal"),
            "corner_radius": 6,
            "height": 32,
            "fg_color": COLORS["accent"] if accent else COLORS["btn"],
            "hover_color": COLORS["accent_hover"] if accent else COLORS["btn_hover"],
            "text_color": "#1a140f" if accent else COLORS["text"],
        }
        if w is not None:
            kwargs["width"] = w
        return ctk.CTkButton(parent, **kwargs)

    def set_status(self, msg: str, ok: bool | None = None) -> None:
        color = COLORS["muted"]
        if ok is True:
            color = COLORS["ok"]
        elif ok is False:
            color = COLORS["danger"]
        self.status.configure(text=msg, text_color=color)

    def _draw_empty(self) -> None:
        self.canvas.delete("all")
        self.canvas.create_text(
            40,
            80,
            anchor="nw",
            fill=COLORS["muted"],
            font=(UI_FONT, 16),
            text="Open a PDF to start.\n\nDrag a box on the page to grab one paragraph.\nCtrl+O  open    ·    Ctrl+S  save text    ·    Ctrl+Shift+S  save PDF",
        )

    def _is_dirty(self) -> bool:
        self._stash_editor()
        if not self.page_texts:
            return False
        return self.page_texts != self._loaded_texts

    def _on_close(self) -> None:
        if self._is_dirty():
            if not messagebox.askyesno(
                "PdfShred",
                "You have unsaved edits. Close anyway?",
                parent=self,
            ):
                return
        self.destroy()

    def destroy(self) -> None:
        self._stash_editor()
        if self.doc is not None:
            self.doc.close()
            self.doc = None
        super().destroy()

    def _stash_editor(self) -> None:
        if not self.page_texts:
            return
        if 0 <= self.page_index < len(self.page_texts):
            self.page_texts[self.page_index] = self.editor.get("1.0", "end-1c")

    def _show_page_text(self) -> None:
        self.editor.delete("1.0", "end")
        if 0 <= self.page_index < len(self.page_texts):
            self.editor.insert("1.0", self.page_texts[self.page_index])

    def open_pdf(self) -> None:
        path = filedialog.askopenfilename(
            title="Open PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path) -> None:
        path = Path(path)
        if not path.exists():
            self.set_status(f"File not found: {path}", ok=False)
            return
        password = ""
        try:
            doc = open_document(path, password)
        except PermissionError as err:
            if str(err) == "PASSWORD_REQUIRED":
                password = simpledialog.askstring(
                    "Password",
                    "This PDF is encrypted. Enter the password:",
                    show="*",
                    parent=self,
                )
                if password is None:
                    self.set_status("Open cancelled.")
                    return
                try:
                    doc = open_document(path, password)
                except PermissionError:
                    self.set_status("Wrong password or the file could not be opened.", ok=False)
                    return
            else:
                self.set_status("Wrong password or the file could not be opened.", ok=False)
                return
        except Exception as exc:
            self.set_status(f"Could not open PDF: {exc}", ok=False)
            return

        if self.doc is not None:
            self.doc.close()

        self.doc = doc
        self.path = path
        self.page_index = 0
        self.page_texts = extract_all_pages(doc)
        self._loaded_texts = list(self.page_texts)
        nonempty = sum(1 for t in self.page_texts if t.strip())
        self._show_page_text()
        self._render()
        self.title(f"PdfShred — {path.name}")

        if nonempty == 0:
            self.set_status(
                f"Opened {path.name}  ·  {doc.page_count} page(s)  ·  no selectable text. Reading the page image…"
            )
            self.ocr_current_page(auto=True)
        else:
            self.set_status(
                f"Opened {path.name}  ·  {doc.page_count} page(s)  ·  text on {nonempty}.",
                ok=True,
            )

    def goto_page(self, index: int) -> None:
        if self.doc is None:
            return
        self._stash_editor()
        index = max(0, min(index, self.doc.page_count - 1))
        if index == self.page_index and self._photo is not None:
            return
        self.page_index = index
        self._show_page_text()
        self._render()
        if not self.page_texts[self.page_index].strip():
            self.ocr_current_page(auto=True)

    def toggle_page_theme(self) -> None:
        self._page_dark = not self._page_dark
        if self._page_dark:
            self._theme_btn.configure(text="Page light")
            self.canvas.configure(background="#12110f")
            self.editor.configure(fg_color="#1c1814", text_color="#e8dcc8")
        else:
            self._theme_btn.configure(text="Page dark")
            self.canvas.configure(background=COLORS["panel2"])
            self.editor.configure(fg_color=COLORS["paper"], text_color=COLORS["ink"])
        self._render()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = max(0.4, min(zoom, 3.5))
        self._render()

    def fit_width(self) -> None:
        if self.doc is None:
            return
        page = self.doc[self.page_index]
        width = max(self.canvas.winfo_width(), 200)
        if page.rect.width:
            self.zoom = max(0.4, min((width - 24) / page.rect.width, 3.5))
        self._render()

    def _maybe_fit(self) -> None:
        if self.doc is None or self._photo is not None:
            return
        if not self._fit_pending:
            self._fit_pending = True
            self.after(80, self._do_first_fit)

    def _do_first_fit(self) -> None:
        self._fit_pending = False
        if self.doc is not None and self._photo is None:
            self.fit_width()

    def _render(self) -> None:
        if self.doc is None:
            self._draw_empty()
            self.page_label.configure(text="No file")
            return
        page = self.doc[self.page_index]
        pix = render_page(page, self.zoom)
        mode = "RGB" if pix.n < 4 else "RGBA"
        image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        if mode == "RGBA":
            image = image.convert("RGB")
        if self._page_dark:
            image = ImageOps.invert(image)
        self._photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo, tags=("page",))
        self.canvas.configure(scrollregion=(0, 0, pix.width, pix.height))
        self.page_label.configure(text=f"Page {self.page_index + 1} / {self.doc.page_count}")
        self._sel_id = None

    def _on_wheel(self, event) -> None:
        delta = getattr(event, "delta", 0)
        num = getattr(event, "num", 0)
        if delta:
            self.canvas.yview_scroll(int(-delta / 120), "units")
        elif num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif num == 5:
            self.canvas.yview_scroll(1, "units")

    def _canvas_to_pdf(self, x: float, y: float) -> tuple[float, float]:
        assert self.doc is not None
        page = self.doc[self.page_index]
        return page.rect.x0 + x / self.zoom, page.rect.y0 + y / self.zoom

    def _on_press(self, event) -> None:
        if self.doc is None:
            return
        self._drag_start = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if self._sel_id is not None:
            self.canvas.delete(self._sel_id)
            self._sel_id = None

    def _on_drag(self, event) -> None:
        if self._drag_start is None:
            return
        x0, y0 = self._drag_start
        x1 = self.canvas.canvasx(event.x)
        y1 = self.canvas.canvasy(event.y)
        if self._sel_id is None:
            self._sel_id = self.canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                outline=COLORS["accent"],
                width=2,
                dash=(4, 3),
            )
        else:
            self.canvas.coords(self._sel_id, x0, y0, x1, y1)

    def _on_release(self, event) -> None:
        if self.doc is None or self._drag_start is None:
            return
        x0, y0 = self._drag_start
        self._drag_start = None
        x1 = self.canvas.canvasx(event.x)
        y1 = self.canvas.canvasy(event.y)
        if abs(x1 - x0) < 8 and abs(y1 - y0) < 8:
            return
        ax, ay = self._canvas_to_pdf(x0, y0)
        bx, by = self._canvas_to_pdf(x1, y1)
        rect = fitz.Rect(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))
        text = extract_clip(self.doc[self.page_index], rect)
        if text.strip():
            copy_to_clipboard(self, text)
            self.set_status(f"Copied {len(text)} characters from the selected box.", ok=True)
            return
        self.set_status("No text layer in that box — reading the image…")
        self.ocr_current_page(clip=rect, copy_only=True)

    def copy_page(self) -> None:
        self._stash_editor()
        text = self.editor.get("1.0", "end-1c")
        try:
            selected = self.editor.get("sel.first", "sel.last")
        except Exception:
            selected = ""
        payload = selected if selected else text
        if not payload.strip():
            self.set_status("Nothing to copy on this page.", ok=False)
            return
        copy_to_clipboard(self, payload)
        kind = "selection" if selected else "page"
        self.set_status(f"Copied {kind} ({len(payload)} characters).", ok=True)

    def copy_all(self) -> None:
        self._stash_editor()
        if not self.page_texts:
            self.set_status("Open a PDF first.", ok=False)
            return
        chunks = []
        for i, text in enumerate(self.page_texts, start=1):
            chunks.append(f"----- page {i} -----\n{text.rstrip()}")
        payload = "\n\n".join(chunks).strip()
        if not payload:
            self.set_status("No text in this file. Try OCR on each page.", ok=False)
            return
        copy_to_clipboard(self, payload)
        self.set_status(f"Copied all pages ({len(payload)} characters).", ok=True)

    def save_txt(self) -> None:
        self._stash_editor()
        if not self.page_texts:
            self.set_status("Open a PDF first.", ok=False)
            return
        initial = (self.path.stem + ".txt") if self.path else "extracted.txt"
        path = filedialog.asksaveasfilename(
            title="Save text",
            defaultextension=".txt",
            initialfile=initial,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            save_text_file(path, self.page_texts)
        except OSError as exc:
            self.set_status(f"Could not save text: {exc}", ok=False)
            return
        self._loaded_texts = list(self.page_texts)
        self.set_status(f"Saved text to {Path(path).name}", ok=True)

    def save_pdf(self) -> None:
        self._stash_editor()
        if not self.page_texts:
            self.set_status("Open a PDF first.", ok=False)
            return
        initial = (self.path.stem + "-editable.pdf") if self.path else "editable.pdf"
        path = filedialog.asksaveasfilename(
            title="Save as copyable PDF",
            defaultextension=".pdf",
            initialfile=initial,
            filetypes=[("PDF files", "*.pdf")],
        )
        if not path:
            return
        try:
            save_text_pdf(path, self.page_texts)
        except OSError as exc:
            self.set_status(f"Could not save PDF: {exc}", ok=False)
            return
        self._loaded_texts = list(self.page_texts)
        self.set_status(
            f"Saved a new copyable PDF: {Path(path).name}",
            ok=True,
        )

    def save_original_pdf(self) -> None:
        self._stash_editor()
        if self.doc is None or not self.page_texts:
            self.set_status("Open a PDF first.", ok=False)
            return
        initial = (self.path.stem + "-edited.pdf") if self.path else "edited.pdf"
        path = filedialog.asksaveasfilename(
            title="Save original layout with edits",
            defaultextension=".pdf",
            initialfile=initial,
            filetypes=[("PDF files", "*.pdf")],
        )
        if not path:
            return
        if self.path is not None and Path(path).resolve() == self.path.resolve():
            self.set_status("Choose a new filename so the open PDF is not overwritten.", ok=False)
            return
        try:
            save_original_layout_pdf(path, self.doc, self.page_texts)
        except Exception as exc:
            self.set_status(f"Could not save original layout: {exc}", ok=False)
            return
        self._loaded_texts = list(self.page_texts)
        self.set_status(
            f"Saved original layout with your edits: {Path(path).name}",
            ok=True,
        )

    def ocr_current_page(
        self,
        auto: bool = False,
        clip: fitz.Rect | None = None,
        copy_only: bool = False,
    ) -> None:
        if self.doc is None:
            self.set_status("Open a PDF first.", ok=False)
            return
        if self._ocr_busy:
            return
        page = self.doc[self.page_index]
        page_index = self.page_index
        self._ocr_busy = True
        self.set_status("Reading text from the page image…")

        def work() -> None:
            err = ""
            text = ""
            try:
                text = ocr_page_text(page, clip=clip)
            except Exception as exc:
                err = str(exc)
            self.after(
                0,
                lambda t=text, e=err: self._ocr_done(
                    t, e, page_index, auto=auto, copy_only=copy_only
                ),
            )

        threading.Thread(target=work, daemon=True).start()

    def _ocr_done(
        self,
        text: str,
        err: str,
        page_index: int,
        auto: bool = False,
        copy_only: bool = False,
    ) -> None:
        self._ocr_busy = False
        if err:
            self.set_status(f"Could not read text from the page image. {err}", ok=False)
            return
        if not text.strip():
            hint = ""
            if self.doc is not None and page_has_images(self.doc[self.page_index]):
                hint = " This page looks like a photo of text."
            self.set_status("No text could be read from that area." + hint, ok=False)
            return
        if copy_only:
            copy_to_clipboard(self, text)
            self.set_status(f"Copied {len(text)} characters from the selected box.", ok=True)
            return
        if 0 <= page_index < len(self.page_texts):
            self.page_texts[page_index] = text
        if page_index == self.page_index:
            self._show_page_text()
        if not auto:
            copy_to_clipboard(self, text)
            self.set_status(
                f"Read {len(text)} characters from the page image. Copied this page.",
                ok=True,
            )
        else:
            self.set_status(
                f"Read {len(text)} characters from the page image. You can copy from the right.",
                ok=True,
            )


def main() -> None:
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = PdfShred()
    app.mainloop()


if __name__ == "__main__":
    main()
