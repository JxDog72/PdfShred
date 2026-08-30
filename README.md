# PdfShred

Local desktop app that opens a PDF, pulls the text out (even when a viewer blocks copy), lets you edit it, and saves a new copyable `.txt` or `.pdf`.

Nothing is uploaded. Files stay on your machine.

**License:** [MIT](LICENSE). No warranty. You are responsible for having the right to copy and edit the documents you open.

---

## Why it exists

Filling several long forms meant pasting the same answers over and over. Viewers that honor a PDF “do not copy” flag made that miserable, and scanned pages have no text layer at all. PdfShred was built in a short sitting so those pages become selectable text.

---

## Is this legal to publish?

Yes, as a personal PDF reader/extractor.

- It does **not** crack user passwords. Encrypted PDFs still ask for the password.
- PDF “do not copy / print only” bits are **permission flags** that viewers may honor. Libraries such as PyMuPDF read the text layer anyway. That is the same class of behavior as `pdftotext` / `mutool`.
- It does **not** strip commercial ebook DRM (Adobe ADEPT, Kindle, etc.).
- You must have the **right** to copy the file you open. PdfShred does not grant copyright.

Linux already has strong CLI PDF tools (`pdftotext`, `ocrmypdf`, Stirling-PDF). PdfShred is a small desktop UI for “open → copy this paragraph → save.” That workflow is worth keeping on Kali/Parrot as well.

---

## What it does

- **Open** a PDF (dialog, command-line path, or drop a file on the Windows `.bat`)
- **Read** the page on the left; **edit** extracted text on the right
- **Drag the mid bar** between the panes to grow the page or the text (or hide one side)
- **Page dark / Page light** inverts the page preview (and the editor paper) so a white PDF is easier at night
- **Copy** from the editor, **Copy page**, **Copy all**, or **drag a box** on the page
- **OCR** scanned pages (Windows OCR on Windows; Tesseract on Linux)
- **Save text** (`.txt`) or **Save PDF** (a new, fully copyable PDF — layout is not preserved)

### How the drag-box copy works

It is **not** computer vision. When you drag a rectangle on the page, PdfShred maps that box to PDF coordinates and asks PyMuPDF for the **text layer** already stored in the file (`page.get_text(..., clip=...)`). If that box has no selectable text (a scan or photo), it falls back to **OCR** (Windows OCR, or Tesseract on Linux) on that same rectangle. No object-detection model is involved.

---

## Windows

Python 3.10+ on PATH.

```bat
Run-PdfShred.bat
```

Or:

```bat
python -m pip install -r requirements.txt
python -m pip install winocr
python app.py
python app.py "C:\path\to\file.pdf"
```

`winocr` uses the built-in Windows OCR engine. If it is missing, PdfShred still extracts digital text and will try Tesseract if you have it.

---

## Linux (Kali / Parrot / Debian)

```bash
sudo apt install python3 python3-tk python3-pip tesseract-ocr tesseract-ocr-eng
python3 -m pip install -r requirements.txt
chmod +x run-pdfshred.sh
./run-pdfshred.sh
# or: python3 app.py /path/to/file.pdf
```

Scanned pages need Tesseract. Digital text extraction works without it.

---

## Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+O | Open |
| Ctrl+S | Save text |
| Ctrl+Shift+S | Save PDF |
| Page Up / Page Down | Previous / next page |

Drag the vertical sash between PAGE and TEXT to resize (or collapse) either pane.

---

## Notes

Saving a PDF writes a **new** file from the edited text. It does not keep the original layout, fonts, or form fields.

---

## Project layout

```
pdfEditor/          (folder name on disk)
├── app.py          PdfShred UI
├── pdf_io.py       open / extract / OCR / save
├── requirements.txt
├── Run-PdfShred.bat
├── run-pdfshred.sh
└── LICENSE
```
