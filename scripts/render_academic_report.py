"""Print the local manuscript to PDF and inspect every resulting page."""

import argparse
import json
import math
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright


def render(folder: Path):
    manuscript = (folder / "Informe_Gemelo_Digital_Cali.html").resolve()
    destination = folder / "Informe_Gemelo_Digital_Cali.pdf"
    footer = (
        '<div style="width:100%;font-family:Arial,sans-serif;font-size:8px;'
        'color:#647480;padding:0 22mm;display:flex;justify-content:space-between">'
        "<span>Gemelo digital de Cali · Quintero Estrada y Arias Pantoja</span>"
        '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 1400})
        page.goto(manuscript.as_uri(), wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        assert page.locator("img").evaluate_all(
            "imgs => imgs.every(i => i.complete && i.naturalWidth > 0)"
        )
        page.pdf(
            path=str(destination),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<span></span>",
            footer_template=footer,
            prefer_css_page_size=True,
            tagged=True,
            outline=True,
            margin={"top": "22mm", "bottom": "21mm", "left": "22mm", "right": "22mm"},
        )
        browser.close()
    with fitz.open(destination) as document:
        document.set_metadata(
            {
                "title": "Gemelo digital de movilidad urbana en Cali",
                "author": "Milton Alberto Quintero Estrada; Jose David Arias Pantoja",
                "subject": "Evaluación experimental de control semafórico PPO",
                "keywords": "Cali, SUMO, PPO, movilidad urbana, aprendizaje por refuerzo",
            }
        )
        document.saveIncr()
    preview = folder / "preview"
    preview.mkdir(exist_ok=True)
    with fitz.open(destination) as document:
        texts = [page.get_text() for page in document]
        full_text = "\n".join(texts)
        assert "Milton Alberto Quintero Estrada" in full_text
        assert "Jose David Arias Pantoja" in full_text
        assert "66,5 %" in full_text and "18,92" in full_text
        assert "[[PAGEBREAK]]" not in full_text and "{{" not in full_text
        assert all(len(text.strip()) > 80 for text in texts), "unexpected blank page"
        clipping = []
        for i, page in enumerate(document):
            for block in page.get_text("blocks"):
                if block[0] < -1 or block[2] > page.rect.width + 1:
                    clipping.append({"page": i + 1, "box": list(block[:4])})
            if i == 0 or "Tabla 5." in texts[i] or "Tabla 6." in texts[i]:
                page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2)).save(preview / f"page-{i + 1:02}.png")
        assert not clipping, clipping
        sheet = fitz.open()
        columns = 4
        rows = math.ceil(len(document) / columns)
        overview = sheet.new_page(width=columns * 190, height=rows * 280)
        for i in range(len(document)):
            x, y = (i % columns) * 190, (i // columns) * 280
            overview.show_pdf_page(fitz.Rect(x + 4, y + 4, x + 186, y + 268), document, i)
            overview.insert_text((x + 88, y + 277), str(i + 1), fontsize=7)
        overview.get_pixmap(matrix=fitz.Matrix(1.6, 1.6)).save(preview / "contact-sheet.png")
        sheet.close()
        quality = {
            "status": "passed",
            "pages": len(document),
            "authors_verified": True,
            "results_verified": True,
            "blank_pages": 0,
            "clipped_blocks": clipping,
            "page_text_lengths": [len(text) for text in texts],
        }
        (folder / "pdf-quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
        print(json.dumps(quality))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    render(args.folder)
