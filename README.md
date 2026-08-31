# PdfShred

Local desktop app: open a PDF, extract and edit the text, save a copyable `.txt` or `.pdf`. Nothing is uploaded.

You can also **just view** a PDF. **Page dark** / **Page light** flips the page (and the editor) for night reading.

![PdfShred with a light page](https://raw.githubusercontent.com/JxDog72/PdfShred/screenshots/light.png)

![PdfShred with a dark page](https://raw.githubusercontent.com/JxDog72/PdfShred/screenshots/dark.png)

**Keep layout** copies the original PDF and writes your edits back into those pages. It is close — not a perfect clone of every font, box, and line.

![Original page vs Keep layout copy](https://raw.githubusercontent.com/JxDog72/PdfShred/screenshots/keep-layout.png)

**License:** [MIT](LICENSE).

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

`winocr` uses Windows OCR. Without it, digital text still extracts; scanned pages need Tesseract if you have it installed.

**OCR page** means Optical Character Recognition: it looks at the page *as a picture* and types out the words. Use it when the PDF is a scan or photo (no selectable text). Digital PDFs already have a text layer, so Open is enough.

Double-click `Run-PdfShred.bat` to start. On Windows the black console window closes after launch.

---

## Linux

```bash
sudo apt install python3 python3-tk python3-pip tesseract-ocr tesseract-ocr-eng
python3 -m pip install -r requirements.txt
chmod +x run-pdfshred.sh
./run-pdfshred.sh
```

Or: `python3 app.py /path/to/file.pdf`

---

## Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+O | Open |
| Ctrl+S | Save text |
| Ctrl+Shift+S | Save PDF |
| Page Up / Page Down | Previous / next page |

Drag the vertical bar between PAGE and TEXT to resize the panes.

**Save PDF** writes a new, copyable file from the edited text (plain pages, no original layout).

**Keep layout** keeps the original pages, images, and form fields, then drops your edited text into the old boxes. Scanned pages keep the page image and get a hidden text layer so the file is still copyable. Pick a new filename so the open file is not overwritten.
